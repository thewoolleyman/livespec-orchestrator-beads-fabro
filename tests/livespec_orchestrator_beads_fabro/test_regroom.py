"""Paired coverage for backlog groom-out helpers."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro import regroom
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _backlog_item(*, item_id: str) -> WorkItem:
    return WorkItem(
        id=item_id,
        type="feature",  # type: ignore[arg-type]
        status="backlog",
        title="t",
        description="d",
        origin="manual",  # type: ignore[arg-type]
        gap_id=None,
        rank="a1",
        assignee=None,
        depends_on=(),
        captured_at="2026-06-20T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def test_backlog_status_names_groomable_state() -> None:
    assert regroom.BACKLOG_STATUS == "backlog"


def test_close_regroomed_out_records_replacement_slice_ids() -> None:
    config = _config()
    append_work_item(path=config, item=_backlog_item(item_id="bd-parent"))

    regroom.close_regroomed_out(
        path=config,
        item_id="bd-parent",
        replacement_slice_ids=["bd-a", "bd-b"],
    )

    closed = materialize_work_items(records=read_work_items(path=config))["bd-parent"]
    assert closed.status == "done"
    assert closed.resolution == "no-longer-applicable"
    assert closed.reason == "regroomed out into replacement slices: bd-a, bd-b"
