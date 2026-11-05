"""Terminal dispatch telemetry and the ACP attempts it can directly observe.

The initial ``dispatcher.dispatch`` span is an anchor whose identity is known
before a run starts.  This module emits the distinct terminal span after the
outcome is settled.  It deliberately accepts event payloads rather than owning
transport: reading events is fallible host I/O, while rendering an already-read
observation remains deterministic and cannot change the dispatch result.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._acp_attempt_windows import attempt_windows
from livespec_orchestrator_beads_fabro.commands._acp_fallback_events import scan_acp_events
from livespec_orchestrator_beads_fabro.commands._dispatcher_correlation import (
    DispatchCorrelation,
    correlation_attributes,
    dispatch_span_ids,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._otel_scrub import measured_attr as _attr

__all__: list[str] = [
    "ATTEMPT_SPAN_NAME",
    "TERMINAL_SPAN_NAME",
    "TerminalAttempt",
    "emit_terminal_span",
    "terminal_attempts",
    "terminal_outcome",
    "terminal_request_line",
]

TERMINAL_SPAN_NAME = "livespec.dispatch.terminal"
ATTEMPT_SPAN_NAME = "livespec.dispatch.attempt"
_SERVICE_NAME = "livespec-dispatcher"
_SERVICE_NAMESPACE = "livespec-family"
_SCOPE_NAME = "livespec.dispatcher.terminal"
_SCOPE_VERSION = "0.1.0"
_SPAN_KIND_INTERNAL = 1


@dataclass(frozen=True, kw_only=True)
class TerminalAttempt:
    """One observed implementing-candidate attempt, in its event-time window."""

    index: int
    fallback: bool
    started_at_ns: int
    ended_at_ns: int
    model: str | None


def terminal_outcome(*, outcome: DispatchOutcome) -> str:
    """Map the dispatch's settled disposition to the closed telemetry enum."""
    if outcome.status == "green":
        return "succeeded"
    if outcome.status in {"cancelled", "stalled-no-progress", "run-wall-budget-exceeded"}:
        return "cancelled"
    if outcome.status in {"abandoned", "run-unobservable"}:
        return "abandoned"
    if outcome.status == "rework" or outcome.verdict in {"rework", "rework-pending"}:
        return "rework"
    return "failed"


def terminal_attempts(
    *, events_payload: object, terminal_at_ns: int
) -> tuple[TerminalAttempt, ...]:
    """Read observed implementing-turn attempts from a Fabro events payload.

    A malformed or unavailable stream yields no observations rather than a
    fabricated attempt.  The final successful candidate has no failover event
    to close it, so the terminal instant is its observable end boundary.
    """
    scan = scan_acp_events(payload=events_payload)
    if isinstance(scan, str):
        return ()
    models = {
        (start.node, start.node_visit, start.candidate_index): start.confirmed_model
        for start in scan.starts
    }
    windows = [window for window in attempt_windows(scan=scan) if window.node == "implement"]
    ordered = sorted(
        windows,
        key=lambda value: (value.started_at_ms, value.node_visit, value.candidate_index),
    )
    return tuple(
        TerminalAttempt(
            index=index,
            fallback=window.candidate_index > 0,
            started_at_ns=window.started_at_ms * 1_000_000,
            ended_at_ns=(
                window.ended_at_ms * 1_000_000 if window.ended_at_ms is not None else terminal_at_ns
            ),
            model=models.get((window.node, window.node_visit, window.candidate_index)),
        )
        for index, window in enumerate(ordered)
    )


def emit_terminal_span(
    *,
    correlation: DispatchCorrelation | None,
    outcome: DispatchOutcome,
    attempts: tuple[TerminalAttempt, ...],
    spans_path: Path,
    started_at_ns: int,
    ended_at_ns: int,
) -> None:
    """Append one terminal request, or nothing when no dispatch id was minted."""
    if correlation is None:
        return
    spans_path.parent.mkdir(parents=True, exist_ok=True)
    with spans_path.open("a", encoding="utf-8") as handle:
        _ = handle.write(
            terminal_request_line(
                correlation=correlation,
                outcome=outcome,
                attempts=attempts,
                started_at_ns=started_at_ns,
                ended_at_ns=ended_at_ns,
            )
            + "\n"
        )


def terminal_request_line(
    *,
    correlation: DispatchCorrelation,
    outcome: DispatchOutcome,
    attempts: tuple[TerminalAttempt, ...],
    started_at_ns: int,
    ended_at_ns: int,
) -> str:
    """Render the terminal and all observed child attempts as one OTLP request."""
    ids = dispatch_span_ids(dispatch_id=correlation.dispatch_id)
    terminal_id = _child_span_id(dispatch_id=correlation.dispatch_id, suffix="terminal")
    terminal_attributes = {
        **correlation_attributes(correlation=correlation),
        "livespec.dispatch.outcome": terminal_outcome(outcome=outcome),
        "livespec.dispatch.attempt_count": len(attempts),
    }
    terminal = {
        "traceId": ids.trace_id,
        "spanId": terminal_id,
        "parentSpanId": ids.span_id,
        "name": TERMINAL_SPAN_NAME,
        "kind": _SPAN_KIND_INTERNAL,
        "startTimeUnixNano": str(started_at_ns),
        "endTimeUnixNano": str(max(started_at_ns, ended_at_ns)),
        "attributes": [_attr(key=key, value=value) for key, value in terminal_attributes.items()],
    }
    children = [
        _attempt_span(
            correlation=correlation,
            parent_span_id=terminal_id,
            attempt=attempt,
            trace_id=ids.trace_id,
        )
        for attempt in attempts
    ]
    request: dict[str, object] = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": _SERVICE_NAME}},
                        {"key": "service.namespace", "value": {"stringValue": _SERVICE_NAMESPACE}},
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": _SCOPE_NAME, "version": _SCOPE_VERSION},
                        "spans": [terminal, *children],
                    }
                ],
            }
        ]
    }
    return json.dumps(request, separators=(",", ":"), sort_keys=True)


def _attempt_span(
    *,
    correlation: DispatchCorrelation,
    parent_span_id: str,
    attempt: TerminalAttempt,
    trace_id: str,
) -> dict[str, object]:
    attributes: dict[str, object] = {
        "livespec.dispatch.id": correlation.dispatch_id,
        "livespec.dispatch.attempt.index": attempt.index,
        "livespec.dispatch.attempt.fallback": attempt.fallback,
    }
    if attempt.model is None:
        attributes["livespec.dispatch.unavailable_fields"] = ("acp.model",)
    else:
        attributes["acp.model"] = attempt.model
    return {
        "traceId": trace_id,
        "spanId": _child_span_id(
            dispatch_id=correlation.dispatch_id, suffix=f"attempt:{attempt.index}"
        ),
        "parentSpanId": parent_span_id,
        "name": ATTEMPT_SPAN_NAME,
        "kind": _SPAN_KIND_INTERNAL,
        "startTimeUnixNano": str(attempt.started_at_ns),
        "endTimeUnixNano": str(max(attempt.started_at_ns, attempt.ended_at_ns)),
        "attributes": [_attr(key=key, value=value) for key, value in attributes.items()],
    }


def _child_span_id(*, dispatch_id: str, suffix: str) -> str:
    value = hashlib.sha256(f"livespec.dispatch.{suffix}:{dispatch_id}".encode()).hexdigest()[:16]
    return "0" * 15 + "1" if value == "0" * 16 else value
