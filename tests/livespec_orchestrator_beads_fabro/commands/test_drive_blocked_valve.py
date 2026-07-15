"""Tests for the blocked-item drive human valve helper."""

from __future__ import annotations

from dataclasses import replace

from livespec_orchestrator_beads_fabro.commands._drive_blocked_valve import unblock_item
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id="bd-ib-drive-block",
        type="task",
        status="blocked",
        title="A blocked task",
        description="Do the thing.",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-07-10T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        blocked_reason="needs-human",
    )
    return replace(base, **overrides)


def _stored() -> dict[str, WorkItem]:
    return materialize_work_items(records=read_work_items(path=_config()))


def test_unblock_item_clears_needs_human_label() -> None:
    item = _item()
    append_work_item(path=_config(), item=item)

    result = unblock_item(
        config=_config(),
        item=item,
        action_id=f"unblock:{item.id}:ready",
        target_status="ready",
    )

    assert result["status"] == "green"
    stored = _stored()[item.id]
    assert (stored.status, stored.blocked_reason) == ("ready", None)


def test_unblock_item_refuses_non_needs_human_source() -> None:
    item = _item(status="ready", blocked_reason=None)

    result = unblock_item(
        config=_config(),
        item=item,
        action_id=f"unblock:{item.id}:ready",
        target_status="ready",
    )

    assert result["status"] == "failed"
    assert result["domain_error"] == "invalid-source-state"
