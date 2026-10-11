"""OTLP span rendering for the Dispatcher's own per-dispatch span.

The span exists so the factory has something to parent TO. The engine
turns the caller's `TRACEPARENT` into a parent for its server run span,
and that traceparent names this span; without it the chain starts at the
server run and the whole host half of a dispatch — admission, plan build,
overlay, launch — is invisible in the trace.

It rides the same `ExportTraceServiceRequest`-per-line shape every other
host emitter here writes (`_dispatcher_calibration_span`,
`_dispatcher_reflection_spans`, report mode), because the file-tail enrich
driver tails all of them through one `EnrichStage` per span-file kind.
Every attribute key below must ALSO be named in
`_otel_scrub.ATTRIBUTE_ALLOWLIST` — the forwarding stage rebuilds
attributes from that allowlist, so an unnamed key is dropped with no error
and the signal arrives silently empty. The three here are the correlation
triple that allowlist already carries.
"""

from __future__ import annotations

import json

from livespec_orchestrator_beads_fabro.commands._dispatcher_correlation import (
    DispatchCorrelation,
    correlation_attributes,
    dispatch_span_ids,
)
from livespec_orchestrator_beads_fabro.commands._otel_scrub import attr as _attr

__all__: list[str] = [
    "DISPATCH_SPAN_NAME",
    "dispatch_request_line",
]

_OTLP_SERVICE_NAME = "livespec-dispatcher"
_OTLP_SERVICE_NAMESPACE = "livespec-family"
_OTLP_SCOPE_NAME = "livespec.dispatcher.dispatch"
_OTLP_SCOPE_VERSION = "0.1.0"
_SPAN_KIND_INTERNAL = 1

# The name the enrich tier's dispatch-outcome columns were already written
# against, so promoting this span feeds the queries rather than adding a
# second vocabulary beside them.
DISPATCH_SPAN_NAME = "dispatcher.dispatch"


def dispatch_request_line(*, correlation: DispatchCorrelation, now_ns: int) -> str:
    """Build one OTLP `ExportTraceServiceRequest` JSON line for a dispatch.

    Zero-duration by construction: the span is an ANCHOR for the run's own
    spans to hang from, not a measurement of the dispatch's wall clock —
    the run's spans carry that, and a host-side end time would have to be
    written after the run it is meant to parent had already exported.
    """
    ids = dispatch_span_ids(dispatch_id=correlation.dispatch_id)
    span = {
        "traceId": ids.trace_id,
        "spanId": ids.span_id,
        "name": DISPATCH_SPAN_NAME,
        "kind": _SPAN_KIND_INTERNAL,
        "startTimeUnixNano": str(now_ns),
        "endTimeUnixNano": str(now_ns),
        "attributes": [
            _attr(key=key, value=value)
            for key, value in correlation_attributes(correlation=correlation).items()
        ],
    }
    request: dict[str, object] = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": _OTLP_SERVICE_NAME}},
                        {
                            "key": "service.namespace",
                            "value": {"stringValue": _OTLP_SERVICE_NAMESPACE},
                        },
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": _OTLP_SCOPE_NAME, "version": _OTLP_SCOPE_VERSION},
                        "spans": [span],
                    }
                ],
            }
        ]
    }
    return json.dumps(request, separators=(",", ":"), sort_keys=True)
