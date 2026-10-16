"""Shared journaling helpers for dispatcher engine slices."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_hook_over_limit import (
    HookOverLimit,
    hook_over_limit_from_text,
    journal_hook_over_limit,
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
    "journal_publish_draft_refresh",
    "journal_run_output_markers",
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


_DEFAULT_STAGE_JOURNAL_OPTIONS = StageJournalOptions()
_PUBLISH_DRAFT_REFRESH_PATTERN = re.compile(
    "".join(
        (
            r"LIVESPEC_PUBLISH_DRAFT_REFRESH: ",
            r"publish_branch=(?P<publish_branch>\S+) ",
            r"base_before=(?P<base_before>[0-9a-f]{40,64}) ",
            r"base_after=(?P<base_after>[0-9a-f]{40,64})",
        )
    )
)


def journal_publish_draft_refresh(
    *,
    journal: JournalWriter,
    work_item_id: str,
    text: str,
) -> None:
    """Project the publish-base refresh marker into its own journal row."""
    match = _PUBLISH_DRAFT_REFRESH_PATTERN.search(text)
    if match is None:
        return
    journal.append(
        record={
            "work_item_id": work_item_id,
            "stage": "publish-draft-refresh",
            "publish_branch": match.group("publish_branch"),
            "base_before": match.group("base_before"),
            "base_after": match.group("base_after"),
        }
    )


def journal_run_output_markers(
    *,
    journal: JournalWriter,
    work_item_id: str,
    text: str,
) -> HookOverLimit | None:
    """Project every publication marker one run's output carries into rows.

    ONE pass over ONE text, which is the point: both markers are printed by the
    same `publish_draft` script into the same stream, and two call sites reading
    the run output separately would be two readings nothing proves agree about
    the run they describe.

    Returns the `hook-over-limit` event so the caller can attach it to the
    terminal outcome. The row is written HERE, unconditionally of how the run
    ended, because the clause requires it "whether or not the run later
    recovers"; the CAUSE is rendered elsewhere, only where the ending is
    attributed to the event. Returning the event rather than re-parsing it at
    the cause writer is what keeps the row and the cause describing one reading.
    """
    journal_publish_draft_refresh(journal=journal, work_item_id=work_item_id, text=text)
    event = hook_over_limit_from_text(text=text)
    journal_hook_over_limit(journal=journal, work_item_id=work_item_id, event=event)
    return event


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
            f"Set dispatcher.stall_timeout_seconds to tune the window — the "
            f"`watchdog-stall-cancel` journal row carries the window this run "
            f"was graded against and the layer that supplied it; the DEFERRED 29f "
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
