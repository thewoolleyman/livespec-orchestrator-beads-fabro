"""Unit coverage for the Dispatcher's non-convergence bounce fail-soft path.

The integration-tier journey (the marked-and-surfaced behavior bound to
SPECIFICATION/scenarios.md "Scenario 11 — Dispatcher bounces a non-converging
slice to needs-regroom") lives in
`tests/integration/test_dispatcher_non_convergence_scenario11.py`. This module
covers the fail-soft branch that integration cannot reach hermetically: a
ledger-write failure during the bounce (the verdict is already final, so the
write error is journaled as `non-convergence-bounce-error` and swallowed — the
dispatch never crashes on the escalation write).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import dispatcher
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
        status="open",
        title="A dispatched slice",
        description="Implement the slice.",
        origin="freeform",
        gap_id=None,
        priority=2,
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

    # The bounce resolves the store config and applies the label; force the
    # label write to fail (the item vanished between dispatch and bounce).
    monkeypatch.setattr(dispatcher, "_store_config", lambda *, repo: repo)
    monkeypatch.setattr(dispatcher, "enter_needs_regroom", _raise)

    # Must NOT raise — the verdict is already final.
    dispatcher._bounce_non_convergence_to_regroom(  # noqa: SLF001 — fail-soft branch under test
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
