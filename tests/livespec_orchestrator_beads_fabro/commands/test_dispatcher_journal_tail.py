"""A journal reader re-reads only what was appended since its previous read."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_journal_tail import (
    journal_tail_records,
    read_journal_tail,
)


def _line(*, n: int) -> str:
    return json.dumps({"stage": "poll", "n": n}, sort_keys=True) + "\n"


def _append(*, path: Path, text: str) -> int:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(text)
    return len(text.encode("utf-8"))


def _ns(*, records: tuple[dict[str, object], ...]) -> list[object]:
    return [record["n"] for record in records]


def test_the_first_read_parses_the_whole_file(tmp_path: Path) -> None:
    journal = tmp_path / "journal.jsonl"
    written = _append(path=journal, text=_line(n=1) + _line(n=2))

    first = read_journal_tail(journal_path=journal)

    assert _ns(records=first.records) == [1, 2]
    assert first.bytes_read == written


def test_a_later_read_reads_only_the_appended_bytes(tmp_path: Path) -> None:
    journal = tmp_path / "journal.jsonl"
    _append(path=journal, text=_line(n=1) + _line(n=2))
    _ = read_journal_tail(journal_path=journal)

    appended = _append(path=journal, text=_line(n=3))
    second = read_journal_tail(journal_path=journal)

    assert _ns(records=second.records) == [1, 2, 3]
    assert second.bytes_read == appended


def test_an_unchanged_file_is_not_read_again(tmp_path: Path) -> None:
    journal = tmp_path / "journal.jsonl"
    _append(path=journal, text=_line(n=1))
    _ = read_journal_tail(journal_path=journal)

    again = read_journal_tail(journal_path=journal)

    assert _ns(records=again.records) == [1]
    assert again.bytes_read == 0


def test_a_file_shorter_than_the_cached_size_is_re_read_from_the_start(tmp_path: Path) -> None:
    journal = tmp_path / "journal.jsonl"
    _append(path=journal, text=_line(n=1) + _line(n=2) + _line(n=3))
    _ = read_journal_tail(journal_path=journal)

    rotated = _line(n=9)
    _ = journal.write_text(rotated, encoding="utf-8")
    after = read_journal_tail(journal_path=journal)

    assert _ns(records=after.records) == [9]
    assert after.bytes_read == len(rotated.encode("utf-8"))


def test_a_file_rewritten_to_the_same_size_at_a_new_time_is_re_read(tmp_path: Path) -> None:
    journal = tmp_path / "journal.jsonl"
    _ = journal.write_text(_line(n=1), encoding="utf-8")
    stat = journal.stat()
    _ = read_journal_tail(journal_path=journal)

    _ = journal.write_text(_line(n=2), encoding="utf-8")
    os.utime(journal, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    after = read_journal_tail(journal_path=journal)

    assert _ns(records=after.records) == [2]
    assert after.bytes_read == len(_line(n=2).encode("utf-8"))


def test_a_replacement_file_larger_than_the_cached_one_is_re_read(tmp_path: Path) -> None:
    journal = tmp_path / "journal.jsonl"
    _ = journal.write_text(_line(n=1), encoding="utf-8")
    _ = read_journal_tail(journal_path=journal)

    replacement = tmp_path / "replacement.jsonl"
    _ = replacement.write_text(_line(n=7) + _line(n=8), encoding="utf-8")
    replacement.replace(journal)
    after = read_journal_tail(journal_path=journal)

    assert _ns(records=after.records) == [7, 8]
    assert after.bytes_read == len((_line(n=7) + _line(n=8)).encode("utf-8"))


def test_an_unterminated_last_line_is_returned_then_completed_without_duplication(
    tmp_path: Path,
) -> None:
    journal = tmp_path / "journal.jsonl"
    whole = _line(n=2)
    _append(path=journal, text=_line(n=1) + whole.rstrip("\n"))

    partial = read_journal_tail(journal_path=journal)
    _ = _append(path=journal, text="\n")
    completed = read_journal_tail(journal_path=journal)

    assert _ns(records=partial.records) == [1, 2]
    assert _ns(records=completed.records) == [1, 2]


def test_an_unterminated_fragment_that_is_not_json_is_left_out_until_it_is_whole(
    tmp_path: Path,
) -> None:
    journal = tmp_path / "journal.jsonl"
    _append(path=journal, text=_line(n=1) + '{"stage": "po')

    torn = read_journal_tail(journal_path=journal)
    _ = _append(path=journal, text='ll", "n": 2}\n')
    healed = read_journal_tail(journal_path=journal)

    assert _ns(records=torn.records) == [1]
    assert _ns(records=healed.records) == [1, 2]


def test_lines_that_are_not_json_objects_are_skipped(tmp_path: Path) -> None:
    journal = tmp_path / "journal.jsonl"
    _ = journal.write_bytes(b"\n[1, 2]\nnot json\n" + _line(n=1).encode("utf-8") + b"\xff\xfe\n")

    read = read_journal_tail(journal_path=journal)

    assert _ns(records=read.records) == [1]


def test_an_absent_file_yields_no_records(tmp_path: Path) -> None:
    read = read_journal_tail(journal_path=tmp_path / "absent.jsonl")

    assert read.records == ()
    assert read.bytes_read == 0


def test_a_directory_yields_no_records(tmp_path: Path) -> None:
    read = read_journal_tail(journal_path=tmp_path)

    assert read.records == ()


def test_a_file_that_cannot_be_opened_yields_no_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal = tmp_path / "journal.jsonl"
    _append(path=journal, text=_line(n=1))

    def refuse(self: Path, *_args: object, **_kwargs: object) -> object:
        raise PermissionError(str(self))

    monkeypatch.setattr(Path, "open", refuse)

    assert read_journal_tail(journal_path=journal).records == ()


def test_the_records_helper_returns_just_the_records(tmp_path: Path) -> None:
    journal = tmp_path / "journal.jsonl"
    _append(path=journal, text=_line(n=1))

    assert _ns(records=journal_tail_records(journal_path=journal)) == [1]
