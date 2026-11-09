"""What a merge wait whose poll budget ran out earns, after one final read of the pull request.

Split out of `_dispatcher_engine_merge` by cohesion once the handoff joined the
two endings that function already chose between: the poll loop decides WHEN to
stop, and this decides what a stop MEANS.

MERGED proceeds as a merge observed within the budget. An OPEN pull request not
in conflict is one of two endings, told apart by whether the forge is still
going to merge it:

- armed, with no required check failed -> HANDED OFF (Scenario 220). The wait
  ends without resting the item, because the pull request is going to merge by
  itself and the budget was only shorter than its CI. Every required check is
  passing or still running, and the ones still running are named.
- anything else -- auto-merge no longer armed, or the required checks cannot be
  read -> RESTED at `blocked / needs-human` with the cause
  `merge-poll-budget-exhausted`, so no claim is left `active` over a run that
  nothing will ever complete.

A required check that failed terminally between the last poll and the final read
is the ordinary required-check failure, recorded exactly as the poll records it.
Anything else -- conflicting, closed, unreadable -- keeps the existing failed
outcome, which is the clause's silence rather than a ruling.

THE FIRST READ OMITS THE STATUS-CHECK ROLLUP, as the access-denied confirmation
does: the state and mergeability are all it decides on. The rollup and the
forge's required-check answer are read only for a pull request that could be
handed off, so the ending that rests the item spends no extra call.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_base_advance import (
    MERGE_POLL_BUDGET_EXHAUSTED,
    BaseAdvancedAfterArming,
    merge_poll_budget_exhausted_detail,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_merge_wait_handoff import (
    HANDED_OFF_STATUS,
    MergeWaitHandedOff,
    merge_wait_handed_off_detail,
    merge_wait_handed_off_journal_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan, PrView
from livespec_orchestrator_beads_fabro.commands._dispatcher_pr_view import view_pr
from livespec_orchestrator_beads_fabro.commands._dispatcher_required_checks import (
    required_check_failure_outcome,
    required_check_names,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
        CommandRunner,
        DispatchOutcome,
        JournalWriter,
    )

__all__: list[str] = ["exhausted_rest_outcome", "outcome_at_exhaustion"]

_CONFLICTING = "DIRTY"


def outcome_at_exhaustion(  # noqa: PLR0913 — kw-only disposition; each field is an independent caller input.
    *,
    outcome_type: type[DispatchOutcome],
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    pr_number: int,
    run_id: str | None,
    waited_seconds: int,
) -> PrView | DispatchOutcome:
    """The merged view, or the one outcome an exhausted budget earns."""
    view = view_pr(plan=plan, runner=runner, journal=journal, include_status_checks=False).view
    if view is not None and view.state == "MERGED":
        return view
    if view is not None and view.state == "OPEN" and view.merge_state_status != _CONFLICTING:
        if view.auto_merge_armed:
            settled = _armed_ending(
                outcome_type=outcome_type,
                plan=plan,
                runner=runner,
                journal=journal,
                run_id=run_id,
                waited_seconds=waited_seconds,
            )
            if settled is not None:
                return settled
        return exhausted_rest_outcome(
            outcome_type=outcome_type,
            plan=plan,
            number=view.number,
            pr_head=view.head,
            default_branch_tip=view.base,
            run_id=run_id,
        )
    return outcome_type(
        work_item_id=plan.work_item_id,
        status="failed",
        stage="merge-poll",
        pr_number=pr_number,
        merge_sha=None,
        detail="PR did not reach MERGED within the poll budget",
        fabro_run_id=run_id,
    )


def exhausted_rest_outcome(
    *,
    outcome_type: type[DispatchOutcome],
    plan: DispatchPlan,
    number: int,
    pr_head: str | None,
    default_branch_tip: str | None,
    run_id: str | None,
) -> DispatchOutcome:
    """The ending that rests the item at `blocked / needs-human`, built in one place.

    ONE builder for the merge wait's own final read and for the stranded-claim
    pass that completes a handed-off wait whose pull request the forge will not
    merge, so both record the same cause, detail and measurements.
    """
    return outcome_type(
        work_item_id=plan.work_item_id,
        status="blocked",
        stage="merge-poll",
        pr_number=number,
        merge_sha=None,
        detail=merge_poll_budget_exhausted_detail(work_item_id=plan.work_item_id),
        fabro_run_id=run_id,
        base_advanced=BaseAdvancedAfterArming(
            factory=plan.fabro_factory_name,
            pr_head=pr_head,
            default_branch_tip=default_branch_tip,
            cause=MERGE_POLL_BUDGET_EXHAUSTED,
        ),
    )


def _armed_ending(
    *,
    outcome_type: type[DispatchOutcome],
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    run_id: str | None,
    waited_seconds: int,
) -> PrView | DispatchOutcome | None:
    """Hand an armed, OPEN pull request off, or say it cannot be (`None`).

    `None` is "rest the item", never "hand off anyway": a pull request whose
    rollup or required-check list cannot be read, or that stopped being armed or
    open between the two reads, is not one the forge is known to be about to merge.
    """
    seen = view_pr(plan=plan, runner=runner, journal=journal).view
    if seen is None:
        return None
    if seen.state == "MERGED":
        return seen
    if seen.state != "OPEN" or not seen.auto_merge_armed or seen.merge_state_status == _CONFLICTING:
        return None
    required = required_check_names(plan=plan, number=seen.number, runner=runner, journal=journal)
    if required is None:
        return None
    failed = [name for name in seen.terminal_check_failures if name in required]
    if failed:
        return required_check_failure_outcome(
            outcome_type=outcome_type,
            plan=plan,
            number=seen.number,
            merge_sha=seen.merge_sha,
            failed=failed,
        )
    handed_off = MergeWaitHandedOff(
        factory=plan.fabro_factory_name,
        pr_head=seen.head,
        waited_seconds=waited_seconds,
        running_checks=tuple(sorted({name for name in seen.running_checks if name in required})),
    )
    journal.append(
        record=merge_wait_handed_off_journal_record(
            work_item_id=plan.work_item_id,
            run_id=run_id,
            pr_number=seen.number,
            handed_off=handed_off,
        )
    )
    return outcome_type(
        work_item_id=plan.work_item_id,
        status=HANDED_OFF_STATUS,
        stage="merge-poll",
        pr_number=seen.number,
        merge_sha=None,
        detail=merge_wait_handed_off_detail(pr_number=seen.number, waited_seconds=waited_seconds),
        fabro_run_id=run_id,
        merge_wait_handed_off=handed_off,
    )
