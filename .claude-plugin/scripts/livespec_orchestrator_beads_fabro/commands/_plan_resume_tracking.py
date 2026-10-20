"""Required-result and budget reconciliation for a typed plan pointer.

Every TERMINAL tracking finding lives here — a legacy pointer carrying no
obligation, an unobservable result, and an expired budget — and returning `None`
is what permits bounded continuation. The SATISFIED finding is deliberately NOT
here: it is the one arm that DERIVES AND PERSISTS a replacement pointer, which
`_plan_resume_advance` owns, and its caller checks it first so that this module
is reached only once staleness has been ruled out.

IT ALSO OWNS THE ONE READ ALL THREE FINDINGS REST ON, and that read resolves an
obligation naming THE PLAN EPIC ITSELF against the plan's own tenant whatever
repository the recorded pointer names. A plan-level leg targets the epic, and the
epic lives in the plan's own tenant, so a recorded foreign repository makes the
read fail — and an unobservable obligation withholds dispatch while being
unreplaceable by design, so one stale `repo` field locks a plan for its whole
budget. `_plan_resume_advance` stops new pointers acquiring that field; this is
what unlocks the plans whose pointers already carry it.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from livespec_orchestrator_beads_fabro._store_ready_dwell import utc_now_iso
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._plan_continuation import instant_expired
from livespec_orchestrator_beads_fabro.commands._plan_next_action import (
    ARCHIVE_KIND,
    LEGACY_TRACKING,
    PROOF_KIND,
    REVIEW_KIND,
    NextAction,
    ResumeDirective,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_observation import (
    OBSERVATION_UNSATISFIED,
    ResultObservation,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_reader import read_result
from livespec_orchestrator_beads_fabro.commands._plan_result_reference import REPO_FIELD
from livespec_orchestrator_beads_fabro.commands._plan_result_repository import (
    project_repository_identity,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_targets import (
    ITEM_COMMENT_KIND,
    ITEM_STATUS_KIND,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "result_observation",
    "tracked_resume_directive",
]

# The three legs whose target is the plan epic itself. An `impl` pointer names a
# CHILD, and a child legitimately lives in another tenant under the cross-tenant
# execution mirror, so widening this set would redirect a read the recorded
# repository is right about.
_PLAN_LEVEL_KINDS: tuple[str, ...] = (PROOF_KIND, REVIEW_KIND, ARCHIVE_KIND)
# The two target kinds a plan-level leg's own obligation is ever written as: a
# comment on the epic for the proof and review legs, and the epic's closed status
# for the archive leg.
_ITEM_TARGET_KINDS: tuple[str, ...] = (ITEM_COMMENT_KIND, ITEM_STATUS_KIND)
_ITEM_ID_FIELD = "item_id"


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
        reference=_plan_owned_reference(config=config, epic_id=epic_id, action=action),
        runner=ShellCommandRunner(),
    )


def _plan_owned_reference(*, config: StoreConfig, epic_id: str, action: NextAction) -> object:
    """The reference to READ: the recorded one, or its plan-owned repository.

    The rewrite is a READ-TIME redirect and persists nothing, which is the right
    division: the recorded pointer is replaced by the ordinary advance once this
    obligation is satisfied, and rewriting it here would be an unsanctioned write
    on a path whose whole job is to observe.

    It is NARROW in both directions it could be wrong. A leg whose target is NOT
    the epic is left alone, because an `impl` child's recorded repository is a
    fact about where that child was filed. And the identity is not compared
    before substituting, because an obligation already naming the plan's own
    repository rewrites to the value it holds.
    """
    if action.kind not in _PLAN_LEVEL_KINDS or not _names_epic(
        required_result=action.required_result, epic_id=epic_id
    ):
        return action.required_result
    recorded = cast("dict[str, Any]", action.required_result)
    return {**recorded, REPO_FIELD: project_repository_identity(config=config)}


def _names_epic(*, required_result: object, epic_id: str) -> bool:
    """Whether a recorded obligation's own target is the plan epic itself.

    Read off the RAW value rather than through the typed parse, because a
    reference the parse refuses is one `read_result` must report its own refusal
    for — so a parse here would either duplicate that ladder or decide a redirect
    on a target the reader never admitted.
    """
    fields = cast("dict[str, Any]", required_result) if isinstance(required_result, dict) else {}
    return any(
        isinstance(target, dict) and cast("dict[str, Any]", target).get(_ITEM_ID_FIELD) == epic_id
        for target in (fields.get(kind) for kind in _ITEM_TARGET_KINDS)
    )


def _budget_unexpired(*, budget: object) -> bool:
    fields = cast("dict[str, Any]", budget)
    deadline = cast("str", fields["deadline"])
    maximum = cast("int", fields["max_handoffs"])
    count = cast("int", fields.get("handoff_count", 0))
    if count >= maximum:
        return False
    return not instant_expired(until=deadline, now=utc_now_iso())
