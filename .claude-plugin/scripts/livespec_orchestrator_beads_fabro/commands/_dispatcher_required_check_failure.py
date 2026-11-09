"""Terminal required-check recovery during merge polling.

This module owns the one bounded failed-jobs rerun decision.  The merge engine
continues to own polling and all non-required-check merge outcomes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_journal import journal_stage
from livespec_orchestrator_beads_fabro.commands._dispatcher_failed_jobs_rerun import (
    FailedRequiredChecks,
    attempt_failed_jobs_rerun,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_journal_file import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_pr_view import GH_TIMEOUT_SECONDS
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection_journal import (
    read_journal_records,
)
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
    from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan, PrView

__all__: list[str] = [
    "RequiredCheckFailureContext",
    "RerunPollState",
    "journal_rerun_merged",
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
    """The one automatic failed-jobs rerun this merge wait has requested, by run attempt."""

    attempts_before_rerun: dict[str, int]


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
    if rerun_state.attempts_before_rerun:
        return _outcome_after_rerun(
            context=context, view=view, failed=failed, rerun_state=rerun_state
        )
    rerun = (
        attempt_failed_jobs_rerun(
            failed=FailedRequiredChecks(
                names=failed,
                failures=view.terminal_check_failure_details,
                pr_number=view.number,
                pr_head=view.head,
            ),
            plan=context.plan,
            runner=context.runner,
            journal=context.journal,
        )
        if may_keep_polling and not _head_already_rerun(context=context, head=view.head)
        else None
    )
    if rerun is not None and rerun.requested:
        rerun_state.attempts_before_rerun[rerun.workflow_run] = rerun.prior_attempt
        return None
    return _blocked_outcome(context=context, view=view, failed=failed)


def _head_already_rerun(*, context: RequiredCheckFailureContext, head: str | None) -> bool:
    """Whether the durable journal already records an automatic rerun for this pull request head."""
    journal = context.journal
    if head is None or not isinstance(journal, JournalFile):
        return False
    return any(
        record.get("stage") == "merge-poll-failed-jobs-rerun"
        and record.get("work_item_id") == context.plan.work_item_id
        and record.get("pr_head") == head
        for record in read_journal_records(journal_path=journal.path)
    )


def _outcome_after_rerun(
    *,
    context: RequiredCheckFailureContext,
    view: PrView,
    failed: list[str],
    rerun_state: RerunPollState,
) -> DispatchOutcome | None:
    """Judge only the re-run attempt: the forge keeps reporting the re-run one until replaced."""
    if not _rerun_attempt_reported(context=context, rerun_state=rerun_state):
        return None
    for workflow_run in rerun_state.attempts_before_rerun:
        context.journal.append(
            record={
                "work_item_id": context.plan.work_item_id,
                "stage": "merge-poll-failed-jobs-rerun",
                "workflow_run": workflow_run,
                "outcome": "required-check-failed",
                "failed_checks": failed,
            }
        )
    return _blocked_outcome(context=context, view=view, failed=failed)


def journal_rerun_merged(
    *, context: RequiredCheckFailureContext, rerun_state: RerunPollState
) -> None:
    """Journal that the re-run attempt reached a merge, against the rerun's workflow run."""
    for workflow_run in rerun_state.attempts_before_rerun:
        context.journal.append(
            record={
                "work_item_id": context.plan.work_item_id,
                "stage": "merge-poll-failed-jobs-rerun",
                "workflow_run": workflow_run,
                "outcome": "merged",
            }
        )


def _rerun_attempt_reported(
    *, context: RequiredCheckFailureContext, rerun_state: RerunPollState
) -> bool:
    """Whether every re-run workflow run now reports a higher run attempt than it had."""
    for workflow_run, prior_attempt in rerun_state.attempts_before_rerun.items():
        result = context.runner.run(
            argv=["gh", "run", "view", workflow_run, "--json", "attempt"],
            cwd=context.plan.repo,
            timeout_seconds=GH_TIMEOUT_SECONDS,
        )
        journal_stage(
            journal=context.journal,
            plan=context.plan,
            stage="merge-poll-rerun-attempt",
            result=result,
        )
        if result.exit_code != 0 or _attempt_of(stdout=result.stdout) <= prior_attempt:
            return False
    return True


def _attempt_of(*, stdout: str) -> int:
    try:
        attempt = cast("dict[str, object]", json.loads(stdout))["attempt"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return 0
    return attempt if isinstance(attempt, int) else 0


def _blocked_outcome(
    *,
    context: RequiredCheckFailureContext,
    view: PrView,
    failed: list[str],
) -> DispatchOutcome:
    """The outcome a terminal required-check failure records without any rerun."""
    return required_check_failure_outcome(
        outcome_type=context.outcome_type,
        plan=context.plan,
        number=view.number,
        merge_sha=view.merge_sha,
        failed=failed,
    )
