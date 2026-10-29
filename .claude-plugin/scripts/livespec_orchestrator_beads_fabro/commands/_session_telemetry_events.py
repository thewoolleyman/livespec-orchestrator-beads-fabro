"""Closed event catalogs and OTLP/HTTP-JSON rendering for host-session telemetry.

Two producers publish through this one seam: the wait command's wait-family
catalog and the recovery path's recovery-family catalog, both under the
versioned `livespec.orchestrator.session_wait` scope with resource
`service.name=livespec-dispatcher` and `service.namespace=livespec-family`.
The catalogs are CLOSED: `session_event` refuses a name outside them, so the
vocabulary a consumer queries cannot drift by one producer inventing a word.

Every attribute key a producer builds must ALSO be named in
`_otel_scrub.ATTRIBUTE_ALLOWLIST`. The receiver rebuilds a span's attributes
from that allowlist, so a key it does not name is dropped with no error and
the event arrives in Honeycomb silently empty.

An absent value is OMITTED, never replaced by a zero or a placeholder: a
measurement nobody took must not be queryable as a measurement of zero.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite

from livespec_orchestrator_beads_fabro.commands._dispatcher_correlation import non_zero_hex
from livespec_orchestrator_beads_fabro.commands._otel_scrub import measured_attr

__all__: list[str] = [
    "RECOVERY_EVENT_NAMES",
    "SCOPE_NAME",
    "SCOPE_VERSION",
    "SERVICE_NAME",
    "SERVICE_NAMESPACE",
    "WAIT_EVENT_NAMES",
    "SessionEvent",
    "TraceParent",
    "request_payload",
    "rfc3339",
    "session_event",
    "trace_parent_from_environ",
]

SCOPE_NAME = "livespec.orchestrator.session_wait"
SCOPE_VERSION = "1.0.0"
SERVICE_NAME = "livespec-dispatcher"
SERVICE_NAMESPACE = "livespec-family"

WAIT_EVENT_NAMES: tuple[str, ...] = (
    "session.wait.armed",
    "session.wait.observed",
    "session.wait.returned",
    "session.wait.acknowledged",
    "session.wait.inventory",
)
RECOVERY_EVENT_NAMES: tuple[str, ...] = (
    "session.obligation.registered",
    "session.recovery.notification",
    "session.recovery.receipt",
    "session.recovery.claimed",
    "session.recovery.started",
    "session.recovery.executed",
    "session.recovery.deferred",
    "session.recovery.reconciled",
    "session.recovery.coverage",
)

_SPAN_KIND_INTERNAL = 1
_NANOS_PER_SECOND = 1_000_000_000
_TRACE_ID_DIGITS = 32
_SPAN_ID_DIGITS = 16
_TRACEPARENT_FIELDS = 4
_TRACEPARENT_ENV = "TRACEPARENT"


@dataclass(frozen=True, kw_only=True)
class TraceParent:
    """An existing W3C trace context a session event is placed under."""

    trace_id: str
    span_id: str


@dataclass(frozen=True, kw_only=True)
class SessionEvent:
    """One curated event: a catalog name, an instant, and present-only attributes."""

    name: str
    at: float
    trace_key: str
    attributes: dict[str, object]


def session_event(
    *, name: str, at: float, trace_key: str, attributes: dict[str, object | None]
) -> SessionEvent:
    """Build one event from the closed catalogs, omitting every absent value."""
    if name not in WAIT_EVENT_NAMES and name not in RECOVERY_EVENT_NAMES:
        message = f"{name!r} is not in the closed session event catalogs"
        raise ValueError(message)
    present: dict[str, object] = {
        key: value
        for key, value in attributes.items()
        if value is not None and not (isinstance(value, float) and not isfinite(value))
    }
    return SessionEvent(name=name, at=at, trace_key=trace_key, attributes=present)


def rfc3339(*, at: float) -> str:
    """The UTC RFC 3339 rendering of an epoch instant, to whole seconds."""
    return datetime.fromtimestamp(at, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def trace_parent_from_environ(*, environ: dict[str, str]) -> TraceParent | None:
    """The caller's `TRACEPARENT`, or None unless it is a valid non-zero context."""
    fields = environ.get(_TRACEPARENT_ENV, "").strip().lower().split("-")
    if len(fields) != _TRACEPARENT_FIELDS:
        return None
    _, trace_id, span_id, _ = fields
    if not _is_hex(text=trace_id, digits=_TRACE_ID_DIGITS):
        return None
    if not _is_hex(text=span_id, digits=_SPAN_ID_DIGITS):
        return None
    if trace_id.strip("0") == "" or span_id.strip("0") == "":
        return None
    return TraceParent(trace_id=trace_id, span_id=span_id)


def _is_hex(*, text: str, digits: int) -> bool:
    return len(text) == digits and all(char in "0123456789abcdef" for char in text)


def _derived_hex(*, material: str, digits: int) -> str:
    return non_zero_hex(digits=hashlib.sha256(material.encode("utf-8")).hexdigest()[:digits])


def _span(*, event: SessionEvent, parent: TraceParent | None) -> dict[str, object]:
    instant = str(int(event.at * _NANOS_PER_SECOND))
    shape = json.dumps(event.attributes, sort_keys=True, default=str)
    span: dict[str, object] = {
        "traceId": (
            parent.trace_id
            if parent is not None
            else _derived_hex(material=f"trace:{event.trace_key}", digits=_TRACE_ID_DIGITS)
        ),
        "spanId": _derived_hex(
            material=f"span:{event.trace_key}:{event.name}:{instant}:{shape}",
            digits=_SPAN_ID_DIGITS,
        ),
        "name": event.name,
        "kind": _SPAN_KIND_INTERNAL,
        "startTimeUnixNano": instant,
        "endTimeUnixNano": instant,
        "attributes": [
            measured_attr(key=key, value=value) for key, value in event.attributes.items()
        ],
    }
    if parent is not None:
        span["parentSpanId"] = parent.span_id
    return span


def request_payload(
    *, events: tuple[SessionEvent, ...], parent: TraceParent | None
) -> dict[str, object]:
    """One OTLP `ExportTraceServiceRequest` carrying the events as spans."""
    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": SERVICE_NAME}},
                        {"key": "service.namespace", "value": {"stringValue": SERVICE_NAMESPACE}},
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": SCOPE_NAME, "version": SCOPE_VERSION},
                        "spans": [_span(event=event, parent=parent) for event in events],
                    }
                ],
            }
        ]
    }
