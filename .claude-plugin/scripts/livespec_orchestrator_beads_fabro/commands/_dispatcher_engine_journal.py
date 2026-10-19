"""Shared journaling helpers for dispatcher engine slices."""

from __future__ import annotations

import re
from collections.abc import Mapping
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_records import (
    RUN_WALL_BUDGET_EXCEEDED_STAGE,
)

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
    "REMOVED_ENV_VARS_FIELD",
    "StageJournalOptions",
    "failed_outcome",
    "journal_publish_draft_refresh",
    "journal_run_output_markers",
    "journal_stage",
    "run_stage",
    "run_wall_budget_outcome",
    "stalled_outcome",
    "tail",
]


@dataclass(frozen=True, kw_only=True)
class StageJournalOptions:
    """Optional journal-row and failed-output behavior for one stage."""

    streams: bool = False
    retention: JanitorRetention | None = None
    # `None` means this stage scrubs nothing and owes no account of it; an
    # EMPTY TUPLE means it scrubs and removed nothing, which is a reading its
    # row must carry rather than omit. A single tuple cannot say both.
    removed_env_vars: tuple[str, ...] | None = None
    # Extra row fields one stage's record carries beside the shared ones, as a
    # plain mapping the CALLER computed. A mapping rather than a callable over
    # the result, because a stage whose row reports on its own command's output
    # already has that output in hand by the time it journals -- and a callable
    # on a shared options type would be a seam for one call site that every
    # other one has to read past. `None` means this stage owes no account
    # beyond the shared fields.
    extra_fields: Mapping[str, object] | None = None


# The row field naming what a stage's child environment LOST against the
# Dispatcher's own. Named once, so the writer and every reader of the scrub's
# durable account cannot drift.
REMOVED_ENV_VARS_FIELD = "removed_env_vars"

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


def run_wall_budget_outcome(
    *,
    outcome_type: type[DispatchOutcome],
    plan: DispatchPlan,
    run_id: str,
) -> DispatchOutcome:
    """The terminal a run cancelled on its whole-run wall budget reports.

    Its OWN status rather than the stall status, because the two carry opposite
    dispositions: a first stall cancel releases the item to `ready` for the
    ordinary admission valve, while a budget cancel rests it at `blocked` /
    `needs-human` and nothing automatic leaves that state.

    The detail names the resolved budget, the LAYER that supplied it and the key
    an operator would raise, because the terminal is what a dispatch RESULT
    reports while the `run-wall-budget-exceeded` journal row carrying the
    measured elapsed seconds is a per-clone file — so a reader holding only the
    result still knows which number was applied and where it came from.
    """
    budget = plan.run_wall_budget
    return outcome_type(
        work_item_id=plan.work_item_id,
        status=RUN_WALL_BUDGET_EXCEEDED_STAGE,
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail=(
            f"run {run_id} held a factory slot past its whole-run wall budget of "
            f"{int(budget.seconds)} seconds (supplied by the {budget.layer} layer); "
            f"its record was exported and read back and the run was then cancelled "
            f"to release the slot. Raise dispatcher.run_wall_budget_seconds, or pass "
            f"--run-wall-budget-seconds, if this item's runs legitimately need "
            f"longer. The {RUN_WALL_BUDGET_EXCEEDED_STAGE} journal row carries the "
            f"elapsed slot-holding seconds measured and the preserve-by-reference "
            f"pointer the tree was exported to."
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

    `journal_options.removed_env_vars` is the durable account of a stage's
    environment scrub, and it is opt-in for the same reason: the janitor is the
    only stage that removes anything, and a field on every row would say
    "removed nothing" about stages that scrub by construction. Its EMPTY arm is
    written rather than omitted, so a reader can tell a scrubbing build that
    found nothing to remove from a build that does not scrub.

    `journal_options.extra_fields` are the row fields one stage owes beyond the
    shared set, already computed. They are merged UNDERNEATH the shared fields
    rather than over them, which is the whole guarantee that an extra account
    ADDS to the record: a stage cannot redefine `stage`, `exit_code` or
    `detail` by naming one of them, so a reader of any row can still read those
    four the same way whatever else the row carries.
    """
    record: dict[str, object] = {
        **(journal_options.extra_fields or {}),
        "work_item_id": plan.work_item_id,
        "stage": stage,
        "exit_code": result.exit_code,
        "detail": tail(text=result.stderr if result.exit_code != 0 else result.stdout),
    }
    if journal_options.streams:
        record["stdout"] = tail(text=result.stdout)
        record["stderr"] = tail(text=result.stderr)
    if journal_options.removed_env_vars is not None:
        record[REMOVED_ENV_VARS_FIELD] = list(journal_options.removed_env_vars)
    if journal_options.retention is not None:
        record.update(
            retained_output_record(
                retention=journal_options.retention,
                stage=stage,
                result=result,
            )
        )
    journal.append(record=record)


StageCommand = tuple[list[str], Path, float, Mapping[str, str | None] | None]


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
