"""Unit coverage for the Dispatcher's non-convergence bounce fail-soft path.

The integration-tier journey (the bounced-and-surfaced behavior bound to
SPECIFICATION/scenarios.md "Scenario 11 — Dispatcher bounces a non-converging
slice to needs-regroom") lives in
`tests/integration/test_dispatcher_non_convergence_scenario11.py`. This module
covers the fail-soft branch that integration cannot reach hermetically: a
ledger-write failure during the bounce-to-backlog (the verdict is already
final, so the write error is journaled as `non-convergence-bounce-error` and
swallowed — the dispatch never crashes on the escalation write).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_blocked, _dispatcher_completion
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.errors import WorkItemNotFoundError
from livespec_orchestrator_beads_fabro.types import WorkItem


@dataclass(kw_only=True)
class _RecordingJournal:
    """A `JournalFile` stand-in that records every appended record."""

    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _item() -> WorkItem:
    return WorkItem(
        id="livespec-impl-beads-slice1",
        type="task",
        status="ready",
        title="A dispatched slice",
        description="Implement the slice.",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-06-11T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _stalled_outcome(*, item_id: str) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=item_id,
        status="stalled-no-progress",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail="run made no progress for the full stall window",
    )


def test_bounce_failsoft_journals_error_when_ledger_write_raises(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A ledger-write failure during the bounce is journaled, never raised."""
    item = _item()
    journal = _RecordingJournal()

    def _raise(**_kwargs: object) -> None:
        raise WorkItemNotFoundError(item_id=item.id)

    # The bounce resolves the store config and transitions to backlog; force
    # the status write to fail (the item vanished between dispatch and bounce).
    monkeypatch.setattr(_dispatcher_completion, "store_config", lambda *, repo: repo)
    monkeypatch.setattr(_dispatcher_completion, "update_work_item_status", _raise)

    # Must NOT raise — the verdict is already final.
    _dispatcher_completion.bounce_non_convergence_to_backlog(
        repo=tmp_path,
        item=item,
        outcome=_stalled_outcome(item_id=item.id),
        journal=journal,
    )

    error_records = [r for r in journal.records if r.get("stage") == "non-convergence-bounce-error"]
    assert len(error_records) == 1
    assert error_records[0]["work_item_id"] == item.id
    assert error_records[0]["reason"] == "WorkItemNotFoundError"
    # The success-path bounce record is NOT written when the label write failed.
    assert not any(r.get("stage") == "non-convergence-bounce" for r in journal.records)


def test_needs_human_block_failsoft_journals_error_when_ledger_write_raises(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    item = _item()
    journal = _RecordingJournal()

    def _raise(**_kwargs: object) -> None:
        raise WorkItemNotFoundError(item_id=item.id)

    monkeypatch.setattr(_dispatcher_blocked, "store_config", lambda *, repo: repo)
    monkeypatch.setattr(_dispatcher_blocked, "update_work_item_blocked_state", _raise)

    _dispatcher_blocked.escalate_needs_human_block(
        repo=tmp_path,
        item=item,
        outcome=DispatchOutcome(
            work_item_id=item.id,
            status="blocked",
            stage="fabro-run",
            pr_number=None,
            merge_sha=None,
            detail="human gate",
        ),
        journal=journal,
    )

    assert journal.records == [
        {
            "stage": "needs-human-blocked-error",
            "work_item_id": item.id,
            "reason": "WorkItemNotFoundError",
        }
    ]
