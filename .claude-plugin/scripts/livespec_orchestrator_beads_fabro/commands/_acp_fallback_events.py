"""Reading one run's event stream onto the closed ACP fallback vocabulary.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": "Unknown versions MUST be round-tripped byte-for-byte and
surfaced as unobservable; they MUST NOT mint a hold or silently
disappear."

THE READER IS A FILTER, NOT A PARSER OF EVERY EVENT. Anything outside
`ACP_PROJECTED_EVENT_TYPES` -- the native `agent.failover`, the
engine-internal `agent.acp.side_effect` -- is passed over silently rather
than misread as a transition. `agent.acp.started` is the one exception,
read for its candidate index alone because the warning clearance rule
turns on which candidate began a node visit.

AN UNKNOWN `schema_version` IS KEPT, NOT DROPPED AND NOT READ. The
version test runs BEFORE any field is read, and a foreign record leaves
on `unobservable` with its raw mapping intact -- the same posture
`_acp_hold_records.parse_hold_record` already takes for a stored
observation, so the two halves of the projection agree about what an
unknown version means.

A REFUSAL IS NOT AN EMPTY SCAN, and the distinction is the whole reason
this returns a union. A run that emitted no transition is a normal,
complete observation; a payload nobody can parse is an UNREAD surface,
and "Read failure is not absence."
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._acp_failure_classifier import (
    CANDIDATE_SCOPE,
    DOMAIN_SCOPE,
)
from livespec_orchestrator_beads_fabro.commands._acp_fallback_event_types import (
    ACP_EVENT_SCHEMA_VERSION,
    ACP_PROJECTED_EVENT_TYPES,
    ACP_STARTED_EVENT,
    AcpEventScan,
    AcpFallbackEvent,
    AcpNodeStart,
)
from livespec_orchestrator_beads_fabro.commands._acp_schema_fields import (
    non_empty_text,
    string_tuple,
)

__all__: list[str] = [
    "scan_acp_events",
]

_UNREADABLE_PAYLOAD = "the run's event stream is not a readable JSON array of event objects"

_REQUIRED_EVENT_TEXT: tuple[str, ...] = (
    "event_id",
    "type",
    "occurred_at",
    "node",
    "hold_key",
    "cause",
    "scope",
    "primary_generation",
    "full_chain",
)


def scan_acp_events(*, payload: object) -> AcpEventScan | str:
    """Read one run's event stream, or refuse naming the payload as unreadable."""
    records = _event_records(payload=payload)
    if records is None:
        return _UNREADABLE_PAYLOAD
    events: list[AcpFallbackEvent] = []
    unobservable: list[Mapping[str, object]] = []
    starts: list[AcpNodeStart] = []
    for record in records:
        if record.get("type") == ACP_STARTED_EVENT:
            start = _parse_start(record=record)
            if start is not None:
                starts.append(start)
            continue
        if record.get("type") not in ACP_PROJECTED_EVENT_TYPES:
            continue
        if record.get("schema_version") != ACP_EVENT_SCHEMA_VERSION:
            unobservable.append(record)
            continue
        parsed = _parse_event(record=record)
        if parsed is None:
            unobservable.append(record)
            continue
        events.append(parsed)
    return AcpEventScan(
        events=tuple(events), unobservable=tuple(unobservable), starts=tuple(starts)
    )


def _event_records(*, payload: object) -> tuple[Mapping[str, Any], ...] | None:
    """The stream as a tuple of objects, tolerating both envelope shapes.

    `fabro events --json` prints a bare array; a server payload wraps the
    same array under `events`. Both are accepted because the alternative
    is a projection that reports every run unreadable the day the port
    switches transports -- a false projection-failure fact that would stop
    the unattended drain repository-wide.
    """
    if isinstance(payload, dict):
        payload = cast("dict[str, Any]", payload).get("events")
    if not isinstance(payload, list):
        return None
    items = cast("list[object]", payload)
    if not all(isinstance(item, dict) for item in items):
        return None
    return tuple(
        {str(key): value for key, value in cast("dict[str, Any]", item).items()} for item in items
    )


def _parse_event(*, record: Mapping[str, Any]) -> AcpFallbackEvent | None:
    """One v1 record as a typed event, or `None` when a required field is absent."""
    texts = _required_texts(record=record)
    if texts is None:
        return None
    source = record.get("from")
    if not isinstance(source, dict):
        return None
    origin = _candidate_identity(entry=cast("dict[str, Any]", source))
    if origin is None:
        return None
    target = _target_identity(record=record)
    return AcpFallbackEvent(
        event_id=texts["event_id"],
        event_type=texts["type"],
        occurred_at=texts["occurred_at"],
        node=texts["node"],
        node_visit=_count(value=record.get("node_visit")),
        engine_attempt=_count(value=record.get("engine_attempt")),
        from_candidate_index=origin[0],
        from_display_name=origin[1],
        from_candidate_key=origin[2],
        from_availability_key=origin[3],
        to_candidate_index=None if target is None else target[0],
        to_display_name=None if target is None else target[1],
        to_candidate_key=None if target is None else target[2],
        hold_key=texts["hold_key"],
        cause=texts["cause"],
        scope=texts["scope"],
        primary_generation=texts["primary_generation"],
        full_chain=texts["full_chain"],
        attempted=string_tuple(value=record.get("attempted")) or (),
        skipped=string_tuple(value=record.get("skipped")) or (),
    )


def _parse_start(*, record: Mapping[str, Any]) -> AcpNodeStart | None:
    """One started event, or `None` when it predates the additive chain fields.

    A pre-chain `agent.acp.started` carries no `candidate_index`, and the
    honest reading of that absence is "this engine does not report which
    candidate ran" -- not "it ran the primary". Returning `None` keeps a
    warning standing rather than clearing it on an assumption.
    """
    index = _index(value=record.get("candidate_index"))
    node = non_empty_text(value=record.get("node"))
    occurred_at = non_empty_text(value=record.get("occurred_at"))
    generation = non_empty_text(value=record.get("primary_generation"))
    if index is None or node is None or occurred_at is None or generation is None:
        return None
    return AcpNodeStart(
        node=node,
        node_visit=_count(value=record.get("node_visit")),
        candidate_index=index,
        occurred_at=occurred_at,
        primary_generation=generation,
    )


def _required_texts(*, record: Mapping[str, Any]) -> dict[str, str] | None:
    """Every non-blank text field a v1 event owes, or `None` when one is missing.

    `scope` is checked against the two ratified values here rather than
    downstream, because an unrecognised scope cannot be shaped into a
    failure at all -- `event_failure` would key a candidate record with no
    candidate, which the stored-record parser then refuses as unobservable
    with no way back to the event that caused it.
    """
    texts: dict[str, str] = {}
    for name in _REQUIRED_EVENT_TEXT:
        value = non_empty_text(value=record.get(name))
        if value is None:
            return None
        texts[name] = value
    if texts["scope"] not in (DOMAIN_SCOPE, CANDIDATE_SCOPE):
        return None
    return texts


def _target_identity(*, record: Mapping[str, Any]) -> tuple[int, str, str] | None:
    """The `to` candidate's index and identity, or `None` on an exhaustion event."""
    target = record.get("to")
    if not isinstance(target, dict):
        return None
    identity = _candidate_identity(entry=cast("dict[str, Any]", target))
    if identity is None:
        return None
    return (identity[0], identity[1], identity[2])


def _candidate_identity(*, entry: Mapping[str, Any]) -> tuple[int, str, str, str] | None:
    """One side's `(index, display_name, candidate_key, availability_key)`."""
    index = _index(value=entry.get("candidate_index"))
    display = non_empty_text(value=entry.get("display_name"))
    candidate_key = non_empty_text(value=entry.get("candidate_key"))
    availability_key = non_empty_text(value=entry.get("availability_key"))
    if index is None or display is None or candidate_key is None or availability_key is None:
        return None
    return (index, display, candidate_key, availability_key)


def _index(*, value: object) -> int | None:
    """A candidate index as a non-negative integer, else `None`.

    `bool` is excluded explicitly: Python makes it an `int` subclass, so
    `candidate_index: true` would otherwise resolve to index 1 -- a real,
    plausible non-primary candidate nobody ran.
    """
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _count(*, value: object) -> int:
    """A non-negative counter field, defaulting to zero when it is unreadable.

    Visit and attempt counters are REPORTED, never decided on: they ride
    into the journal record so an operator can correlate with the run, and
    a missing one must not cost the whole event its hold.
    """
    index = _index(value=value)
    return 0 if index is None else index
