"""Shared journaling helpers for dispatcher engine slices."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_janitor_failure_diagnostics import (
    janitor_failure_diagnosis,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_janitor_output_retention import (
    retained_output_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
        CommandResult,
        CommandRunner,
        DispatchOutcome,
        JournalWriter,
    )
    from livespec_orchestrator_beads_fabro.commands._dispatcher_janitor_output_retention import (
        JanitorRetention,
    )

__all__: list[str] = [
    "StageJournalOptions",
    "failed_outcome",
    "journal_stage",
    "run_stage",
    "stalled_outcome",
    "tail",
]


@dataclass(frozen=True, kw_only=True)
class StageJournalOptions:
    """Optional journal-row and failed-output behavior for one stage."""

    streams: bool = False
    retention: JanitorRetention | None = None
    janitor_failure_diagnostics: bool = False


_DEFAULT_STAGE_JOURNAL_OPTIONS = StageJournalOptions()


def failed_outcome(
    *,
    outcome_type: type[DispatchOutcome],
    plan: DispatchPlan,
    stage: str,
    detail: str,
    fabro_run_id: str | None = None,
) -> DispatchOutcome:
    return outcome_type(
        work_item_id=plan.work_item_id,
        status="failed",
        stage=stage,
        pr_number=None,
        merge_sha=None,
        detail=detail,
        fabro_run_id=fabro_run_id,
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
        fabro_run_id=run_id,
    )


def journal_stage(
    *,
    journal: JournalWriter,
    plan: DispatchPlan,
    stage: str,
    result: CommandResult,
    journal_options: StageJournalOptions = _DEFAULT_STAGE_JOURNAL_OPTIONS,
) -> None:
    """Append one stage record, optionally carrying BOTH captured streams.

    `detail` alone carries whichever stream the exit code SELECTED, which is
    enough for a step that fails loudly and not enough for one that FAILS OPEN --
    exits 0 having provisioned nothing, with its diagnosis on the stream the
    exit code did not select. That record is indistinguishable from a step which
    genuinely did its work, so the venue's provisioning steps ask for `streams`
    and journal both.

    `journal_options.retention` is the post-merge janitor's output-retention
    venue, and it is OPT-IN per call site rather than read off the plan here,
    because the retention clause covers the janitor's own commands and nothing
    else: a default that retained for every journaled stage would be the broad
    capture of every command the clause declines to perform.
    """
    record: dict[str, object] = {
        "work_item_id": plan.work_item_id,
        "stage": stage,
        "exit_code": result.exit_code,
        "detail": tail(text=result.stderr if result.exit_code != 0 else result.stdout),
    }
    if journal_options.streams:
        record["stdout"] = tail(text=result.stdout)
        record["stderr"] = tail(text=result.stderr)
    if journal_options.retention is not None:
        record.update(
            retained_output_record(
                retention=journal_options.retention,
                stage=stage,
                result=result,
            )
        )
    if journal_options.janitor_failure_diagnostics and result.exit_code != 0:
        diagnosis = janitor_failure_diagnosis(stdout=result.stdout, stderr=result.stderr)
        record["detail"] = diagnosis.detail
        if diagnosis.failed_targets:
            record["failed_targets"] = list(diagnosis.failed_targets)
    journal.append(record=record)


StageCommand = tuple[list[str], Path, float, dict[str, str] | None]


def run_stage(
    *,
    runner: CommandRunner,
    journal: JournalWriter,
    plan: DispatchPlan,
    stage: str,
    command: StageCommand,
    journal_options: StageJournalOptions = _DEFAULT_STAGE_JOURNAL_OPTIONS,
) -> CommandResult:
    argv, cwd, timeout_seconds, env = command
    result = runner.run(argv=argv, cwd=cwd, timeout_seconds=timeout_seconds, env=env)
    journal_stage(
        journal=journal,
        plan=plan,
        stage=stage,
        result=result,
        journal_options=journal_options,
    )
    return result


def tail(*, text: str, limit: int = 2000) -> str:
    stripped = text.strip()
    if len(stripped) <= limit:
        return stripped
    return stripped[-limit:]
