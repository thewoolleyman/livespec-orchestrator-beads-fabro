"""Required-result and budget reconciliation for a typed plan pointer."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from livespec_orchestrator_beads_fabro._store_ready_dwell import utc_now_iso
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._plan_continuation import instant_expired
from livespec_orchestrator_beads_fabro.commands._plan_next_action import (
    LEGACY_TRACKING,
    NextAction,
    ResumeDirective,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_observation import (
    OBSERVATION_SATISFIED,
    OBSERVATION_UNSATISFIED,
    ResultObservation,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_reader import read_result

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "result_observation",
    "tracked_resume_directive",
]


def tracked_resume_directive(
    *,
    action: NextAction,
    observation: ResultObservation | None,
    findings: tuple[str, ...],
) -> ResumeDirective | None:
    """Return a terminal tracking directive, or permit bounded continuation."""
    if observation is not None and observation.status == OBSERVATION_SATISFIED:
        finding = (
            f"next_action stale: observed {observation.target} satisfied via"
            f" {observation.evidence}; derive the next step from the ledger"
        )
        return ResumeDirective(
            ask=False,
            next_action=None,
            reason=finding,
            findings=(*findings, finding),
            observation=observation,
        )
    if observation is not None and observation.status != OBSERVATION_UNSATISFIED:
        finding = f"next_action result is unobservable: {observation.detail}"
        return ResumeDirective(
            ask=False,
            next_action=None,
            reason=finding,
            findings=(*findings, finding),
            observation=observation,
        )
    if observation is None or _budget_unexpired(budget=action.budget):
        return None
    finding = f"next_action obligation expired after observing {observation.target}"
    return ResumeDirective(
        ask=False,
        next_action=None,
        reason=finding,
        findings=(*findings, finding),
        observation=observation,
    )


def result_observation(*, config: StoreConfig, action: NextAction) -> ResultObservation | None:
    """Read an explicitly tracked pointer; legacy pointers retain their old path."""
    if action.required_result is LEGACY_TRACKING or action.required_result is None:
        return None
    project_root = config.repo_root if config.repo_root is not None else Path.cwd()
    return read_result(
        project_root=project_root,
        reference=action.required_result,
        runner=ShellCommandRunner(),
    )


def _budget_unexpired(*, budget: object) -> bool:
    fields = cast("dict[str, Any]", budget)
    deadline = cast("str", fields["deadline"])
    maximum = cast("int", fields["max_handoffs"])
    count = cast("int", fields.get("handoff_count", 0))
    if count >= maximum:
        return False
    return not instant_expired(until=deadline, now=utc_now_iso())
