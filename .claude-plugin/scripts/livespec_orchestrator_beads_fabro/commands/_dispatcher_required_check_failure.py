"""Terminal required-check recovery during merge polling.

This module owns the one bounded failed-jobs rerun decision.  The merge engine
continues to own polling and all non-required-check merge outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_failed_jobs_rerun import (
    attempt_failed_jobs_rerun,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_required_checks import (
    required_check_names,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
        CommandRunner,
        DispatchOutcome,
        JournalWriter,
    )
    from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan, PrView

__all__: list[str] = [
    "RequiredCheckFailureContext",
    "RerunPollState",
    "required_check_failure",
]


@dataclass(frozen=True, kw_only=True)
class RequiredCheckFailureContext:
    """Dependencies shared by every required-check decision in one merge wait."""

    outcome_type: type[DispatchOutcome]
    plan: DispatchPlan
    runner: CommandRunner
    journal: JournalWriter


@dataclass(kw_only=True)
class RerunPollState:
    """One pull request head's consumed automatic failed-jobs rerun."""

    workflow_ids: set[str]


def required_check_failure(
    *,
    context: RequiredCheckFailureContext,
    view: PrView | None,
    rerun_state: RerunPollState,
    may_keep_polling: bool,
) -> DispatchOutcome | None:
    """Recover one classified failure or return the ordinary blocked outcome."""
    if view is None or not view.terminal_check_failures:
        return None
    required = required_check_names(
        plan=context.plan,
        number=view.number,
        runner=context.runner,
        journal=context.journal,
    )
    if required is None:
        return None
    failed = [name for name in view.terminal_check_failures if name in required]
    if not failed:
        return None
    if rerun_state.workflow_ids:
        return _terminal_required_check_outcome(
            context=context,
            view=view,
            failed=failed,
        )
    rerun = (
        attempt_failed_jobs_rerun(
            failed_check_names=failed,
            failures=view.terminal_check_failure_details,
            plan=context.plan,
            pr_number=view.number,
            runner=context.runner,
            journal=context.journal,
        )
        if may_keep_polling
        else None
    )
    if rerun is not None:
        rerun_state.workflow_ids.add(rerun.workflow_run)
    if rerun is not None and rerun.requested:
        return None
    return _terminal_required_check_outcome(
        context=context,
        view=view,
        failed=failed,
    )


def _terminal_required_check_outcome(
    *,
    context: RequiredCheckFailureContext,
    view: PrView,
    failed: list[str],
) -> DispatchOutcome:
    """Return the ordinary blocked outcome and journal the terminal attempt."""
    context.journal.append(
        record={
            "work_item_id": context.plan.work_item_id,
            "stage": "merge-poll-failed-jobs-rerun",
            "outcome": "required-check-failed" if failed else "not-requested",
        }
    )
    return context.outcome_type(
        work_item_id=context.plan.work_item_id,
        status="blocked",
        stage="merge-poll",
        pr_number=view.number,
        merge_sha=view.merge_sha,
        detail=(
            f"required check failed terminally: {', '.join(failed)}; the factory run "
            "succeeded but its pull request cannot merge. Recover with "
            f"`resolve-blocked:{context.plan.work_item_id}:ready`, then "
            f"`resume --item {context.plan.work_item_id}`, which checks out the pull request's "
            "published head for rework."
        ),
    )
