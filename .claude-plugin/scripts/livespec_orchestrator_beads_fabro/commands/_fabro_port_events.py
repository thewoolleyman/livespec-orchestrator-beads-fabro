"""The `fabro events --json` output as event records, whatever container it uses.

ONE reader for the whole repository, because two readers of the same bytes
cannot be proven to agree and the disagreement would be invisible: each would
return a well-formed list of events. The stall watchdog reads these records for
their timestamps and the port hands them on as its events payload; both go
through here.

THREE CONTAINERS, all measured rather than assumed. The pinned 0.254 build
prints a JSON ARRAY, and a server-side payload wraps the same array under
`events` — the two shapes `_acp_fallback_events` already tolerates for the same
reason. The Petri-era build (v0.378.0-nightly.0, research note 006) prints "a
stream of envelopes", each carrying a `stream_seq`, so the records can arrive
one JSON object per LINE; the enemy-test harness has carried a line-parsing
fallback for that case since before this reader existed.

AN UNREADABLE STREAM IS `None`, AND AN EMPTY ONE IS `()`. "Read failure is not
absence" is the governing rule for every consumer here: a run whose probe
errored and a run that has emitted nothing yet support opposite conclusions —
one is unmeasured, the other is measured and quiet — and collapsing them into
an empty tuple would let a probe outage read as a healthy, silent run.
"""

from __future__ import annotations

from typing import Any, cast

from livespec_orchestrator_beads_fabro.effects import JsonParseFailure, parse_json

__all__: list[str] = [
    "fabro_event_records_from_stdout",
]


def fabro_event_records_from_stdout(*, stdout: str) -> tuple[dict[str, Any], ...] | None:
    """The stream's event records, or None when nothing in it was readable."""
    parsed = parse_json(text=stdout)
    if isinstance(parsed, JsonParseFailure):
        return _line_delimited_records(stdout=stdout)
    return _records_from_payload(payload=parsed)


def _records_from_payload(*, payload: object) -> tuple[dict[str, Any], ...] | None:
    """The records a single parsed JSON document carries, or None.

    A bare mapping with no `events` key is ONE record: a one-envelope stream
    parses as an object rather than as an array, and the enemy harness reads it
    that way too. A scalar document is not a stream in any measured shape, so it
    is unreadable rather than empty.
    """
    if isinstance(payload, list):
        return _mappings(values=cast("list[object]", payload))
    if not isinstance(payload, dict):
        return None
    mapping = cast("dict[str, Any]", payload)
    events: object = mapping.get("events")
    if isinstance(events, list):
        return _mappings(values=cast("list[object]", events))
    return (mapping,)


def _line_delimited_records(*, stdout: str) -> tuple[dict[str, Any], ...] | None:
    """The records of a newline-delimited stream, or None when no line parsed.

    A line that is not a JSON object is SKIPPED rather than fatal — a stream
    truncated mid-record by a probe timeout still carries every record before
    the cut, and discarding those would turn a partial read into no signal at
    all. A blank line lands in that same arm, so it needs no case of its own.
    If NO line yields a record the text was never a stream, which is the
    unreadable answer rather than an empty one.
    """
    records = [
        cast("dict[str, Any]", parsed)
        for line in stdout.splitlines()
        if isinstance(parsed := parse_json(text=line), dict)
    ]
    return tuple(records) or None


def _mappings(*, values: list[object]) -> tuple[dict[str, Any], ...]:
    """The mapping entries of a list, with non-mapping entries passed over."""
    return tuple(cast("dict[str, Any]", value) for value in values if isinstance(value, dict))
