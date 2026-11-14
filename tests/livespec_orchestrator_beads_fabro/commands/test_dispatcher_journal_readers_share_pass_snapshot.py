"""The admission-path journal readers take the pass snapshot instead of their own full read.

Three pre-launch readers each ran `read_text` over the whole dispatch journal and parsed
every line, past both the pass snapshot and the tail cache: the degraded-step gate, the
claim accounting behind every WIP-cap read, and the run-slot board that accounting
consults. One full parse of the 413 MB operator journal is about 10.7 CPU-seconds, and
admission and the requested-items preflight each reached those readers, so the parse
was paid again for each of them although the pass already held the records.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_live_runs import (
    current_run_factories,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_reclaim import (
    claimed_active_projection,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_pass_snapshot import (
    pass_snapshot,
    snapshot_records,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_step_persistence import (
    outstanding_degraded_step,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_ITEM_ID = "bd-ib-snapshotreaders"


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="bug",
        status="active",
        title="An active row with no live lock",
        description="Implement the slice.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-11-08T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _journal(*, tmp_path: Path) -> Path:
    path = tmp_path / "journal.jsonl"
    rows = (
        {"stage": "ledger-admit", "work_item_id": _ITEM_ID},
        {"stage": "dispatch-run-stamp", "work_item_id": _ITEM_ID, "dispatch_factory": "hp"},
        {"stage": "outcome", "outcome": {"work_item_id": _ITEM_ID, "status": "green"}},
    )
    _ = path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


def _reader_calls(*, path: Path) -> dict[str, Callable[[], object]]:
    return {
        "degraded-step": lambda: outstanding_degraded_step(journal_path=path),
        "run-factories": lambda: current_run_factories(journal_path=path),
        "claim-accounting": lambda: claimed_active_projection(
            repo=path.parent, items=[_item()], journal=JournalFile(path=path)
        ).green_terminal_active_ids,
    }


@pytest.mark.parametrize(
    ("reader", "expected"),
    [
        ("degraded-step", None),
        ("run-factories", {_ITEM_ID: "hp"}),
        ("claim-accounting", (_ITEM_ID,)),
    ],
)
def test_a_reader_inside_a_live_pass_does_not_read_the_journal_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reader: str, expected: object
) -> None:
    path = _journal(tmp_path=tmp_path)
    call = _reader_calls(path=path)[reader]
    outside_a_pass = call()
    reads: list[Path] = []
    original = Path.read_text

    def counting(self: Path, encoding: str | None = None) -> str:
        reads.append(self)
        return original(self, encoding=encoding)

    with pass_snapshot():
        assert snapshot_records(journal_path=path) is not None
        monkeypatch.setattr(Path, "read_text", counting)
        inside_a_pass = call()
        monkeypatch.setattr(Path, "read_text", original)

    assert [read for read in reads if read == path] == []
    assert outside_a_pass == expected
    assert inside_a_pass == expected
