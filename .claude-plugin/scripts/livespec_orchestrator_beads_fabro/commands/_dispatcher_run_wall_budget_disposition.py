"""Where a whole-run wall-budget cancel leaves its work-item."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from livespec_orchestrator_beads_fabro._store_blocked_mutations import (
    update_work_item_blocked_state,
)
from livespec_orchestrator_beads_fabro._store_comments import append_work_item_comment
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_guard import terminal_claim
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_writes import claim_blocked_write
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_journal_rows import (
    journal_records,
    names_stage,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_comment import (
    run_wall_budget_comment,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_records import (
    RUN_WALL_BUDGET_EXCEEDED_STAGE,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    WorkItemNotFoundError,
)
from livespec_orchestrator_beads_fabro.io import write_stderr
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "RUN_WALL_BUDGET_NEEDS_HUMAN_STAGE",
    "dispose_run_wall_budget_cancel",
    "latest_run_wall_budget_row",
]

RUN_WALL_BUDGET_NEEDS_HUMAN_STAGE = "run-wall-budget-needs-human"
_LEDGER_WRITE_ERRORS = (
    WorkItemNotFoundError,
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
)


def latest_run_wall_budget_row(
    *, journal: JournalFile, item_id: str
) -> Mapping[str, object] | None:
    """Return this item's newest budget-cancel row, if one exists."""
    rows = [
        record
        for record in journal_records(journal=journal)
        if names_stage(record=record, item_id=item_id, stage=RUN_WALL_BUDGET_EXCEEDED_STAGE)
    ]
    return rows[-1] if rows else None


def dispose_run_wall_budget_cancel(
    *, repo: Path, item: WorkItem, outcome: DispatchOutcome, journal: JournalFile
) -> None:
    """Rest a run-wall-budget-cancelled item at blocked / needs-human."""
    if outcome.status != RUN_WALL_BUDGET_EXCEEDED_STAGE:
        return
    row = latest_run_wall_budget_row(journal=journal, item_id=item.id)
    _ = attempt(
        action=lambda: append_work_item_comment(
            path=store_config(repo=repo),
            work_item_id=item.id,
            body=run_wall_budget_comment(item_id=item.id, row=row),
        ),
        exceptions=_LEDGER_WRITE_ERRORS,
    )
    rested = attempt(
        action=lambda: claim_blocked_write(
            repo=repo,
            path=store_config(repo=repo),
            intent="run-wall-budget-rest",
            write=update_work_item_blocked_state,
            item_id=item.id,
            blocked_reason="needs-human",
            admission_policy="manual",
            journal=journal,
            still_as_decided=terminal_claim(item=item, run_id=outcome.fabro_run_id),
        ),
        exceptions=_LEDGER_WRITE_ERRORS,
    )
    if isinstance(rested, AttemptFailure):
        journal.append(
            record={
                "stage": f"{RUN_WALL_BUDGET_NEEDS_HUMAN_STAGE}-error",
                "work_item_id": item.id,
                "reason": f"{type(rested.error).__name__}",
            }
        )
        return
    if rested is not None:
        return
    _journal_rest(journal=journal, item=item, row=row)


def _journal_rest(
    *, journal: JournalFile, item: WorkItem, row: Mapping[str, object] | None
) -> None:
    """Record a completed human rest and surface it for the operator."""
    journal.append(
        record={
            "stage": RUN_WALL_BUDGET_NEEDS_HUMAN_STAGE,
            "work_item_id": item.id,
            "status": "blocked",
            "blocked_reason": "needs-human",
            "run_id": None if row is None else row.get("run_id"),
            "elapsed_seconds": None if row is None else row.get("elapsed_seconds"),
            "budget_seconds": None if row is None else row.get("budget_seconds"),
            "preserved_pointer": None if row is None else row.get("preserved_pointer"),
            "preserved_ref": None if row is None else row.get("preserved_ref"),
            "preserved_ref_commit": None if row is None else row.get("preserved_ref_commit"),
        }
    )
    _ = write_stderr(
        text=(
            f"SURFACE: work-item {item.id} held a factory slot past its whole-run wall "
            f"budget; its run was exported and cancelled, it rests at blocked / "
            f"needs-human, and no further dispatch or resume is invoked automatically. "
            f"The cancellation is NOT non-convergence and the slice was not bounced to "
            f"backlog.\n"
        )
    )
