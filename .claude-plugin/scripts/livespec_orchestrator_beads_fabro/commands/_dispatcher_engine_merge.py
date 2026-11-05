"""Merge and post-merge janitor flow for the Dispatcher engine."""

from __future__ import annotations

from dataclasses import dataclass
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_failed_jobs_rerun import (
    attempt_failed_jobs_rerun,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_merge_outcome import (
    outcome_at_exhaustion,
)
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_required_checks import (
    required_check_names,
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


@dataclass(kw_only=True)
class _RerunPollState:
    """One poll's permission and history for bounded failed-jobs recovery."""

    workflow_ids: set[str]
    may_keep_polling: bool


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
    rerun_workflow_ids: set[str] = set()
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
        elif (
            failure := _required_check_failure(
                outcome_type=outcome_type,
                view=view,
                plan=plan,
                runner=runner,
                journal=journal,
                rerun_state=_RerunPollState(
                    workflow_ids=rerun_workflow_ids,
                    may_keep_polling=attempt + 1 < poll.attempts,
                ),
            )
        ) is not None:
            return failure
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
    if merged is None:
        merged = outcome_at_exhaustion(
            outcome_type=outcome_type,
            plan=plan,
            runner=runner,
            journal=journal,
            pr_number=pr_number,
            run_id=run_id,
        )
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
    return merged


def _required_check_failure(
    *,
    outcome_type: type[DispatchOutcome],
    view: PrView | None,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    rerun_state: _RerunPollState,
) -> DispatchOutcome | None:
    """The terminal outcome when a check the forge reports as required has failed for good.

    The forge is asked only once something has already failed, so a green poll
    spends no extra call. An unreadable answer is no answer: the poll continues.
    """
    if view is None or not view.terminal_check_failures:
        return None
    required = required_check_names(
        plan=plan,
        number=view.number,
        runner=runner,
        journal=journal,
    )
    if required is None:
        return None
    failed = [name for name in view.terminal_check_failures if name in required]
    if not failed:
        return None
    if rerun_state.workflow_ids:
        return _terminal_required_check_outcome(
            outcome_type=outcome_type,
            plan=plan,
            view=view,
            failed=failed,
            journal=journal,
        )
    rerun = (
        attempt_failed_jobs_rerun(
            failed_check_names=failed,
            failures=view.terminal_check_failure_details,
            plan=plan,
            pr_number=view.number,
            runner=runner,
            journal=journal,
        )
        if rerun_state.may_keep_polling
        else None
    )
    if rerun is not None:
        rerun_state.workflow_ids.add(rerun.workflow_run)
    if rerun is not None and rerun.requested:
        return None
    return _terminal_required_check_outcome(
        outcome_type=outcome_type,
        plan=plan,
        view=view,
        failed=failed,
        journal=journal,
    )


def _terminal_required_check_outcome(
    *,
    outcome_type: type[DispatchOutcome],
    plan: DispatchPlan,
    view: PrView,
    failed: list[str],
    journal: JournalWriter,
) -> DispatchOutcome:
    """Return the ordinary blocked outcome, recording a re-run attempt verdict."""
    journal.append(
        record={
            "work_item_id": plan.work_item_id,
            "stage": "merge-poll-failed-jobs-rerun",
            "outcome": "required-check-failed" if failed else "not-requested",
        }
    )
    return outcome_type(
        work_item_id=plan.work_item_id,
        status="blocked",
        stage="merge-poll",
        pr_number=view.number,
        merge_sha=view.merge_sha,
        detail=(
            f"required check failed terminally: {', '.join(failed)}; the factory run "
            "succeeded but its pull request cannot merge. Recover with "
            f"`resolve-blocked:{plan.work_item_id}:ready`, then "
            f"`resume --item {plan.work_item_id}`, which checks out the pull request's "
            "published head for rework."
        ),
    )


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
