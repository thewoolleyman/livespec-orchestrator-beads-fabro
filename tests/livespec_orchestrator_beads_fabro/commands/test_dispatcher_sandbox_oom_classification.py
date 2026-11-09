"""A run whose sandbox container was OOM-killed is permanent and names the kill.

Scenario 335 in `SPECIFICATION/scenarios.md`, governed by `contracts.md`
section "Provider-limit permanence and root-cause surfacing" -> "A sandbox
killed for memory is named." (`bd-ib-jnstxo`). The evidence is the sandbox
provider's report of the container's termination, read while the sandbox still
exists; the failure text alone ("reaching the Kubernetes API failed") is what
the engine already records as `transient_infra` and is NOT evidence of an OOM
kill.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_terminal import (
    fabro_run_terminal_outcome,
    inspect_run,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan

_RUN = "01M70P2CVG4SYMMBXGBZZSWM2W"
_SERVER = "https://petri.example:32276"
_EXEC_FAILURE = (
    "sandbox exec failed: starting a command in the sandbox: reaching the Kubernetes API "
    "failed: failed to upgrade to a WebSocket connection: failed to switch protocol: "
    "500 Internal Server Error"
)
_ARRIVED_SIGNATURE = "implement|transient_infra|a1b2c3"
_LIMIT_BYTES = 7629 * 1024 * 1024
_SCRIPTS = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _pod(*, terminated_reason: str | None, memory: str | None = "7629Mi") -> dict[str, Any]:
    state: dict[str, Any] = (
        {"running": {}}
        if terminated_reason is None
        else {"terminated": {"reason": terminated_reason, "exitCode": 137}}
    )
    limits: dict[str, str] = {} if memory is None else {"memory": memory}
    return {
        "metadata": {"name": f"fabro-run-{_RUN.lower()}", "namespace": "fabro"},
        "spec": {"containers": [{"name": "sandbox", "resources": {"limits": limits}}]},
        "status": {"containerStatuses": [{"name": "sandbox", "state": state}]},
    }


@dataclass(kw_only=True)
class _Runner:
    pods: list[dict[str, Any]] = field(default_factory=list)
    kubectl_exit: int = 0
    status_kind: str = "failed"
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        self.calls.append(argv)
        if argv[0] == "kubectl":
            return CommandResult(
                exit_code=self.kubectl_exit,
                stdout=json.dumps({"items": self.pods}) if self.kubectl_exit == 0 else "",
                stderr="" if self.kubectl_exit == 0 else "the server could not be reached",
            )
        if argv[1] == "events":
            return CommandResult(exit_code=0, stdout="[]", stderr="")
        assert argv[1] == "inspect"
        return CommandResult(
            exit_code=0,
            stderr="",
            stdout=json.dumps(
                [
                    {
                        "run_id": _RUN,
                        "status": {"kind": self.status_kind},
                        "failure": {
                            "causes": [_EXEC_FAILURE],
                            "category": "transient_infra",
                            "signature": _ARRIVED_SIGNATURE,
                        },
                    }
                ]
            ),
        )


def _plan(*, tmp_path: Path) -> DispatchPlan:
    return DispatchPlan(
        repo=tmp_path,
        work_item_id="bd-ib-jnstxo",
        branch="feat/bd-ib-jnstxo",
        workflow_toml=tmp_path / "workflow.toml",
        goal_file=tmp_path / "goal.txt",
        fabro_bin="fabro",
        fabro_factory_name="petri",
        fabro_factory_server=_SERVER,
        fabro_factory_dev_token=None,
        janitor=None,
        janitor_checkout=tmp_path / ".janitor",
        janitor_core_checkout=tmp_path / ".janitor" / ".livespec-core",
        janitor_core_repo_url="https://github.com/thewoolleyman/livespec.git",
        janitor_core_ref="master",
        review_fix_visit_cap=3,
        merge_on_review_cap_outcome="succeeded",
    )


def _derive(*, tmp_path: Path, runner: _Runner) -> tuple[Any, DispatchOutcome, _Journal]:
    plan = _plan(tmp_path=tmp_path)
    journal = _Journal()
    inspect = inspect_run(plan=plan, runner=runner, journal=journal, run_id=_RUN)
    assert inspect is not None
    outcome = fabro_run_terminal_outcome(
        outcome_type=DispatchOutcome,
        plan=plan,
        run_id=_RUN,
        inspect=inspect,
        exit_code=1,
        stderr="",
    )
    assert outcome is not None
    return inspect, outcome, journal


def test_oom_killed_sandbox_is_permanent_and_names_the_kill(*, tmp_path: Path) -> None:
    runner = _Runner(pods=[_pod(terminated_reason="OOMKilled")])

    inspect, outcome, journal = _derive(tmp_path=tmp_path, runner=runner)

    failure = inspect.failure
    assert failure.category == "deterministic"
    assert failure.signature == "implement|deterministic|a1b2c3"
    assert failure.provider_usage_limit is False
    assert failure.provider_usage_limit_provider is None
    exhaustion = failure.resource_exhaustion
    assert exhaustion.kind == "sandbox-oom-killed"
    assert exhaustion.run_id == _RUN
    assert exhaustion.memory_limit_bytes == _LIMIT_BYTES
    assert outcome.fabro_failure_category == "deterministic"
    assert outcome.fabro_failure_signature == "implement|deterministic|a1b2c3"
    assert outcome.provider_usage_limit is False
    for named in ("OOM", _RUN, str(_LIMIT_BYTES)):
        assert named in outcome.detail
    recorded = asdict(outcome)["sandbox_termination"]
    assert recorded["oom_killed"] is True
    assert recorded["run_id"] == _RUN
    assert recorded["memory_limit_bytes"] == _LIMIT_BYTES
    termination_rows = [r for r in journal.records if r.get("stage") == "fabro-sandbox-termination"]
    assert len(termination_rows) == 1
    assert _RUN in json.dumps(termination_rows[0])


def test_oom_without_a_reported_limit_records_the_limit_as_unobservable(*, tmp_path: Path) -> None:
    runner = _Runner(pods=[_pod(terminated_reason="OOMKilled", memory=None)])

    inspect, outcome, _ = _derive(tmp_path=tmp_path, runner=runner)

    assert inspect.failure.category == "deterministic"
    assert inspect.failure.resource_exhaustion.memory_limit_bytes is None
    assert "memory limit unobservable" in outcome.detail


def test_connection_failure_with_no_oom_kill_keeps_its_classification(*, tmp_path: Path) -> None:
    runner = _Runner(pods=[_pod(terminated_reason=None)])

    inspect, outcome, _ = _derive(tmp_path=tmp_path, runner=runner)

    assert inspect.failure.category == "transient_infra"
    assert inspect.failure.signature == _ARRIVED_SIGNATURE
    assert inspect.failure.resource_exhaustion is None
    assert outcome.fabro_failure_category == "transient_infra"
    assert "unobservable" not in outcome.detail
    assert "OOM" not in outcome.detail


@pytest.mark.parametrize(
    "runner",
    [
        _Runner(kubectl_exit=1),
        _Runner(pods=[]),
        _Runner(pods=[_pod(terminated_reason="OOMKilled") | {"metadata": {"name": "other"}}]),
    ],
)
def test_unreadable_termination_is_reported_as_unobservable(
    *, tmp_path: Path, runner: _Runner
) -> None:
    inspect, outcome, _ = _derive(tmp_path=tmp_path, runner=runner)

    assert inspect.failure.category == "transient_infra"
    assert inspect.failure.signature == _ARRIVED_SIGNATURE
    assert inspect.failure.resource_exhaustion is None
    assert "termination unobservable" in outcome.detail
    assert asdict(outcome)["sandbox_termination"]["observed"] is False


def test_a_run_that_did_not_fail_reads_no_sandbox_termination(*, tmp_path: Path) -> None:
    runner = _Runner(pods=[_pod(terminated_reason="OOMKilled")], status_kind="succeeded")

    inspect_run(plan=_plan(tmp_path=tmp_path), runner=runner, journal=_Journal(), run_id=_RUN)

    assert all(call[0] != "kubectl" for call in runner.calls)


def test_the_termination_reader_lives_in_its_own_module() -> None:
    assert (_SCRIPTS / "_fabro_sandbox_termination.py").is_file()
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._fabro_sandbox_termination"
    )
    assert module.memory_quantity_bytes(text="7629Mi") == _LIMIT_BYTES
    assert module.memory_quantity_bytes(text="8Gi") == 8 * 1024**3
    assert module.memory_quantity_bytes(text="512M") == 512 * 10**6
    assert module.memory_quantity_bytes(text="1048576") == 1048576
    assert module.memory_quantity_bytes(text="lots") is None
