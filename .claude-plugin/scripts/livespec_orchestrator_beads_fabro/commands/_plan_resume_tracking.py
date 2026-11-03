"""Required-result and budget reconciliation for a typed plan pointer.

Every TERMINAL tracking finding lives here — a legacy pointer carrying no
obligation, and an unobservable result — and returning `None` is what permits
continuation. A passed deadline or an exhausted handoff count is deliberately
NOT one of them: the budget is a reporting datum only, and the expiry finding
that once stopped the resume here was deleted on the maintainer's 2026-11-03
ruling. The SATISFIED finding is deliberately NOT
here: it is the one arm that DERIVES AND PERSISTS a replacement pointer, which
`_plan_resume_advance` owns, and its caller checks it first so that this module
is reached only once staleness has been ruled out.

IT ALSO OWNS THE ONE READ ALL THREE FINDINGS REST ON, and that read goes through
`_plan_result_plan_owned.read_plan_owned_result` rather than reaching
`read_result` directly, so an obligation naming THE PLAN EPIC ITSELF resolves
against the plan's own tenant whatever repository the recorded pointer names.
That module carries the measurement and the reason the reader is shared rather
than local: one plan-level obligation is read three times on the way through a
single resume — the authority CHAIN first, this pointer second, and the
sanctioned write's own prior-obligation reading third — and settling it at any
subset of them leaves the plan stopped, so the redirect belongs to the READER
every one of them calls rather than to any of the call sites.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

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
    read_plan_owned_result,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "result_observation",
    "tracked_resume_directive",
]


def tracked_resume_directive(
    *,
    observation: ResultObservation | None,
    findings: tuple[str, ...],
) -> ResumeDirective | None:
    """Return a terminal tracking directive, or permit continuation.

    PURE over the pointer and its already-taken observation. It reads no store
    and asks no factory, which is what makes the findings it renders
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
    return None


def result_observation(
    *, config: StoreConfig, epic_id: str, action: NextAction
) -> ResultObservation | None:
    """Read an explicitly tracked pointer; legacy pointers retain their old path."""
    if action.required_result is LEGACY_TRACKING or action.required_result is None:
        return None
    return read_plan_owned_result(
        config=config, epic_id=epic_id, required_result=action.required_result
    )
