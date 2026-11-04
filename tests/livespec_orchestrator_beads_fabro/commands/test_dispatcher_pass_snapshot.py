"""One dispatch pass reads and parses the dispatch journal at most once.

Binds the first two assertions of work-item bd-ib-6bbcda's Definition of Done:
within one dispatch pass the Dispatcher parses the journal at most once and
every pre-launch reader consumes that one snapshot, and a record the pass
appends is visible to its later readers without another read of the file.

The 2026-10-24 host profile put 98% of a pre-launch dispatcher's CPU in
re-parsing a 307 MB journal; the selection-replay lane was folded onto the
records it already held, but a dozen other pre-launch readers still each parse
the whole file for themselves. Every case here drives the REAL readers over a
real file, because a snapshot that no reader consults cannot fail a test that
only exercises the snapshot.

THE SPIES COUNT TWO THINGS. `Path.open` for reading is every way of reaching the
file -- `Path.read_text` opens through it, and so does the incremental tail
reader -- so a reader that was not moved onto the snapshot shows up as an extra
open. The snapshot's own `parse_json` is how a line is parsed, so a snapshot that
re-parsed lines on each read shows up as a count above the journal's line count.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import _acp_journal_records as acp_records
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_decision_journal as decision_journal,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_reflection_journal as reflection_journal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_journal_file import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_attribution import (
    read_journaled_runs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_session_headroom_baseline import (
    session_headroom_baseline,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMMANDS = (
    _REPO_ROOT / ".claude-plugin" / "scripts" / "livespec_orchestrator_beads_fabro" / "commands"
)
_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_MODULE = "_dispatcher_pass_snapshot"

_RECORDS = 40
_NOW = "2026-10-29T12:00:00Z"


def _snapshot() -> Any:
    """Import the pass snapshot, proving the module file exists first."""
    path = _COMMANDS / f"{_MODULE}.py"
    assert path.is_file(), f"{_MODULE}.py is not implemented yet"
    return importlib.import_module(f"{_PACKAGE}.{_MODULE}")


def _journal(*, tmp_path: Path, records: int = _RECORDS) -> JournalFile:
    journal = JournalFile(path=tmp_path / "tmp" / "fabro-dispatch-journal.jsonl")
    for index in range(records):
        journal.append(
            record={
                "stage": "dispatch-run-stamp",
                "work_item_id": f"bd-ib-item{index}",
                "run_id": f"run{index}",
            }
        )
    return journal


class _Spies:
    """How many times the journal was opened for reading and how many lines were parsed."""

    def __init__(self) -> None:
        self.opens_for_read = 0
        self.lines_parsed = 0


def _spy(*, monkeypatch: pytest.MonkeyPatch, journal: Path) -> _Spies:
    spies = _Spies()
    snapshot = _snapshot()
    real_open = Path.open
    real_parse = snapshot.parse_json

    def open_(self: Path, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if self.resolve() == journal.resolve() and "r" in mode:
            spies.opens_for_read += 1
        return real_open(self, mode, *args, **kwargs)

    def parse_json(*, text: str) -> object:
        spies.lines_parsed += 1
        return real_parse(text=text)

    monkeypatch.setattr(Path, "open", open_)
    monkeypatch.setattr(snapshot, "parse_json", parse_json)
    return spies


def _every_reader(*, path: Path) -> list[Callable[[], object]]:
    """The pre-launch readers, each as a thunk over the one journal path."""
    # Imported here: this module's own import closure reaches the dispatcher
    # engine, which is a cycle when it is the first module a process imports.
    provider_exhaustion = importlib.import_module(f"{_PACKAGE}._dispatcher_provider_exhaustion")
    return [
        lambda: reflection_journal.read_journal_records(journal_path=path),
        lambda: acp_records.journal_records(journal_path=path),
        lambda: read_journaled_runs(path=path),
        lambda: decision_journal.read_auto_disposition_decisions(journal_path=path),
        lambda: provider_exhaustion.live_provider_exhaustions(journal_path=path, now_iso=_NOW),
        lambda: session_headroom_baseline(
            journal_path=path, credential_identity="acct", now_iso=_NOW
        ),
    ]


def test_every_pre_launch_reader_shares_one_parse_of_the_journal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = _snapshot()
    journal = _journal(tmp_path=tmp_path)
    spies = _spy(monkeypatch=monkeypatch, journal=journal.path)
    with snapshot.pass_snapshot():
        for read in _every_reader(path=journal.path):
            _ = read()
        runs = read_journaled_runs(path=journal.path)
        records = reflection_journal.read_journal_records(journal_path=journal.path)
    assert spies.opens_for_read == 1
    assert spies.lines_parsed == _RECORDS
    assert len(records) == _RECORDS
    assert runs.item_id_by_run["run7"] == "bd-ib-item7"


def test_a_record_the_pass_appends_is_visible_without_reading_the_journal_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = _snapshot()
    journal = _journal(tmp_path=tmp_path)
    spies = _spy(monkeypatch=monkeypatch, journal=journal.path)
    with snapshot.pass_snapshot():
        before = reflection_journal.read_journal_records(journal_path=journal.path)
        journal.append(record={"stage": "pass-appended", "work_item_id": "bd-ib-new"})
        after = reflection_journal.read_journal_records(journal_path=journal.path)
        through_acp = acp_records.journal_records(journal_path=journal.path)
    assert len(before) == _RECORDS
    assert [record["stage"] for record in after][-1] == "pass-appended"
    assert len(after) == _RECORDS + 1
    assert len(through_acp) == _RECORDS + 1
    assert spies.opens_for_read == 1
    assert spies.lines_parsed == _RECORDS


def test_nothing_is_retained_outside_a_pass(tmp_path: Path) -> None:
    snapshot = _snapshot()
    journal = _journal(tmp_path=tmp_path)
    assert snapshot.snapshot_records(journal_path=journal.path) is None
    first = reflection_journal.read_journal_records(journal_path=journal.path)
    with journal.path.open("a", encoding="utf-8") as handle:
        _ = handle.write('{"stage": "written-by-another-process"}\n')
    second = reflection_journal.read_journal_records(journal_path=journal.path)
    assert len(second) == len(first) + 1
    with snapshot.pass_snapshot():
        assert len(snapshot.snapshot_records(journal_path=journal.path)) == _RECORDS + 1
    assert snapshot.snapshot_records(journal_path=journal.path) is None


def test_releasing_the_snapshot_returns_every_reader_to_its_own_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = _snapshot()
    journal = _journal(tmp_path=tmp_path)
    spies = _spy(monkeypatch=monkeypatch, journal=journal.path)
    with snapshot.pass_snapshot():
        _ = reflection_journal.read_journal_records(journal_path=journal.path)
        snapshot.release_pass_snapshot()
        assert snapshot.snapshot_records(journal_path=journal.path) is None
        _ = reflection_journal.read_journal_records(journal_path=journal.path)
    assert spies.opens_for_read == 2
