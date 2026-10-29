"""Every dispatch-journal reader re-reads only the bytes appended since its last read."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands._acp_journal_records import (
    journal_records as acp_journal_records,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_decision_journal import (
    read_auto_disposition_decisions,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_journal_rows import (
    journal_records as stall_journal_records,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_probe_cycle import (
    journal_records as probe_journal_records,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection_journal import (
    read_journal_records,
)

_Reader = Callable[[Path], tuple[Mapping[str, Any], ...]]

_READERS: dict[str, _Reader] = {
    "reflection": lambda path: read_journal_records(journal_path=path),
    "acp": lambda path: acp_journal_records(journal_path=path),
    "probe-cycle": lambda path: probe_journal_records(journal_path=path),
    "stall-disposition": lambda path: stall_journal_records(journal=JournalFile(path=path)),
    "auto-disposition": lambda path: read_auto_disposition_decisions(journal_path=path),
}


@dataclass(kw_only=True)
class _CountingHandle:
    handle: Any
    reads: list[int]

    def __enter__(self) -> _CountingHandle:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.handle.close()

    def read(self, size: int = -1) -> Any:
        data = self.handle.read(size)
        self.reads.append(len(data))
        return data

    def seek(self, offset: int, whence: int = 0) -> int:
        return self.handle.seek(offset, whence)


def _count_reads_of(*, monkeypatch: pytest.MonkeyPatch, target: Path) -> list[int]:
    reads: list[int] = []
    original = Path.open

    def spy(self: Path, *args: Any, **kwargs: Any) -> Any:
        handle = original(self, *args, **kwargs)
        return _CountingHandle(handle=handle, reads=reads) if self == target else handle

    monkeypatch.setattr(Path, "open", spy)
    return reads


def _line(*, n: int) -> str:
    return json.dumps({"stage": "auto-disposition", "n": n}, sort_keys=True) + "\n"


@pytest.mark.parametrize("reader_name", sorted(_READERS))
def test_a_later_read_of_the_journal_reads_only_the_appended_bytes(
    *, reader_name: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    reader = _READERS[reader_name]
    journal = tmp_path / "tmp" / "fabro-dispatch-journal.jsonl"
    journal.parent.mkdir()
    first_text = _line(n=1) + _line(n=2)
    _ = journal.write_text(first_text, encoding="utf-8")
    reads = _count_reads_of(monkeypatch=monkeypatch, target=journal)

    first = reader(journal)
    first_total = sum(reads)
    appended = _line(n=3)
    with open(journal, "a", encoding="utf-8") as handle:  # noqa: PTH123 — bypasses the Path.open spy
        _ = handle.write(appended)
    reads.clear()
    second = reader(journal)

    assert [record["n"] for record in first] == [1, 2]
    assert first_total == len(first_text.encode("utf-8"))
    assert [record["n"] for record in second] == [1, 2, 3]
    assert sum(reads) == len(appended.encode("utf-8"))
