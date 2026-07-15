"""Dispatcher ledger escalation for Fabro human-gate blocked outcomes."""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro._store_mutations import update_work_item_blocked_state
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    WorkItemNotFoundError,
)
from livespec_orchestrator_beads_fabro.io import write_stderr
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = ["escalate_needs_human_block"]

_LEDGER_WRITE_ERRORS = (
    WorkItemNotFoundError,
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
)


def escalate_needs_human_block(
    *,
    repo: Path,
    item: WorkItem,
    outcome: DispatchOutcome,
    journal: JournalFile,
) -> None:
    """Persist a Fabro human-gate terminal as blocked/needs-human.

    A Fabro `blocked` terminal means the implementation run reached an in-loop
    human gate. Persist that as a Dispatcher-level terminal ledger state, not as
    `backlog`: the item remains unavailable to autonomous admission until a
    human valve deliberately clears the block.
    """
    if outcome.status != "blocked":
        return
    if item.status == "blocked" and item.blocked_reason == "needs-human":
        return
    try:
        update_work_item_blocked_state(
            path=store_config(repo=repo),
            item_id=item.id,
            status="blocked",
            blocked_reason="needs-human",
            admission_policy="manual",
        )
    except _LEDGER_WRITE_ERRORS as exc:
        journal.append(
            record={
                "stage": "needs-human-blocked-error",
                "work_item_id": item.id,
                "reason": f"{type(exc).__name__}",
            }
        )
        return
    journal.append(
        record={
            "stage": "needs-human-blocked",
            "work_item_id": item.id,
            "reason": "needs-human",
            "outcome_stage": outcome.stage,
            "outcome_status": outcome.status,
        }
    )
    surface_line = (
        f"SURFACE: work-item {item.id} parked at a Fabro human gate; "
        "marked blocked/needs-human and held terminal until a human valve "
        "moves it out.\n"
    )
    _ = write_stderr(text=surface_line)
