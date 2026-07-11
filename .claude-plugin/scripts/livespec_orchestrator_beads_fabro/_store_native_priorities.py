"""Native beads-priority reads for migration helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro.errors import BeadsMappingError

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsRecord
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = ["read_work_item_native_priorities"]


def read_work_item_native_priorities(*, path: StoreConfig) -> dict[str, int]:
    """Return beads-native priority values keyed by work-item id.

    `WorkItem` deliberately no longer exposes logical `priority`; this
    narrow migration helper reads the raw native column only for the
    one-time legacy rank seed ordering. Malformed records raise through
    the same mapping-error path as normal materialization.
    """
    client = make_beads_client(config=path)
    priorities: dict[str, int] = {}
    for record in client.list_issues():
        issue_id = _require_str(record=record, key="id")
        priority = record.get("priority")
        if not isinstance(priority, int) or isinstance(priority, bool):
            raise BeadsMappingError(
                record_id=issue_id,
                detail="priority must be an integer",
            )
        priorities[issue_id] = priority
    return priorities


def _require_str(*, record: BeadsRecord, key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str):
        raise BeadsMappingError(
            record_id=str(record.get("id", "<unknown>")),
            detail=f"field {key!r} must be a string (got {type(value).__name__})",
        )
    return value
