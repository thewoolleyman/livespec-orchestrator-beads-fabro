"""The generalized dispatch-time status normalizer also clears `in_progress`.

Companion planning + CLI tests live in
`test_dispatcher_ledger_normalize_cli.py`; this file carries the single
dispatch-path expansion. `ledger_blocked_after_normalization` used to
normalize only beads-native `open` → `backlog`, leaving an `in_progress`
row flagged by the status-conformance check (dispatch blocked). It now
ALSO remaps `in_progress` (the status a raw `bd --claim` stamps) →
`active`, so a tenant whose only non-conformance is a raw claim clears
the pre-dispatch gate instead of being blocked.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_close import (
    ledger_blocked_after_normalization,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
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


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id="livespec-impl-beads-t1",
        type="task",
        status="ready",
        title="A ready task",
        description="Do the thing.",
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
        admission_policy="auto",
        acceptance_policy="ai-only",
    )
    return replace(base, **overrides)


def test_dispatch_gate_normalizes_beads_native_in_progress(tmp_path: Path) -> None:
    """A lone `in_progress` row is remapped to `active` and no longer blocks."""
    config = _config()
    append_work_item(path=config, item=_item(id="raw-claim", status="in_progress"))
    items = [_item(id="raw-claim", status="in_progress")]
    journal = JournalFile(path=tmp_path / "journal.jsonl")

    blocked = ledger_blocked_after_normalization(items=items, config=config, journal=journal)

    assert blocked is False
    assert items[0].status == "active"
