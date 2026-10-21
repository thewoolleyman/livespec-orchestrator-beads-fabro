"""Merge and post-merge janitor flow for the Dispatcher engine."""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_base_advance import (
    CONSECUTIVE_CONFLICTING_REPORTS,
    BaseAdvancedAfterArming,
    base_advanced_detail,
    reports_base_advanced_after_arming,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_confirm import confirm_pr
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_janitor import post_merge
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_journal import journal_stage
from livespec_orchestrator_beads_fabro.commands._dispatcher_merge_pr_association import (
    pr_view_for_merge_sha,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
    PrView,
    pr_update_branch_argv,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_pr_view import (
    GH_TIMEOUT_SECONDS,
    view_pr,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
        CommandRunner,
        DispatchOutcome,
        JournalWriter,
        PollPolicy,
        SleepFn,
    )

__all__: list[str] = ["await_merge", "confirm_pr", "outcome_after_await"]


def await_merge(
    *,
    outcome_type: type[DispatchOutcome],
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    sleep: SleepFn,
    poll: PollPolicy,
) -> PrView | DispatchOutcome | None:
    # The streak of CONSECUTIVE polls that reported an armed, OPEN pull request
    # conflicting with the default branch. Reset by any poll that reported
    # otherwise AND by any poll whose view could not be read, per
    # `_dispatcher_base_advance`'s own rule that an absent reading is not a
    # report in either direction.
    conflicting_reports = 0
    for attempt in range(poll.attempts):
        reading = view_pr(
            plan=plan,
            runner=runner,
            journal=journal,
        )
        view = reading.view if reading.error is None else None
        if view is not None and view.state == "MERGED":
            return view
        if _is_integration_access_denied(error=reading.error):
            # Polling an OPEN PR must keep its rollup: terminal required-check
            # failures are a fast failure, not a poll timeout. A credential may
            # nevertheless be unable to read that rollup AFTER GitHub merged the
            # PR, so use the confirmation-shaped read only to establish MERGED.
            merged_reading = view_pr(
                plan=plan,
                runner=runner,
                journal=journal,
                include_status_checks=False,
            )
            merged_view = merged_reading.view
            if merged_view is not None and merged_view.state == "MERGED":
                return merged_view
        if view is not None and _reports_overtaken_arming(view=view):
            conflicting_reports += 1
            if conflicting_reports >= CONSECUTIVE_CONFLICTING_REPORTS:
                return outcome_type(
                    work_item_id=plan.work_item_id,
                    status="blocked",
                    stage="merge-poll",
                    pr_number=view.number,
                    merge_sha=None,
                    detail=base_advanced_detail(work_item_id=plan.work_item_id),
                    base_advanced=BaseAdvancedAfterArming(
                        factory=plan.fabro_factory_name,
                        pr_head=view.head,
                        default_branch_tip=view.base,
                    ),
                )
        else:
            conflicting_reports = 0
        if view is not None and view.merge_state_status == "BEHIND":
            update = runner.run(
                argv=pr_update_branch_argv(plan=plan, number=view.number),
                cwd=plan.repo,
                timeout_seconds=GH_TIMEOUT_SECONDS,
            )
            journal_stage(journal=journal, plan=plan, stage="pr-update-branch", result=update)
        elif view is not None and view.terminal_required_check_failures:
            checks = ", ".join(view.terminal_required_check_failures)
            return outcome_type(
                work_item_id=plan.work_item_id,
                status="failed",
                stage="merge-poll",
                pr_number=view.number,
                merge_sha=view.merge_sha,
                detail=f"required check failed terminally: {checks}",
            )
        if attempt + 1 < poll.attempts:
            sleep(poll.interval_seconds)
    return None


def outcome_after_await(  # noqa: PLR0913 — kw-only disposition; each field is an independent caller input.
    *,
    outcome_type: type[DispatchOutcome],
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    merged: PrView | DispatchOutcome | None,
    pr_number: int,
    run_id: str | None,
) -> DispatchOutcome:
    """One terminal outcome from `await_merge`'s three-way answer.

    The poll reports a MERGED view, a terminal failure it already decided (a
    required check that failed for good), or an exhausted budget, and each is a
    different outcome. It lives beside the poll rather than inside `run_dispatch`
    so that function stays one readable list of stages rather than a stage list
    with a disposition tree hanging off its end.
    """
    # Discriminated on `PrView` rather than on `outcome_type`, which is a
    # runtime PARAMETER and so narrows nothing for the reader or the checker.
    if isinstance(merged, PrView):
        return post_merge(
            outcome_type=outcome_type,
            plan=plan,
            runner=runner,
            journal=journal,
            merged=pr_view_for_merge_sha(
                repo=plan.repo,
                work_item_id=plan.work_item_id,
                merged=merged,
                runner=runner,
                journal=journal,
            ),
        )
    if merged is None:
        return outcome_type(
            work_item_id=plan.work_item_id,
            status="failed",
            stage="merge-poll",
            pr_number=pr_number,
            merge_sha=None,
            detail="PR did not reach MERGED within the poll budget",
            fabro_run_id=run_id,
        )
    return merged


def _reports_overtaken_arming(*, view: PrView) -> bool:
    """One poll's reading, routed through the pure decision that owns the rule."""
    return reports_base_advanced_after_arming(
        state=view.state,
        auto_merge_armed=view.auto_merge_armed,
        merge_state_status=view.merge_state_status,
    )


def _is_integration_access_denied(*, error: str | None) -> bool:
    """Recognize GitHub App authorization denial without retrying transient reads."""
    return error is not None and "resource not accessible by integration" in error.lower()
