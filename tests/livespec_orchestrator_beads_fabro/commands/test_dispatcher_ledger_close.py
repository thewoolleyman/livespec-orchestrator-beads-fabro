"""Tests for dispatcher outcome emission helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_close import (
    emit_outcomes,
    ledger_blocked_after_normalization,
    plan_native_status_remaps,
)
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from livespec_runtime.work_items.rank import BOTTOM_SENTINEL, key_between
from returns.result import Success, safe


def _item(*, item_id: str, status: str, rank: str) -> WorkItem:
    return WorkItem(
        id=item_id,
        type="task",
        status=status,
        title=item_id,
        description="Rank normalization regression",
        origin="freeform",
        gap_id=None,
        rank=rank,
        assignee=None,
        depends_on=(),
        captured_at="2026-10-14T09:14:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


@pytest.mark.parametrize(
    "malformed", ["zz", "zzz", "", "a", "a00", "a!", "a0!", "é0", "00", "A" + "0" * 26]
)
@pytest.mark.parametrize("anchor", [None, "a5", "Zz", "a0V", "b00"])
def test_native_adoptions_ignore_malformed_live_ranks(
    *, malformed: str, anchor: str | None
) -> None:
    items = [
        _item(item_id="bad-rank", status="pending-approval", rank=malformed),
        _item(item_id="raw-open", status="open", rank=BOTTOM_SENTINEL),
        _item(item_id="raw-claim", status="in_progress", rank=BOTTOM_SENTINEL),
        _item(item_id="closed-tail", status="done", rank="zzz"),
    ]
    if anchor is not None:
        items.append(_item(item_id="anchor", status="backlog", rank=anchor))

    result = safe(plan_native_status_remaps)(items=items)

    assert isinstance(result, Success), result
    planned = result.unwrap()
    first = key_between(a=anchor, b=None)
    assert [(row["item_id"], row["to"], row["rank"]) for row in planned] == [
        ("raw-open", "backlog", first),
        ("raw-claim", "active", key_between(a=first, b=None)),
    ]
    assert items[0].rank == malformed


@pytest.mark.parametrize("native_status", [None, "open", "in_progress"])
def test_preflight_reports_malformed_live_ranks_without_blocking(
    *, tmp_path: Path, native_status: str | None
) -> None:
    config = StoreConfig(
        tenant="rank-regression",
        prefix="rank-regression",
        server_user="rank-regression",
        database="rank-regression",
        bd_path="bd",
        fake=True,
    )
    items = [
        _item(item_id="bd-ib-hiduhs", status="pending-approval", rank="zz"),
        _item(item_id="empty-rank", status="backlog", rank=""),
        _item(item_id="anchor", status="ready", rank="a5"),
        _item(item_id="unranked", status="backlog", rank=BOTTOM_SENTINEL),
        _item(item_id="closed-fixture", status="done", rank="zzz"),
    ]
    if native_status is not None:
        items.append(_item(item_id="raw-native", status=native_status, rank=BOTTOM_SENTINEL))
    for item in items:
        append_work_item(path=config, item=item)
    journal_path = tmp_path / "journal.jsonl"

    blocked = ledger_blocked_after_normalization(
        items=items, config=config, journal=JournalFile(path=journal_path)
    )

    assert blocked is False
    records = (
        [json.loads(line) for line in journal_path.read_text(encoding="utf-8").splitlines()]
        if journal_path.exists()
        else []
    )
    warnings = [row for row in records if row["stage"] == "rank-normalization-warning"]
    assert len(warnings) == 1
    assert warnings[0]["malformed_ranks"] == [
        {"item_id": "bd-ib-hiduhs", "rank": "zz"},
        {"item_id": "empty-rank", "rank": ""},
    ]
    assert warnings[0]["at"]
    assert warnings[0]["invoker"]
    stored = materialize_work_items(records=read_work_items(path=config))
    assert stored["bd-ib-hiduhs"].rank == "zz"
    if native_status is not None:
        assert stored["raw-native"].status == ("backlog" if native_status == "open" else "active")
        assert stored["raw-native"].rank == key_between(a="a5", b=None)


def test_emit_outcomes_json_includes_present_fabro_failure_fields(
    capsys: pytest.CaptureFixture[str],
) -> None:
    outcome = DispatchOutcome(
        work_item_id="bd-ib-rdbtzo.3",
        status="failed",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail="script failed with exit 2",
        fabro_run_id="01RUNCAUSE",
        fabro_failure_cause="script failed with exit 2",
        fabro_failure_category="deterministic",
        fabro_failure_signature="fix|deterministic|script failed",
    )

    emit_outcomes(outcomes=[outcome], as_json=True)

    payload = json.loads(capsys.readouterr().out)
    assert payload == [
        {
            "detail": "script failed with exit 2",
            "fabro_failure_cause": "script failed with exit 2",
            "fabro_failure_category": "deterministic",
            "fabro_failure_signature": "fix|deterministic|script failed",
            "fabro_run_id": "01RUNCAUSE",
            "merge_sha": None,
            "pr_number": None,
            "stage": "fabro-run",
            "status": "failed",
            "work_item_id": "bd-ib-rdbtzo.3",
        }
    ]
