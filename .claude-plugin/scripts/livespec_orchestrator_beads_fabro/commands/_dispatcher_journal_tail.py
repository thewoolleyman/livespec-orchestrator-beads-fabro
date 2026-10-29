"""Reading the append-only dispatch journal by its tail instead of in full.

The journal grows without bound and is read by many Dispatcher loops. Measured
2026-10-26, a 163 MB journal cost about 2.5 CPU-seconds per full parse, and seven
loops re-parsed it on every read. Because the file is append-only, a reader that
already holds the parsed prefix only needs the bytes written since.

THE CACHE KEY IS THE FILE'S IDENTITY, SIZE AND MODIFICATION TIME. A read that
finds all three unchanged reads nothing. A read that finds the file longer reads
from the last consumed offset. A read that finds the file SHORTER than the cached
size (truncation or rotation), a different inode (replacement), or the same size
at a different modification time (rewritten in place) discards the cache and
reads from the start, because none of those is an append and a cache extended
across one would describe a file that no longer exists.

ONLY COMPLETE LINES ADVANCE THE OFFSET. A concurrent append can be observed
half-written, and a half-written line parsed and then consumed would be lost for
ever once its remainder arrived. The unterminated tail is therefore parsed for
THIS read's answer (the previous whole-file reader returned a valid last line
with no trailing newline, and a test or a crash can leave exactly that) and
re-read, from the same offset, by the next one.

A LINE THAT IS NOT A JSON OBJECT IS SKIPPED rather than raised, for the reason
`_acp_journal_records` gives: the journal is shared by every dispatcher stage, so
one torn line must not make the whole file unreadable. An unreadable file yields
no records, the same posture every previous reader took.

THE JOURNAL IS ASSUMED APPEND-ONLY. A file REWRITTEN IN PLACE to a longer length
inside one modification-time tick, with the same inode, is indistinguishable from
an append by the three keys above and would be read from the stale offset; the
only writer, `JournalFile.append`, never does that, and rotation replaces the
inode.

THE RETURNED RECORDS ARE SHARED across callers of one process and MUST be treated
as read-only.
"""

from __future__ import annotations

import os
import stat as stat_module
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.effects import (
    AttemptFailure,
    JsonParseFailure,
    attempt,
    parse_json,
)

__all__: list[str] = [
    "JournalTailRead",
    "journal_tail_records",
    "read_journal_tail",
]

_NEWLINE = b"\n"


@dataclass(frozen=True, kw_only=True)
class JournalTailRead:
    """The journal's records and how many bytes of the file this read consumed."""

    records: tuple[dict[str, object], ...]
    bytes_read: int


@dataclass(kw_only=True)
class _Tail:
    inode: int
    size: int
    mtime_ns: int
    offset: int
    committed: list[dict[str, object]] = field(default_factory=list)
    view: tuple[dict[str, object], ...] = ()


_LOCK = threading.Lock()
_TAILS: dict[str, _Tail] = {}


def journal_tail_records(*, journal_path: Path) -> tuple[dict[str, object], ...]:
    """Every parseable JSON-object line of the journal, in append order."""
    return read_journal_tail(journal_path=journal_path).records


def read_journal_tail(*, journal_path: Path) -> JournalTailRead:
    """The journal's records, reading only the bytes appended since the last read."""
    key = str(journal_path)
    with _LOCK:
        observed = attempt(action=journal_path.stat, exceptions=(OSError,))
        if isinstance(observed, AttemptFailure) or not stat_module.S_ISREG(observed.st_mode):
            _ = _TAILS.pop(key, None)
            return JournalTailRead(records=(), bytes_read=0)
        tail = _TAILS.get(key)
        if tail is not None and _unchanged(tail=tail, observed=observed):
            return JournalTailRead(records=tail.view, bytes_read=0)
        if tail is None or not _is_append(tail=tail, observed=observed):
            tail = _Tail(
                inode=observed.st_ino,
                size=0,
                mtime_ns=observed.st_mtime_ns,
                offset=0,
            )
        start = tail.offset
        chunk = attempt(
            action=lambda: _read_span(path=journal_path, start=start, end=observed.st_size),
            exceptions=(OSError,),
        )
        if isinstance(chunk, AttemptFailure):
            _ = _TAILS.pop(key, None)
            return JournalTailRead(records=(), bytes_read=0)
        whole, _separator, fragment = chunk.rpartition(_NEWLINE)
        consumed = len(chunk) - len(fragment)
        tail.committed.extend(_records_of(data=whole))
        tail.offset += consumed
        tail.size = observed.st_size
        tail.mtime_ns = observed.st_mtime_ns
        tail.inode = observed.st_ino
        tail.view = (*tail.committed, *_records_of(data=fragment))
        _TAILS[key] = tail
        return JournalTailRead(records=tail.view, bytes_read=len(chunk))


def _unchanged(*, tail: _Tail, observed: os.stat_result) -> bool:
    return (
        tail.inode == observed.st_ino
        and tail.size == observed.st_size
        and tail.mtime_ns == observed.st_mtime_ns
    )


def _is_append(*, tail: _Tail, observed: os.stat_result) -> bool:
    return tail.inode == observed.st_ino and tail.size < observed.st_size


def _read_span(*, path: Path, start: int, end: int) -> bytes:
    with path.open("rb") as handle:
        _ = handle.seek(start)
        return handle.read(max(end - start, 0))


def _records_of(*, data: bytes) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for line in data.split(_NEWLINE):
        parsed = parse_json(text=line.decode("utf-8", errors="replace"))
        if isinstance(parsed, JsonParseFailure) or not isinstance(parsed, dict):
            continue
        records.append(cast("dict[str, object]", parsed))
    return records
