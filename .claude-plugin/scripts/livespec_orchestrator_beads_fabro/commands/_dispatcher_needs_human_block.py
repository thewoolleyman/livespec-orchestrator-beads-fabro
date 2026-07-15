"""Dispatcher-level blocked / needs-human ledger escalation write path."""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._store_mutations import update_work_item_blocked_reason
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    WorkItemNotFoundError,
)

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = ["block_needs_human"]


def block_needs_human(*, repo: Path, item: WorkItem, reason: str, journal: JournalFile) -> None:
    """Escalate an in-flight item to terminal `blocked` / `needs-human`.

    The existing item is transitioned in place to `blocked`, the
    `blocked-reason:needs-human` label is written through the store seam, and a
    dispatcher journal record names both the work item and escalation reason.
    Fail-soft mirrors the other post-verdict ledger writes: the dispatch verdict
    is already terminal, so expected store failures are journaled and swallowed.
    """
    try:
        update_work_item_blocked_reason(
            path=store_config(repo=repo),
            item_id=item.id,
            status="blocked",
            blocked_reason="needs-human",
        )
    except (
        WorkItemNotFoundError,
        BeadsCommandError,
        BeadsConnectionError,
        BeadsMappingError,
        BeadsTenantMissingError,
    ) as exc:
        journal.append(
            record={
                "stage": "needs-human-block-error",
                "work_item_id": item.id,
                "reason": f"{type(exc).__name__}",
            }
        )
        return
    journal.append(
        record={
            "stage": "needs-human-blocked",
            "work_item_id": item.id,
            "reason": reason,
        }
    )
