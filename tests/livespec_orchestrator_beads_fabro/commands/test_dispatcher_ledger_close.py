"""Tests for dispatcher outcome emission helpers."""

from __future__ import annotations

import json

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_close import (
    emit_outcomes,
    plan_native_status_remaps,
)
from livespec_orchestrator_beads_fabro.types import WorkItem
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
