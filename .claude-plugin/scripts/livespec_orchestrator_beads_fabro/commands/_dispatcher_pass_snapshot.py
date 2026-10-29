"""One dispatch pass's single parsed snapshot of the append-only dispatch journal.

The dispatch journal is the one file every pre-launch reader consults, and on
the operator host it was 307 MB. Each reader used to take its own copy --
`read_text`, split, parse every line -- so a single dispatch parsed the whole
file once per reader (and, before the selection-replay lane was folded onto the
records it already held, once per warning and per attempt as well). The host
profile of 2026-10-24 put 98% of a pre-launch dispatcher's CPU there.

WITHIN A PASS EACH BYTE OF THE JOURNAL IS PARSED AT MOST ONCE. `pass_snapshot`
opens the scope; every reader that asks `snapshot_records` for a path inside
it receives the same parsed records. The scope is process-wide rather than
per-thread because the drain dispatches on worker threads and every one of them
reads the same file.

THE SNAPSHOT IS NEVER STALE, and that is what makes it safe to share:

- A record this process appends through `JournalFile` is handed to
  `record_journal_append` and joins the snapshot in memory, so a later reader in
  the pass sees it without the file being read again.
- A record another process appends changes the file's `stat`, and the next
  read then parses only the new bytes, starting from the offset the snapshot
  already holds. An unchanged `stat` costs no read at all.
- The consumed prefix is anchored by its last bytes. A file that was rewritten
  or truncated under the snapshot no longer matches its anchor, and the
  snapshot is rebuilt from the start rather than extended from a wrong offset.
- A final line with no terminating newline is a write in flight, or a crash
  mid-append. It is parsed for the reader that asked but is not consumed, so
  the bytes that complete it are parsed whole when they arrive.

THE SAME SCOPE ALSO MEMOIZES `fabro inspect`, one reading per factory and run
(`memoized_inspection`). The pre-launch readers each open their own port onto the
same factory, so the only unit they share is the pair, and a pass asked the
factory about one run once per reader. A failed reading is memoized too: the
pass has been told the factory could not answer, and asking again inside the
same pass does not make the answer fresher. `forget_inspection` drops one pair,
because a removed run is no longer what was read.

`release_pass_snapshot` ends the snapshot at the launch, because the memory it
holds is a pre-launch cost and a run can last hours. After it, and outside any
scope, `snapshot_records` answers `None` and every reader falls back to its own
read -- the behaviour each one had before this module existed.

THE RECORDS ARE SHARED, NOT COPIED. A reader must treat them as read-only.

Anything this module cannot read -- an unreadable file, bytes that are not
UTF-8 -- answers `None` too, so each reader keeps its own account of that
failure instead of this module inventing one for all of them.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeVar, cast

from livespec_orchestrator_beads_fabro.effects import (
    AttemptFailure,
    JsonParseFailure,
    attempt,
    parse_json,
)

__all__: list[str] = [
    "forget_inspection",
    "memoized_inspection",
    "pass_snapshot",
    "record_journal_append",
    "release_pass_snapshot",
    "snapshot_records",
]

_ANCHOR_BYTES = 64

_StatKey = tuple[int, int, int]

_Reading = TypeVar("_Reading")


@dataclass(kw_only=True)
class _Cursor:
    """What has been consumed of one journal file, and where the next read starts."""

    offset: int = 0
    anchor: bytes = b""
    stat_key: _StatKey | None = None
    records: list[dict[str, object]] = field(default_factory=list)
    view: tuple[dict[str, object], ...] | None = None
    tail: tuple[dict[str, object], ...] = ()


@dataclass(kw_only=True)
class _Scope:
    depth: int = 0
    live: bool = True
    cursors: dict[Path, _Cursor] = field(default_factory=dict)
    inspections: dict[tuple[str, str], object] = field(default_factory=dict)


@dataclass(kw_only=True)
class _Holder:
    scope: _Scope | None = None


_HOLDER = _Holder()
_LOCK = threading.RLock()


@contextmanager
def pass_snapshot() -> Iterator[None]:
    """Open the dispatch pass's snapshot scope; a nested open joins the outer one."""
    with _LOCK:
        scope = _HOLDER.scope
        if scope is None:
            scope = _Scope()
            _HOLDER.scope = scope
        scope.depth += 1
    try:
        yield
    finally:
        with _LOCK:
            scope.depth -= 1
            if scope.depth == 0:
                _HOLDER.scope = None


def release_pass_snapshot() -> None:
    """End the snapshot for the rest of the scope and free what it holds."""
    with _LOCK:
        scope = _HOLDER.scope
        if scope is not None:
            scope.live = False
            scope.cursors.clear()
            scope.inspections.clear()


def memoized_inspection(*, factory: str, run_id: str, read: Callable[[], _Reading]) -> _Reading:
    """`read()` once per factory and run inside a live pass; every call outside one reads."""
    with _LOCK:
        scope = _HOLDER.scope
        if scope is None or not scope.live:
            return read()
        key = (factory, run_id)
        if key not in scope.inspections:
            scope.inspections[key] = read()
        return cast("_Reading", scope.inspections[key])


def forget_inspection(*, factory: str, run_id: str) -> None:
    """Drop what the pass read of one run, so its next inspection asks the factory."""
    with _LOCK:
        scope = _HOLDER.scope
        if scope is not None:
            _ = scope.inspections.pop((factory, run_id), None)


def snapshot_records(*, journal_path: Path | None) -> tuple[dict[str, object], ...] | None:
    """The journal's parsed records inside a live pass, else `None`.

    An absent file is the empty sequence, as it is for every reader. `None`
    means "take your own reading": no live pass, or a file this module could not
    read.
    """
    if journal_path is None:
        return None
    with _LOCK:
        scope = _HOLDER.scope
        if scope is None or not scope.live:
            return None
        key = journal_path.resolve()
        if not key.is_file():
            _ = scope.cursors.pop(key, None)
            return ()
        cursor = scope.cursors.setdefault(key, _Cursor())
        extended = attempt(
            action=lambda: _extend(cursor=cursor, path=key), exceptions=(OSError, ValueError)
        )
        if isinstance(extended, AttemptFailure):
            _ = scope.cursors.pop(key, None)
            return None
        return extended


def record_journal_append(*, path: Path, start: int, line: bytes, status: os.stat_result) -> None:
    """Fold a record this process just appended into the snapshot, if it is current.

    `start` is the file's size just before the write and `status` is the file
    as the writer's own handle saw it just after. The record joins the snapshot
    only when the snapshot had consumed exactly up to `start` AND the write
    grew the file by exactly this line; otherwise another writer got in between,
    and the next read parses the gap from the file, this line included.
    """
    with _LOCK:
        scope = _HOLDER.scope
        if scope is None or not scope.live:
            return
        cursor = scope.cursors.get(path.resolve())
        end = start + len(line)
        if cursor is None or cursor.offset != start or status.st_size != end:
            return
        record = _as_record(parsed=json.loads(line))
        if record is None:
            return
        cursor.records.append(record)
        cursor.offset = end
        cursor.anchor = (cursor.anchor + line)[-_ANCHOR_BYTES:]
        cursor.stat_key = _key_of(status=status)
        cursor.view = None
        cursor.tail = ()


def _extend(*, cursor: _Cursor, path: Path) -> tuple[dict[str, object], ...]:
    """Bring `cursor` up to the file's end, parsing only bytes not yet consumed."""
    key = _key_of(status=path.stat())
    if cursor.stat_key != key:
        fresh = _fresh_bytes(cursor=cursor, path=path)
        cut = fresh.rfind(b"\n") + 1
        complete = fresh[:cut]
        for line in complete.decode("utf-8").splitlines():
            record = _as_record(parsed=parse_json(text=line))
            if record is not None:
                cursor.records.append(record)
        cursor.offset += cut
        cursor.anchor = (cursor.anchor + complete)[-_ANCHOR_BYTES:]
        cursor.stat_key = key
        cursor.view = None
        cursor.tail = _unfinished_line(fragment=fresh[cut:])
    if cursor.view is None:
        cursor.view = tuple(cursor.records)
    return cursor.view + cursor.tail


def _fresh_bytes(*, cursor: _Cursor, path: Path) -> bytes:
    """Every byte past the consumed prefix, rebuilding the cursor if the prefix changed."""
    anchored = _read_from(path=path, start=max(0, cursor.offset - _ANCHOR_BYTES))
    held = len(cursor.anchor)
    if anchored[:held] != cursor.anchor:
        cursor.offset = 0
        cursor.anchor = b""
        cursor.records.clear()
        return _read_from(path=path, start=0)
    return anchored[held:]


def _unfinished_line(*, fragment: bytes) -> tuple[dict[str, object], ...]:
    """The newline-less final line as a record, when it already parses."""
    if not fragment:
        return ()
    record = _as_record(parsed=parse_json(text=fragment.decode("utf-8")))
    return () if record is None else (record,)


def _read_from(*, path: Path, start: int) -> bytes:
    with path.open("rb") as handle:
        _ = handle.seek(start)
        return handle.read()


def _key_of(*, status: os.stat_result) -> _StatKey:
    return (status.st_ino, status.st_size, status.st_mtime_ns)


def _as_record(*, parsed: object) -> dict[str, object] | None:
    if isinstance(parsed, JsonParseFailure) or not isinstance(parsed, dict):
        return None
    return {str(key): value for key, value in cast("dict[object, object]", parsed).items()}
