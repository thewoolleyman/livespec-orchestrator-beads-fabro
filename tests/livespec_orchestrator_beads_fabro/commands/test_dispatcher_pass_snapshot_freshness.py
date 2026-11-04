"""The pass snapshot is never stale, and it parses each byte of the journal once.

`test_dispatcher_pass_snapshot.py` binds the two Definition-of-Done assertions the
snapshot exists for. This module binds what makes sharing one parse SAFE: a
journal another process appends to mid-pass, a journal rewritten under the pass,
a write caught half way, and every reading the snapshot cannot take, each of which
must end with a reader seeing what the file holds NOW or taking its own reading.

EVERY CASE ASKS THE FILE, never the snapshot's own bookkeeping, because a snapshot
that served a stale copy would satisfy any assertion about its own state.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_pass_snapshot as snapshot
from livespec_orchestrator_beads_fabro.commands._dispatcher_journal_file import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_observe import (
    journal_records_or_none,
)


def _line(*, marker: str) -> str:
    return json.dumps({"stage": "marker", "marker": marker}) + "\n"


def _journal(*, tmp_path: Path, markers: tuple[str, ...]) -> Path:
    path = tmp_path / "journal.jsonl"
    path.write_text("".join(_line(marker=marker) for marker in markers), encoding="utf-8")
    return path


def _markers(*, path: Path) -> list[object]:
    records = snapshot.snapshot_records(journal_path=path)
    assert records is not None
    return [record["marker"] for record in records]


def _count_parses(*, monkeypatch: pytest.MonkeyPatch) -> list[int]:
    count = [0]
    real = snapshot.parse_json

    def counting(*, text: str) -> object:
        count[0] += 1
        return real(text=text)

    monkeypatch.setattr(snapshot, "parse_json", counting)
    return count


def test_a_line_another_process_appends_is_seen_and_only_it_is_parsed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _journal(tmp_path=tmp_path, markers=("a", "b"))
    parsed = _count_parses(monkeypatch=monkeypatch)
    with snapshot.pass_snapshot():
        assert _markers(path=path) == ["a", "b"]
        with path.open("a", encoding="utf-8") as handle:
            _ = handle.write(_line(marker="c"))
        assert _markers(path=path) == ["a", "b", "c"]
        assert _markers(path=path) == ["a", "b", "c"]
    assert parsed[0] == 3


def test_a_journal_rewritten_shorter_under_the_pass_is_read_afresh(tmp_path: Path) -> None:
    path = _journal(tmp_path=tmp_path, markers=("a", "b", "c", "d"))
    with snapshot.pass_snapshot():
        assert _markers(path=path) == ["a", "b", "c", "d"]
        path.write_text(_line(marker="z"), encoding="utf-8")
        assert _markers(path=path) == ["z"]


def test_a_journal_rewritten_longer_with_other_content_is_read_afresh(tmp_path: Path) -> None:
    path = _journal(tmp_path=tmp_path, markers=("a", "b"))
    with snapshot.pass_snapshot():
        assert _markers(path=path) == ["a", "b"]
        path.write_text("".join(_line(marker=marker) for marker in ("x", "y", "z", "w")))
        assert _markers(path=path) == ["x", "y", "z", "w"]


def test_a_final_line_without_a_newline_is_read_and_not_consumed(tmp_path: Path) -> None:
    path = _journal(tmp_path=tmp_path, markers=("a",))
    unfinished = json.dumps({"stage": "marker", "marker": "b"})
    with path.open("a", encoding="utf-8") as handle:
        _ = handle.write(unfinished)
    with snapshot.pass_snapshot():
        assert _markers(path=path) == ["a", "b"]
        assert _markers(path=path) == ["a", "b"]
        with path.open("a", encoding="utf-8") as handle:
            _ = handle.write("\n" + _line(marker="c"))
        assert _markers(path=path) == ["a", "b", "c"]


def test_an_unparseable_final_fragment_is_ignored(tmp_path: Path) -> None:
    path = _journal(tmp_path=tmp_path, markers=("a",))
    with path.open("a", encoding="utf-8") as handle:
        _ = handle.write('{"stage": "mark')
    with snapshot.pass_snapshot():
        assert _markers(path=path) == ["a"]


def test_lines_that_are_not_objects_are_skipped(tmp_path: Path) -> None:
    path = tmp_path / "journal.jsonl"
    path.write_text(f"not json\n[1, 2]\n{_line(marker='a')}\n", encoding="utf-8")
    with snapshot.pass_snapshot():
        assert _markers(path=path) == ["a"]


def test_an_absent_journal_is_empty_until_it_exists(tmp_path: Path) -> None:
    path = tmp_path / "journal.jsonl"
    with snapshot.pass_snapshot():
        assert snapshot.snapshot_records(journal_path=path) == ()
        path.write_text(_line(marker="a"), encoding="utf-8")
        assert _markers(path=path) == ["a"]
        path.unlink()
        assert snapshot.snapshot_records(journal_path=path) == ()


def test_a_journal_that_cannot_be_read_is_left_to_each_reader(tmp_path: Path) -> None:
    path = tmp_path / "journal.jsonl"
    path.write_bytes(b"\xff\xfe\n")
    with snapshot.pass_snapshot():
        assert snapshot.snapshot_records(journal_path=path) is None
        path.write_text(_line(marker="a"), encoding="utf-8")
        assert _markers(path=path) == ["a"]


def test_an_unreadable_file_is_left_to_each_reader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _journal(tmp_path=tmp_path, markers=("a",))

    def refuse(**_kwargs: Any) -> bytes:
        raise PermissionError("denied")

    monkeypatch.setattr(snapshot, "_read_from", refuse)
    with snapshot.pass_snapshot():
        assert snapshot.snapshot_records(journal_path=path) is None


def test_no_path_and_no_pass_answer_none(tmp_path: Path) -> None:
    path = _journal(tmp_path=tmp_path, markers=("a",))
    with snapshot.pass_snapshot():
        assert snapshot.snapshot_records(journal_path=None) is None
    assert snapshot.snapshot_records(journal_path=path) is None


def test_a_nested_pass_joins_the_outer_one_and_the_outer_one_ends_it(tmp_path: Path) -> None:
    path = _journal(tmp_path=tmp_path, markers=("a",))
    with snapshot.pass_snapshot():
        with snapshot.pass_snapshot():
            assert _markers(path=path) == ["a"]
        assert _markers(path=path) == ["a"]
    assert snapshot.snapshot_records(journal_path=path) is None


def test_releasing_outside_a_pass_changes_nothing(tmp_path: Path) -> None:
    path = _journal(tmp_path=tmp_path, markers=("a",))
    snapshot.release_pass_snapshot()
    with snapshot.pass_snapshot():
        assert _markers(path=path) == ["a"]


def test_a_released_pass_stays_released_until_the_next_pass(tmp_path: Path) -> None:
    path = _journal(tmp_path=tmp_path, markers=("a",))
    journal = JournalFile(path=path)
    with snapshot.pass_snapshot():
        assert _markers(path=path) == ["a"]
        snapshot.release_pass_snapshot()
        journal.append(record={"stage": "marker", "marker": "b"})
        assert snapshot.snapshot_records(journal_path=path) is None
    with snapshot.pass_snapshot():
        assert _markers(path=path) == ["a", "b"]


def test_an_append_before_the_first_read_is_simply_read_later(tmp_path: Path) -> None:
    path = _journal(tmp_path=tmp_path, markers=("a",))
    journal = JournalFile(path=path)
    with snapshot.pass_snapshot():
        journal.append(record={"stage": "marker", "marker": "b"})
        assert _markers(path=path) == ["a", "b"]


def _status(*, path: Path) -> os.stat_result:
    return path.stat()


def test_an_append_that_lands_after_another_writers_is_read_from_the_file(
    tmp_path: Path,
) -> None:
    path = _journal(tmp_path=tmp_path, markers=("a",))
    size = path.stat().st_size
    with snapshot.pass_snapshot():
        assert _markers(path=path) == ["a"]
        with path.open("a", encoding="utf-8") as handle:
            _ = handle.write(_line(marker="other"))
            _ = handle.write(_line(marker="mine"))
        snapshot.record_journal_append(
            path=path,
            start=size,
            line=_line(marker="mine").encode("utf-8"),
            status=_status(path=path),
        )
        assert _markers(path=path) == ["a", "other", "mine"]


def test_an_append_whose_file_grew_by_more_than_the_line_is_read_from_the_file(
    tmp_path: Path,
) -> None:
    path = _journal(tmp_path=tmp_path, markers=("a",))
    size = path.stat().st_size
    with snapshot.pass_snapshot():
        assert _markers(path=path) == ["a"]
        line = _line(marker="mine")
        with path.open("a", encoding="utf-8") as handle:
            _ = handle.write(line)
            _ = handle.write(_line(marker="after"))
        snapshot.record_journal_append(
            path=path, start=size, line=line.encode("utf-8"), status=_status(path=path)
        )
        assert _markers(path=path) == ["a", "mine", "after"]


def test_an_appended_line_that_is_not_an_object_joins_nothing(tmp_path: Path) -> None:
    path = _journal(tmp_path=tmp_path, markers=("a",))
    size = path.stat().st_size
    with snapshot.pass_snapshot():
        assert _markers(path=path) == ["a"]
        line = b"[1]\n"
        with path.open("ab") as handle:
            _ = handle.write(line)
        snapshot.record_journal_append(path=path, start=size, line=line, status=_status(path=path))
        assert _markers(path=path) == ["a"]


def test_an_append_outside_any_pass_is_ignored(tmp_path: Path) -> None:
    path = _journal(tmp_path=tmp_path, markers=("a",))
    JournalFile(path=path).append(record={"stage": "marker", "marker": "b"})
    with snapshot.pass_snapshot():
        assert _markers(path=path) == ["a", "b"]


def test_a_stranded_claim_reader_consumes_the_pass_snapshot(tmp_path: Path) -> None:
    path = _journal(tmp_path=tmp_path, markers=("a", "b"))
    with snapshot.pass_snapshot():
        records = journal_records_or_none(journal_path=path)
    assert records is not None
    assert [record["marker"] for record in records] == ["a", "b"]
