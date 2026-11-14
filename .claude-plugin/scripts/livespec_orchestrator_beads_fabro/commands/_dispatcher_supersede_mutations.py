"""Ledger mutations applied after filing a contaminated-item successor."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro._beads_client import (
    EDGE_BLOCKS,
    EDGE_PARENT_CHILD,
    BeadsRecord,
)
from livespec_orchestrator_beads_fabro._store_comments import append_work_item_comment

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "copy_labels",
    "parent_id",
    "record_disposition_comments",
    "replace_inbound_blocks",
]


def parent_id(*, record: BeadsRecord) -> str | None:
    """Return the original item's plan parent, if it carries one."""
    edges = record.get("dependencies")
    if not isinstance(edges, list):
        return None
    for raw_edge in cast("list[object]", edges):
        edge = cast("BeadsRecord", raw_edge)
        target = edge.get("depends_on_id")
        if edge.get("type") == EDGE_PARENT_CHILD and isinstance(target, str):
            return target
    return None


def copy_labels(*, client: BeadsClient, raw: BeadsRecord, successor_id: str) -> None:
    """Carry ordinary labels while excluding lifecycle and run bookkeeping."""
    labels = raw.get("labels")
    if not isinstance(labels, list):
        return
    copied = [
        label
        for label in cast("list[object]", labels)
        if isinstance(label, str)
        and not label.startswith(("lifecycle:", "claim:", "dispatch-record:"))
    ]
    if copied:
        client.update_issue(issue_id=successor_id, add_labels=copied)


def replace_inbound_blocks(*, client: BeadsClient, original_id: str, successor_id: str) -> None:
    """Move each item blocked on the original to the usable successor."""
    for record in client.list_issues():
        from_id = record.get("id")
        edges = record.get("dependencies")
        if not isinstance(from_id, str) or not isinstance(edges, list):
            continue
        if not _blocks(record_edges=cast("list[object]", edges), original_id=original_id):
            continue
        client.remove_dependency(from_id=from_id, to_id=original_id)
        client.add_dependency(from_id=from_id, to_id=successor_id, edge_type=EDGE_BLOCKS)


def record_disposition_comments(
    *,
    original_id: str,
    successor_id: str,
    reason: str,
    record_ids: tuple[str, ...],
    config: StoreConfig,
) -> None:
    """Append reciprocal evidence after every instruction rider has copied."""
    ids = ", ".join(record_ids) or "none"
    append_work_item_comment(
        path=config,
        work_item_id=successor_id,
        body=(
            f"Supersedes {original_id}; reason: {reason}; "
            f"record comments left on original: {ids}."
        ),
    )
    append_work_item_comment(
        path=config,
        work_item_id=original_id,
        body=f"Superseded by {successor_id}; reason: {reason}.",
    )


def _blocks(*, record_edges: list[object], original_id: str) -> bool:
    return any(
        cast("BeadsRecord", raw_edge).get("type") == EDGE_BLOCKS
        and cast("BeadsRecord", raw_edge).get("depends_on_id") == original_id
        for raw_edge in record_edges
    )
