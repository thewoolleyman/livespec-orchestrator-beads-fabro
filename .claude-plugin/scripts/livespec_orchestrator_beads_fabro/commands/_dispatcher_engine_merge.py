"""Merge and post-merge janitor flow for the Dispatcher engine."""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_journal import journal_stage
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
    PrView,
    parse_pr_view,
    pr_arm_argv,
    pr_update_branch_argv,
    pr_view_argv,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
        CommandRunner,
        DispatchOutcome,
        JournalWriter,
        PollPolicy,
        SleepFn,
    )

__all__: list[str] = ["await_merge", "confirm_pr"]

_GH_TIMEOUT_SECONDS = 300.0


def confirm_pr(
    *,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
) -> PrView | None:
    view = _view_pr(plan=plan, runner=runner, journal=journal)
    if view is None:
        return None
    if view.auto_merge_armed or view.state == "MERGED":
        return view
    arm = runner.run(
        argv=pr_arm_argv(plan=plan, number=view.number),
        cwd=plan.repo,
        timeout_seconds=_GH_TIMEOUT_SECONDS,
    )
    journal_stage(journal=journal, plan=plan, stage="pr-arm-fallback", result=arm)
    return _view_pr(plan=plan, runner=runner, journal=journal)


def await_merge(
    *,
    outcome_type: type[DispatchOutcome],
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    sleep: SleepFn,
    poll: PollPolicy,
) -> PrView | DispatchOutcome | None:
    for attempt in range(poll.attempts):
        view = _view_pr(plan=plan, runner=runner, journal=journal)
        if view is not None and view.state == "MERGED":
            return view
        if view is not None and view.merge_state_status == "BEHIND":
            update = runner.run(
                argv=pr_update_branch_argv(plan=plan, number=view.number),
                cwd=plan.repo,
                timeout_seconds=_GH_TIMEOUT_SECONDS,
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


def _view_pr(
    *,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
) -> PrView | None:
    result = runner.run(
        argv=pr_view_argv(plan=plan),
        cwd=plan.repo,
        timeout_seconds=_GH_TIMEOUT_SECONDS,
    )
    journal_stage(journal=journal, plan=plan, stage="pr-view", result=result)
    if result.exit_code != 0:
        return None
    return parse_pr_view(stdout=result.stdout)
