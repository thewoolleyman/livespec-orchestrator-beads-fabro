"""Consumer-tier acceptance for SPECIFICATION/scenarios.md Scenario 335.

Binds "## Scenario 335 — A run whose sandbox was OOM-killed is classified
permanent and names the kill and the memory limit". Its three Given/When/Then
blocks map 1:1 to the three cases below, and each is driven through `run_dispatch`,
the surface that derives a dispatched run's outcome and writes its journal, over a
runner that answers the engine's `inspect` and the cluster's pod listing the way
the two measured runs (`01M6YS4E7TG2`, `01M6YVGGFC9K`) left them: the stage's next
sandbox exec refused with the Kubernetes API's 500, recorded by the engine as
`transient_infra`, while the pod's container shows termination reason `OOMKilled`.

Everything is HERMETIC: no factory and no cluster is reached.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
    FabroRunResult,
    PollPolicy,
    run_dispatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan

_RUN = "01M6YS4E7TG2ZZZZZZZZZZZZZZ"
_EXEC_FAILURE = (
    "sandbox exec failed: starting a command in the sandbox: reaching the Kubernetes API "
    "failed: failed to upgrade to a WebSocket connection: failed to switch protocol: "
    "500 Internal Server Error"
)
_SIGNATURE = "implement|transient_infra|exec refused"
_LIMIT_BYTES = 7629 * 1024 * 1024


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@dataclass(kw_only=True)
class _Cluster:
    pods: str | None
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
            if self.pods is None:
                return CommandResult(exit_code=1, stdout="", stderr="the server is unreachable")
            return CommandResult(exit_code=0, stdout=self.pods, stderr="")
        if argv[1] == "events":
            return CommandResult(exit_code=0, stdout="[]", stderr="")
        return CommandResult(
            exit_code=0,
            stderr="",
            stdout=json.dumps(
                [
                    {
                        "run_id": _RUN,
                        "status": {"kind": "failed"},
                        "failure": {
                            "causes": [_EXEC_FAILURE],
                            "category": "transient_infra",
                            "signature": _SIGNATURE,
                        },
                    }
                ]
            ),
        )


@dataclass(frozen=True, kw_only=True)
class _FailedLauncher:
    def launch(self, *, plan: DispatchPlan, runner: _Cluster, journal: _Journal) -> FabroRunResult:
        _ = (plan, runner, journal)
        return FabroRunResult(
            command=CommandResult(exit_code=1, stdout="", stderr="exec refused"), run_id=_RUN
        )


def _pods(*, reason: str | None) -> str:
    state = {"running": {}} if reason is None else {"terminated": {"reason": reason}}
    pod = {
        "metadata": {"name": f"fabro-run-{_RUN.lower()}"},
        "spec": {
            "containers": [{"name": "sandbox", "resources": {"limits": {"memory": "7629Mi"}}}]
        },
        "status": {"containerStatuses": [{"name": "sandbox", "state": state}]},
    }
    return json.dumps({"items": [pod]})


def _plan(*, tmp_path: Path) -> DispatchPlan:
    return DispatchPlan(
        repo=tmp_path,
        work_item_id="bd-ib-jnstxo",
        branch="feat/bd-ib-jnstxo",
        workflow_toml=tmp_path / "workflow.toml",
        goal_file=tmp_path / "goal.txt",
        fabro_bin="fabro",
        fabro_factory_name="petri",
        fabro_factory_server=None,
        fabro_factory_dev_token=None,
        janitor=("just", "check"),
        janitor_checkout=tmp_path / ".janitor",
        janitor_core_checkout=tmp_path / ".janitor" / ".livespec-core",
        janitor_core_repo_url="https://github.com/thewoolleyman/livespec.git",
        janitor_core_ref="master",
        review_fix_visit_cap=3,
        merge_on_review_cap_outcome="succeeded",
    )


def _dispatch(*, tmp_path: Path, pods: str | None) -> tuple[DispatchOutcome, _Journal]:
    journal = _Journal()
    outcome = run_dispatch(
        plan=_plan(tmp_path=tmp_path),
        runner=_Cluster(pods=pods),
        journal=journal,
        sleep=lambda _seconds: None,
        poll=PollPolicy(attempts=1, interval_seconds=0.0),
        fabro_launcher=_FailedLauncher(),
    )
    return outcome, journal


def test_an_oom_killed_sandbox_reclassifies_the_failure_and_names_the_kill(
    *, tmp_path: Path
) -> None:
    outcome, journal = _dispatch(tmp_path=tmp_path, pods=_pods(reason="OOMKilled"))

    record = asdict(outcome)
    assert record["status"] == "failed"
    assert record["fabro_failure_category"] == "deterministic"
    assert record["fabro_failure_signature"] == "implement|deterministic|exec refused"
    assert record["provider_usage_limit"] is False
    assert record["provider_usage_limit_provider"] is None
    for named in ("OOM", _RUN, str(_LIMIT_BYTES)):
        assert named in record["detail"]
    termination = record["sandbox_termination"]
    assert (termination["run_id"], termination["memory_limit_bytes"]) == (_RUN, _LIMIT_BYTES)
    assert termination["oom_killed"] is True
    rows = [row for row in journal.records if row["stage"] == "fabro-sandbox-termination"]
    assert rows
    assert all(row["run_id"] == _RUN and row["memory_limit_bytes"] == _LIMIT_BYTES for row in rows)
    assert all(row["oom_killed"] is True for row in rows)


def test_a_connection_failure_with_no_oom_kill_keeps_its_classification(*, tmp_path: Path) -> None:
    outcome, _ = _dispatch(tmp_path=tmp_path, pods=_pods(reason=None))

    record = asdict(outcome)
    assert record["fabro_failure_category"] == "transient_infra"
    assert record["fabro_failure_signature"] == _SIGNATURE
    assert "sandbox_termination" in record
    assert "OOM" not in record["detail"]


@pytest.mark.parametrize("pods", [None, '{"items": []}'])
def test_an_unreadable_termination_is_reported_as_unobservable(
    *, tmp_path: Path, pods: str | None
) -> None:
    outcome, _ = _dispatch(tmp_path=tmp_path, pods=pods)

    record = asdict(outcome)
    assert "termination unobservable" in record["detail"]
    assert record["sandbox_termination"]["observed"] is False
    assert record["fabro_failure_category"] == "transient_infra"
    assert record["fabro_failure_signature"] == _SIGNATURE
