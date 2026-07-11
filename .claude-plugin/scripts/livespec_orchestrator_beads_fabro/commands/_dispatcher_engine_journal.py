"""Shared journaling helpers for dispatcher engine slices."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
        CommandResult,
        CommandRunner,
        DispatchOutcome,
        JournalWriter,
    )

__all__: list[str] = ["failed_outcome", "journal_stage", "run_stage", "stalled_outcome", "tail"]


def failed_outcome(
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


def stalled_outcome(
    *,
    outcome_type: type[DispatchOutcome],
    plan: DispatchPlan,
    run_id: str,
) -> DispatchOutcome:
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
            f"Set LIVESPEC_DISPATCH_STALL_SECONDS to tune the window; the DEFERRED 29f "
            f"OTEL metrics-heartbeat primary will refine this coarse signal."
        ),
    )


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
            "detail": tail(text=result.stderr if result.exit_code != 0 else result.stdout),
        }
    )


StageCommand = tuple[list[str], Path, float, dict[str, str] | None]


def run_stage(
    *,
    runner: CommandRunner,
    journal: JournalWriter,
    plan: DispatchPlan,
    stage: str,
    command: StageCommand,
) -> CommandResult:
    argv, cwd, timeout_seconds, env = command
    result = runner.run(argv=argv, cwd=cwd, timeout_seconds=timeout_seconds, env=env)
    journal_stage(journal=journal, plan=plan, stage=stage, result=result)
    return result


def tail(*, text: str, limit: int = 2000) -> str:
    stripped = text.strip()
    if len(stripped) <= limit:
        return stripped
    return stripped[-limit:]
