"""Required-result and budget reconciliation for a typed plan pointer.

Every TERMINAL tracking finding lives here — a legacy pointer carrying no
obligation, an unobservable result, and an expired budget — and returning `None`
is what permits bounded continuation. The SATISFIED finding is deliberately NOT
here: it is the one arm that DERIVES AND PERSISTS a replacement pointer, which
`_plan_resume_advance` owns, and its caller checks it first so that this module
is reached only once staleness has been ruled out.

IT ALSO OWNS THE ONE READ ALL THREE FINDINGS REST ON, and that read takes the
SHARED plan-owned redirect of `_plan_result_plan_owned`, so an obligation naming
THE PLAN EPIC ITSELF resolves against the plan's own tenant whatever repository
the recorded pointer names. That module carries the measurement and the reason
the redirect is shared rather than local: the resume reads the obligation from
the authority CHAIN first and returns on that verdict, so a redirect living in
this module alone is unreachable for every chain-tracked plan — which is every
plan the progress gate can lock.
"""

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
    OBSERVATION_UNSATISFIED,
    ResultObservation,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_plan_owned import (
    plan_owned_reference,
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
    """Return a terminal tracking directive, or permit bounded continuation.

    PURE over the pointer and its already-taken observation. It reads no store
    and asks no factory, which is what makes the three findings it renders
    exercisable across every state without a double for either.
    """
    if observation is None:
        finding = "plan-progress-tracking: missing — pointer carries no required_result and budget"
        return ResumeDirective(
            ask=False,
            next_action=None,
            reason=finding,
            findings=(*findings, finding),
        )
    if observation.status != OBSERVATION_UNSATISFIED:
        finding = f"next_action result is unobservable: {observation.detail}"
        return ResumeDirective(
            ask=False,
            next_action=None,
            reason=finding,
            findings=(*findings, finding),
            observation=observation,
        )
    if _budget_unexpired(budget=action.budget):
        return None
    finding = f"next_action obligation expired after observing {observation.target}"
    return ResumeDirective(
        ask=False,
        next_action=None,
        reason=finding,
        findings=(*findings, finding),
        observation=observation,
    )


def result_observation(
    *, config: StoreConfig, epic_id: str, action: NextAction
) -> ResultObservation | None:
    """Read an explicitly tracked pointer; legacy pointers retain their old path."""
    if action.required_result is LEGACY_TRACKING or action.required_result is None:
        return None
    project_root = config.repo_root if config.repo_root is not None else Path.cwd()
    return read_result(
        project_root=project_root,
        reference=plan_owned_reference(
            config=config, epic_id=epic_id, required_result=action.required_result
        ),
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
