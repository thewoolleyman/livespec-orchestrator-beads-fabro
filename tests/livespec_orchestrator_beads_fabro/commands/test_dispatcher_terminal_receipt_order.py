"""The WIP receipt never holds up a terminal lifecycle disposition."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop_selection
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.types import WorkItem


@dataclass
class _Journal:
    path: Path
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def test_terminal_receipt_follows_the_lifecycle_disposition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    order: list[str] = []

    def _noop(**_kwargs: object) -> None:
        return None

    monkeypatch.setattr(_dispatcher_loop_selection, "record_provider_exhaustion_if_observed", _noop)
    monkeypatch.setattr(
        _dispatcher_loop_selection, "record_dead_implementer_truncation_if_observed", _noop
    )
    monkeypatch.setattr(_dispatcher_loop_selection, "preserve_terminated_run_work", _noop)
    monkeypatch.setattr(_dispatcher_loop_selection, "record_groom_draft", lambda **_: False)
    monkeypatch.setattr(_dispatcher_loop_selection, "record_base_advanced_after_arming", _noop)
    monkeypatch.setattr(
        _dispatcher_loop_selection,
        "escalate_needs_human_block",
        lambda **_: order.append("transition"),
    )
    monkeypatch.setattr(_dispatcher_loop_selection, "record_needs_human_cause", _noop)
    monkeypatch.setattr(_dispatcher_loop_selection, "dispose_terminal_routing", _noop)
    monkeypatch.setattr(_dispatcher_loop_selection, "emit_calibration", _noop)
    monkeypatch.setattr(
        _dispatcher_loop_selection,
        "_record_wip_capture_receipt",
        lambda **_: order.append("receipt"),
    )

    _dispatcher_loop_selection.post_run_dispositions(
        args=argparse.Namespace(close_on_merge=False),
        repo=tmp_path,
        item=WorkItem(
            id="bd-ib-xdhe5z",
            type="bug",
            status="active",
            title="Receipt order",
            description="",
            origin="freeform",
            gap_id=None,
            rank="a0",
            assignee="fabro",
            depends_on=(),
            captured_at="2026-11-06T00:00:00Z",
            resolution=None,
            reason=None,
            audit=None,
            superseded_by=None,
        ),
        outcome=DispatchOutcome(
            work_item_id="bd-ib-xdhe5z",
            status="failed",
            stage="fabro-run",
            pr_number=None,
            merge_sha=None,
            detail="terminal failure",
            fabro_run_id="01RECEIPTORDER",
        ),
        journal=_Journal(path=tmp_path / "journal.jsonl"),  # type: ignore[arg-type]
        wall_clock_seconds=1.0,
        dispatch_context_size=1,
        token_supplier=lambda: "token",
    )

    assert order == ["transition", "receipt"]
