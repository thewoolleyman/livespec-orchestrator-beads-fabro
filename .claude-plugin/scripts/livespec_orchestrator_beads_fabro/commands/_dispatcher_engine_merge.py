"""Merge and post-merge janitor flow for the Dispatcher engine."""

from __future__ import annotations

from typing import TYPE_CHECKING

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
        CommandResult,
        CommandRunner,
        DispatchOutcome,
        JournalWriter,
        PollPolicy,
        SleepFn,
    )

__all__: list[str] = [
    "await_merge",
    "confirm_pr",
    "failed",
    "journal_stage",
    "stalled",
]

_GH_TIMEOUT_SECONDS = 300.0

# The env-var an operator tunes the watchdog stall window with (named in
# the stalled-no-progress detail so the message is self-documenting).
_STALL_ENV_HINT = "LIVESPEC_DISPATCH_STALL_SECONDS"


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


def journal_stage(
    *,
    journal: JournalWriter,
    plan: DispatchPlan,
    stage: str,
    result: CommandResult,
) -> None:
    journal.append(
        record={
            "work_item_id": plan.work_item_id,
            "stage": stage,
            "exit_code": result.exit_code,
            "detail": _tail(text=result.stderr if result.exit_code != 0 else result.stdout),
        }
    )


def failed(
    *,
    outcome_type: type[DispatchOutcome],
    plan: DispatchPlan,
    stage: str,
    detail: str,
) -> DispatchOutcome:
    return outcome_type(
        work_item_id=plan.work_item_id,
        status="failed",
        stage=stage,
        pr_number=None,
        merge_sha=None,
        detail=detail,
    )


def stalled(
    *,
    outcome_type: type[DispatchOutcome],
    plan: DispatchPlan,
    run_id: str,
) -> DispatchOutcome:
    """The distinct `stalled-no-progress` terminal (the 7us.6 hang class).

    The coarse wall-clock watchdog confirmed sustained no progress (no new
    fabro event for the full stall window) and `fabro rm -f`-ed the run.
    This is a FAIL-CLOSED terminal — never silently treated as success: a
    distinct `status` so the loop verdict exits non-zero and h1p's
    `notify_terminal` alarms the operator with the `stalled-no-progress`
    outcome class.
    """
    return outcome_type(
        work_item_id=plan.work_item_id,
        status="stalled-no-progress",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail=(
            f"run {run_id} made no progress for the full stall window "
            f"(no new fabro event); the coarse wall-clock watchdog "
            f"`fabro rm -f`-ed it (the 7us.6 silent-deadlock class). "
            f"Set {_STALL_ENV_HINT} to tune the window; the DEFERRED 29f "
            f"OTEL metrics-heartbeat primary will refine this coarse signal."
        ),
    )


def _tail(*, text: str, limit: int = 2000) -> str:
    stripped = text.strip()
    if len(stripped) <= limit:
        return stripped
    return stripped[-limit:]
