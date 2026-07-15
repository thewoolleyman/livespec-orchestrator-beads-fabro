"""Focused tests for dispatcher needs-human blocking edge cases."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_needs_human_block as needs_human_block,
)
from livespec_orchestrator_beads_fabro.errors import WorkItemNotFoundError
from livespec_orchestrator_beads_fabro.types import WorkItem


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id="bd-ib-block-error",
        type="task",
        status="active",
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
        admission_policy="auto",
        acceptance_policy="ai-only",
    )
    return replace(base, **overrides)


@dataclass(kw_only=True)
class _RecordingJournal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def test_block_needs_human_failsoft_journals_expected_store_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    item = _item()
    journal = _RecordingJournal()

    def _raise(**_kwargs: object) -> None:
        raise WorkItemNotFoundError(item_id=item.id)

    monkeypatch.setattr(needs_human_block, "store_config", lambda *, repo: repo)
    monkeypatch.setattr(needs_human_block, "update_work_item_blocked_reason", _raise)

    needs_human_block.block_needs_human(
        repo=tmp_path, item=item, reason="operator judgment needed", journal=journal
    )

    assert journal.records == [
        {
            "stage": "needs-human-block-error",
            "work_item_id": item.id,
            "reason": "WorkItemNotFoundError",
        }
    ]
