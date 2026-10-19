"""One instant read off a Fabro run record, under a caller's candidate keys.

Extracted VERBATIM from `_dispatcher_reconcile_runs_grace` when the whole-run
wall budget became the second consumer of the same reading. That module owns
the BOUNDED SLOT HOLD -- which key names a park, what an unmeasurable park
costs, and the grace it is graded against -- while this owns the mechanics
both consumers share: search a run record and its nested state sub-objects
under an ordered key list, and coerce whatever is found to epoch seconds.
Each consumer keeps its OWN key list, because which key names the instant is
the whole of what the two disagree about.

THE SEARCH IS A SEARCH AND NOT A SCHEMA, and that is the property an editor
must not harden. Which key the pinned Fabro build actually emits was NOT
verifiable where either consumer was written: the implementation sandbox
reaches no factory, and no captured `inspect` payload exists anywhere in this
repository. Both key lists are therefore ordered most-specific-first and both
callers fail CLOSED on an unmatched record -- the grace arm holds the run
rather than reaping it, and the budget leaves its clock unfixed rather than
dating it from a guess. Replacing the search with one known key would convert
an unrecognised schema from a safe no-op into a confident wrong number.

THE NESTED SUB-OBJECTS ARE SEARCHED BESIDE THE RECORD ITSELF because Fabro
reports a run's state as `status: {kind: ...}`, so an instant that belongs to
the STATE rather than to the run is likelier to live there than at the top
level.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import timezone
from typing import Any, cast

from livespec_orchestrator_beads_fabro.effects import IsoDatetimeParseFailure, parse_iso_datetime

__all__: list[str] = [
    "NESTED_RECORD_KEYS",
    "record_instant_epoch",
]

# Sub-objects of the run record searched beside the record itself. Fabro
# reports a run's state as `status: {kind: ...}`, so a timestamp that belongs
# to the state rather than to the run is likelier to live there.
NESTED_RECORD_KEYS: tuple[str, ...] = ("status", "checkpoint")


def record_instant_epoch(
    *,
    record: Mapping[str, Any] | None,
    keys: Sequence[str],
) -> float | None:
    """The first instant one run record carries under `keys`, as epoch seconds.

    `keys` is walked in the caller's own order, MOST SPECIFIC FIRST, and the
    record itself is searched before its nested sub-objects for each key --
    so a caller's preference between two keys is never overridden by where in
    the record one of them happened to sit.

    None when no key matched anywhere, which is the UNMEASURED answer both
    consumers fail closed on.
    """
    candidates = _candidate_records(record=record)
    for key in keys:
        for candidate in candidates:
            epoch = _epoch_value(value=candidate.get(key))
            if epoch is not None:
                return epoch
    return None


def _candidate_records(*, record: Mapping[str, Any] | None) -> tuple[Mapping[str, Any], ...]:
    if record is None:
        return ()
    nested = [
        cast("Mapping[str, Any]", record[key])
        for key in NESTED_RECORD_KEYS
        if isinstance(record.get(key), dict)
    ]
    return (record, *nested)


def _epoch_value(*, value: object) -> float | None:
    # `bool` is an `int`, and `True` would read as the epoch's first second.
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        return _iso_epoch(text=value)
    return None


def _iso_epoch(*, text: str) -> float | None:
    normalized = f"{text.removesuffix('Z')}+00:00" if text.endswith("Z") else text
    parsed = parse_iso_datetime(text=normalized)
    if isinstance(parsed, IsoDatetimeParseFailure):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc).timestamp()
    return parsed.timestamp()
