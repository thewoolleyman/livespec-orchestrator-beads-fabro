"""Immutable factory-size admission evidence for one dispatch."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import JournalWriter
    from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_size_gate import (
        FactorySizeDecision,
    )
    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "FACTORY_SIZE_ADMISSION_STAGE",
    "record_factory_size_admission_decision",
    "size_justified_at_admission",
]

FACTORY_SIZE_ADMISSION_STAGE = "factory-size-admission"
_SIZE_JUSTIFIED_FIELD = "size_justified"
_DISPATCH_ID_STAGE = "dispatch-id"
_DISPATCH_ID_FIELD = "dispatch_id"


def record_factory_size_admission_decision(
    *, journal: JournalWriter, item: WorkItem, decision: FactorySizeDecision
) -> None:
    """Persist the exact size-gate decision before this item dispatches."""
    journal.append(
        record={
            "stage": FACTORY_SIZE_ADMISSION_STAGE,
            "work_item_id": item.id,
            "adopted_assertion_count_ceiling": decision.adopted_ceiling,
            "assertion_count": decision.assertion_count,
            _SIZE_JUSTIFIED_FIELD: decision.size_justified,
        }
    )


def size_justified_at_admission(
    *,
    records: tuple[dict[str, object], ...],
    work_item_id: str,
    dispatch_id: str,
) -> bool | None:
    """Read the size decision immediately preceding one exact dispatch."""
    dispatch_index = next(
        (
            index
            for index in range(len(records) - 1, -1, -1)
            if records[index].get("stage") == _DISPATCH_ID_STAGE
            and records[index].get("work_item_id") == work_item_id
            and records[index].get(_DISPATCH_ID_FIELD) == dispatch_id
        ),
        None,
    )
    if dispatch_index is None:
        return None
    for record in reversed(records[:dispatch_index]):
        if record.get("work_item_id") != work_item_id:
            continue
        stage = record.get("stage")
        if stage == FACTORY_SIZE_ADMISSION_STAGE:
            value = record.get(_SIZE_JUSTIFIED_FIELD)
            return value if isinstance(value, bool) else None
        if stage == _DISPATCH_ID_STAGE:
            return None
    return None
