"""The `--item` preflight answers set membership without taking the ready-age ordering.

`requested_items_preflight_error` asks only whether each requested id is dispatchable,
which is a question about a SET. It reached that set through `ready_items` and the
rework projection, and both sort their rows by the ready-age key, whose lookup reads the
whole ledger (`bd list --status all --limit 0` and a parse of every record) to find the
ready-dwell instants. The preflight discarded the order it paid for (measured 2026-11-14:
28-31 CPU-seconds per dispatch in this phase, a share of it those two dumps).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import pytest
from livespec_orchestrator_beads_fabro import _beads_client_fake
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_checks import (
    requested_items_preflight_error,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_READY_ID = "bd-ib-preflightready"
_MARKED_ID = "bd-ib-preflightmarked"


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _item(*, item_id: str, status: Literal["ready", "active"], rework_pending: bool) -> WorkItem:
    return WorkItem(
        id=item_id,
        type="bug",
        status=status,
        title="A requested row",
        description="Implement the slice.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro" if status == "active" else None,
        depends_on=(),
        captured_at="2026-11-08T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        rework_pending=rework_pending,
    )


def test_the_preflight_takes_no_whole_ledger_read_for_an_ordering_it_discards(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    items = [
        _item(item_id=_READY_ID, status="ready", rework_pending=False),
        _item(item_id=_MARKED_ID, status="active", rework_pending=True),
    ]
    for item in items:
        append_work_item(path=_config(), item=item)
    monkeypatch.setattr(
        _beads_client_fake.FakeBeadsClient,
        "list_issues",
        lambda _self: pytest.fail("the preflight read the whole ledger for an ordering"),
    )

    error = requested_items_preflight_error(
        requested_ids={_READY_ID, _MARKED_ID},
        items=items,
        repo=repo,
        journal=JournalFile(path=repo / "journal.jsonl"),
    )

    assert error is None
