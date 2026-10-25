"""Reconcile a typed plan pointer and decide whether resume asks or acts.

The pointer's required result is read before any continuation decision.  A
satisfied result is stale even if a factory run remains alive; an unsatisfied
result must still fit inside its original budget.  Only after those checks may
an unattended session, or an attended session carrying a current continuation
ruling, take one of the sanctioned executable kinds.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro._store_ready_dwell import utc_now_iso
from livespec_orchestrator_beads_fabro.commands._plan_next_action import (
    HUMAN_KIND,
    IMPL_KIND,
    NEXT_ACTION_METADATA_KEY,
    NONE_KIND,
    NextAction,
    ResumeDirective,
    dispatchable_action_id,
    parse_next_action,
    plan_record_metadata,
)
from livespec_orchestrator_beads_fabro.commands._plan_progress_resume import (
    evaluate_resume_progress,
)
from livespec_orchestrator_beads_fabro.commands._plan_resume_gap import (
    definition_of_done_findings,
    missing_definition_gap_directive,
)
from livespec_orchestrator_beads_fabro.commands._plan_resume_reconcile import (
    reconciled_directive,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "decide_plan_resume",
]


def decide_plan_resume(*, config: StoreConfig, epic_id: str, unattended: bool) -> ResumeDirective:
    """Decide whether this resume asks which action to take, or takes it.

    THE PROGRESS CHECK RUNS FIRST, as the clause requires in as many words: "The
    progress check MUST precede the unattended dispatch decision." It is read
    from the epic's AUTHORITY CHAIN rather than from the `next_action` pointer,
    because every sanctioned writer rewrites that pointer wholesale and a budget
    stored there is one a writer can hand itself a new value for.

    Its position ahead of the missing-Definition-of-Done pre-emption is what
    makes a plan that is BOTH expired and missing its Definition of Done report
    the expiry: settling the dispatch question first answers with the gap
    pointer and never reads the obligation at all.
    """
    progress = evaluate_resume_progress(config=config, epic_id=epic_id, now=utc_now_iso())
    record = make_beads_client(config=config).show_issue(issue_id=epic_id)
    action = parse_next_action(
        value=plan_record_metadata(record=record).get(NEXT_ACTION_METADATA_KEY)
    )
    findings = (
        *definition_of_done_findings(record=record, epic_id=epic_id),
        *progress.findings,
    )
    if not progress.dispatch:
        return ResumeDirective(
            ask=False,
            next_action=progress.authorized_action,
            reason=progress.reason or "plan progress withholds dispatch",
            findings=findings,
        )
    if definition_of_done_findings(record=record, epic_id=epic_id) and (
        unattended and not _is_impl(action=action)
    ):
        return missing_definition_gap_directive(
            config=config,
            epic_id=epic_id,
            findings=findings,
        )
    if action is None:
        return ResumeDirective(
            ask=True,
            next_action=None,
            reason=f"epic {epic_id} carries no typed next_action",
            findings=findings,
        )
    identifier = dispatchable_action_id(action=action)
    if identifier is None:
        return ResumeDirective(
            ask=True,
            next_action=None,
            reason=_picker_reason(action=action),
            findings=findings,
        )
    return reconciled_directive(
        config=config,
        epic_id=epic_id,
        unattended=unattended,
        action=action,
        identifier=identifier,
        findings=findings,
    )


def _is_impl(*, action: NextAction | None) -> bool:
    """Whether the existing pointer is the one the gap must NOT overwrite.

    `impl` ALONE, as the clause words it. A `spec-op` pointer is dispatchable and
    is still replaced, because a plan that has not said what done means has
    nothing for a spec operation to ratify toward — whereas an `impl` pointer
    names work already filed, groomed and admitted, and overwriting it would
    strand a live dispatch behind a question nobody is present to answer.
    """
    return action is not None and action.kind == IMPL_KIND


def _picker_reason(*, action: NextAction) -> str:
    if action.kind in (HUMAN_KIND, NONE_KIND):
        return f"next_action kind {action.kind} raises the picker"
    if action.ref.strip() == "":
        return f"next_action kind {action.kind} carries an empty ref"
    return f"next_action kind {action.kind} raises the picker"
