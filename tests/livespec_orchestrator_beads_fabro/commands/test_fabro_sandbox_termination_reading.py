"""The sandbox-termination reader grades every pod shape it can be handed.

Companion of `test_dispatcher_sandbox_oom_classification.py`: that file drives the
Scenario 335 arms end to end, and this one pins the reader's edges -- which pods
are attributed to a run, which containers count as OOM-killed, and what each
unreadable shape reports.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_termination import (
    outcome_naming_sandbox_termination,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import FabroFailureDetail
from livespec_orchestrator_beads_fabro.commands._fabro_resource_exhaustion import (
    SandboxTermination,
    sandbox_termination_statement,
)
from livespec_orchestrator_beads_fabro.commands._fabro_sandbox_termination import (
    oom_reclassified_failure,
    permanent_failure_signature,
    read_sandbox_termination,
)

_RUN = "01M70P2CVG4SYMMBXGBZZSWM2W"


@dataclass(kw_only=True)
class _Kubectl:
    stdout: str

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (argv, cwd, timeout_seconds, env, stdin)
        return CommandResult(exit_code=0, stdout=self.stdout, stderr="")


def _read(*, pods: object) -> SandboxTermination:
    return read_sandbox_termination(
        runner=_Kubectl(stdout=json.dumps(pods)), cwd=Path(), run_id=_RUN
    )


def _pod(*, metadata: dict[str, Any], containers: Any, statuses: Any) -> dict[str, Any]:
    return {
        "metadata": metadata,
        "spec": {"containers": containers},
        "status": {"containerStatuses": statuses},
    }


def _killed(*, name: str = "sandbox", key: str = "state") -> dict[str, Any]:
    return {"name": name, key: {"terminated": {"reason": "OOMKilled"}}}


@pytest.mark.parametrize(
    "stdout",
    ["not json", "[]", '{"items": "no"}'],
)
def test_a_listing_that_is_not_a_pod_list_is_unobservable(*, stdout: str) -> None:
    reading = read_sandbox_termination(runner=_Kubectl(stdout=stdout), cwd=Path(), run_id=_RUN)

    assert reading.observed is False
    assert reading.oom_killed is False


def test_a_pod_is_attributed_to_the_run_by_a_label_value() -> None:
    pod = _pod(
        metadata={"name": "unrelated", "labels": {"run": _RUN, "n": 3}},
        containers=[{"name": "sandbox", "resources": {"limits": {"memory": "1Gi"}}}],
        statuses=[_killed()],
    )

    reading = _read(pods={"items": [pod, "not a pod", {"metadata": "bad"}]})

    assert reading.oom_killed is True
    assert reading.memory_limit_bytes == 1024**3


def test_a_last_state_kill_counts_and_a_kill_in_another_container_carries_its_own_limit() -> None:
    pod = _pod(
        metadata={"name": f"fabro-run-{_RUN.lower()}"},
        containers=[
            {"name": "sidecar", "resources": {"limits": {"memory": "64Mi"}}},
            {"name": "sandbox", "resources": {"limits": {"memory": 5}}},
            {"resources": {}},
            "not a container",
        ],
        statuses=[{"name": "sidecar", "state": {"running": {}}}, _killed(key="lastState")],
    )

    reading = _read(pods={"items": [pod]})

    assert reading.oom_killed is True
    assert reading.memory_limit_bytes is None


def test_a_pod_with_no_container_statuses_reports_no_kill() -> None:
    pod = _pod(metadata={"name": _RUN.lower()}, containers=[], statuses=None)
    pod["spec"] = {"containers": "not a list"}

    reading = _read(pods={"items": [pod]})

    assert reading.observed is True
    assert reading.oom_killed is False


def test_container_statuses_without_a_name_are_skipped() -> None:
    pod = _pod(
        metadata={"name": _RUN.lower()}, containers=[], statuses=[{"state": {}}, "not a status"]
    )

    assert _read(pods={"items": [pod]}).oom_killed is False


def test_an_oom_failure_with_no_recorded_failure_is_still_permanent() -> None:
    termination = SandboxTermination(
        run_id=_RUN, observed=True, oom_killed=True, memory_limit_bytes=7, detail="read"
    )

    failure = oom_reclassified_failure(failure=None, termination=termination)

    assert failure is not None
    assert failure.category == "deterministic"
    assert failure.signature is None
    assert failure.resource_exhaustion is not None
    assert failure.resource_exhaustion.memory_limit_bytes == 7
    assert failure.provider_usage_limit is False


def test_a_failure_with_no_signature_stays_without_one() -> None:
    termination = SandboxTermination(
        run_id=_RUN, observed=True, oom_killed=True, memory_limit_bytes=None, detail="read"
    )
    arrived = FabroFailureDetail(cause="x", category="transient_infra", signature=None)

    failure = oom_reclassified_failure(failure=arrived, termination=termination)

    assert failure is not None
    assert failure.signature is None
    assert permanent_failure_signature(signature=None) is None


def test_a_reading_that_shows_no_kill_returns_the_failure_as_it_arrived() -> None:
    arrived = FabroFailureDetail(
        cause="x", category="transient_infra", signature="a|transient_infra|b"
    )
    clean = SandboxTermination(
        run_id=_RUN, observed=True, oom_killed=False, memory_limit_bytes=None, detail="read"
    )

    assert oom_reclassified_failure(failure=arrived, termination=clean) is arrived
    assert sandbox_termination_statement(termination=clean) is None


def test_the_statement_names_the_run_and_the_limit_or_its_absence() -> None:
    killed = SandboxTermination(
        run_id=_RUN, observed=True, oom_killed=True, memory_limit_bytes=None, detail="read"
    )

    assert sandbox_termination_statement(termination=killed) == (
        f"sandbox OOM-killed: run {_RUN} container memory limit unobservable"
    )


def test_an_outcome_with_no_detail_carries_the_statement_alone() -> None:
    outcome = DispatchOutcome(
        work_item_id="bd-ib-jnstxo",
        status="failed",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail="",
        fabro_failure_category="transient_infra",
    )
    unobserved = SandboxTermination(
        run_id=_RUN, observed=False, oom_killed=False, memory_limit_bytes=None, detail="gone"
    )

    from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroInspectResult

    inspect = FabroInspectResult(
        command=CommandResult(exit_code=0, stdout="", stderr=""),
        payload=None,
        status_kind="failed",
        failure=None,
        sandbox_termination=unobserved,
    )

    named = outcome_naming_sandbox_termination(outcome=outcome, inspect=inspect)

    assert named.detail == f"sandbox termination unobservable for run {_RUN}: gone"
    assert named.fabro_failure_category == "transient_infra"
    assert outcome_naming_sandbox_termination(outcome=outcome, inspect=None) is outcome
