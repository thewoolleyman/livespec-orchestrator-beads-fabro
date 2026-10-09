"""Ledger reads and mutations for the factory-size admission gate."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsRecord
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "record_size_justification",
    "route_factory_size_decomposition",
    "size_justification_for",
    "size_justification_from_record",
]

SIZE_JUSTIFICATION_KEY = "size_justification"


def size_justification_for(*, path: StoreConfig, work_item_id: str) -> object:
    """Return the raw justification metadata so the exact validator can judge it."""
    record = make_beads_client(config=path).show_issue(issue_id=work_item_id)
    return size_justification_from_record(record=record)


def size_justification_from_record(*, record: BeadsRecord) -> object:
    """Return a record's uncoerced justification, or ``None`` when absent."""
    return _metadata_of(record=record).get(SIZE_JUSTIFICATION_KEY)


def record_size_justification(
    *, path: StoreConfig, work_item_id: str, justification: object
) -> None:
    """Persist one groom/capture justification without dropping other metadata."""
    client = make_beads_client(config=path)
    metadata = _metadata_of(record=client.show_issue(issue_id=work_item_id))
    metadata[SIZE_JUSTIFICATION_KEY] = justification
    client.update_issue(issue_id=work_item_id, metadata=metadata)


def route_factory_size_decomposition(*, path: StoreConfig, work_item_id: str, reason: str) -> None:
    """Move one oversized item to backlog and retain the auditable reason."""
    client = make_beads_client(config=path)
    client.update_issue(issue_id=work_item_id, status="backlog")
    client.add_comment(issue_id=work_item_id, body=reason)


def _metadata_of(*, record: BeadsRecord) -> dict[str, Any]:
    raw = record.get("metadata")
    return dict(cast("dict[str, Any]", raw)) if isinstance(raw, dict) else {}
