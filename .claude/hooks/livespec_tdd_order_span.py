"""OTLP decision-span emission for the livespec TDD order guard.

Every allow-or-refuse verdict the guard reaches becomes one OTLP/HTTP JSON
span posted to the sandbox-to-host receiver, so a refusal is visible on the
run's own trace rather than only in a session transcript nobody queries. The
plan this implements calls this signal 1 of three; the per-run aggregate
fields and the Honeycomb board are later slices.

Five attributes carry the verdict: `tdd.decision`, `tdd.path`,
`tdd.head_state`, `tdd.reason` and `tdd.tool`. The host-side receive stage
rebuilds every span's attributes from an ALLOWLIST and drops anything absent
from it, so those five keys are named in
`livespec_orchestrator_beads_fabro.commands._otel_scrub.ATTRIBUTE_ALLOWLIST`
too — without that, this span would arrive carrying no signal at all and the
loss would be silent.

WHY THE SCRUB IS RESTATED HERE. The authoritative credential-shape scrub lives
on the receive side, in that same `_otel_scrub`. This module cannot import it:
`.claude/hooks/` is repo-local dev tooling that must not couple to the shipped
plugin package's internals, and that package is not on this hook's import path
anyway. So the three constants are copied — and `tests/hooks/
test_livespec_tdd_order_span.py` ASSERTS the copies equal the originals, which
is what keeps a copy from drifting into a scrub that no longer scrubs.

Emission NEVER raises and never blocks the guard's decision: an unreachable or
rejecting receiver reports a failed emission and the verdict stands. Telemetry
is an observer of the decision, not a participant in it.
"""

from __future__ import annotations

import json
import re
import secrets
import time
import urllib.request
from collections.abc import Mapping

import livespec_tdd_order_policy as policy

__all__: list[str] = [
    "ATTR_MAX_LEN",
    "CREDENTIAL_URL_RE",
    "EMITTED",
    "ENDPOINT_ENV_VAR",
    "NO_ENDPOINT",
    "REDACTION_MARKER",
    "SCOPE_NAME",
    "SCOPE_VERSION",
    "SERVICE_NAME",
    "SERVICE_NAMESPACE",
    "SPAN_NAME",
    "TRACE_CONTEXT_ENV_VAR",
    "UNDELIVERED",
    "decision_span_body",
    "emit_decision_span",
    "emit_for_decision",
    "resolve_endpoint",
    "trace_context",
]

# Copied from `_otel_scrub`; the paired test asserts the equality.
ATTR_MAX_LEN = 300
REDACTION_MARKER = "[redacted-credential-shaped-value]"
CREDENTIAL_URL_RE = re.compile(r"[a-zA-Z0-9_-]+:[^@\s/]+@")

SERVICE_NAME = "livespec-tdd-order-guard"
SERVICE_NAMESPACE = "livespec-family"
SCOPE_NAME = "livespec.tdd.order"
SCOPE_VERSION = "0.1.0"
SPAN_NAME = "tdd.order.decision"

ENDPOINT_ENV_VAR = "LIVESPEC_SANDBOX_OTEL_ENDPOINT"
TRACE_CONTEXT_ENV_VAR = "TRACEPARENT"

# Each value NAMES the outcome it reports, so a caller logging it says
# something a reader can act on.
EMITTED = "emitted"
NO_ENDPOINT = "no-endpoint"
UNDELIVERED = "undelivered"

_TRACES_PATH = "/v1/traces"
_SPAN_KIND_INTERNAL = 1
_POST_TIMEOUT_SECONDS = 2.0
_HTTP_OK_FLOOR = 200
_HTTP_OK_CEILING = 300
_TRACE_ID_BYTES = 16
_SPAN_ID_BYTES = 8
# W3C trace-context version 00: `00-<32 hex trace id>-<16 hex span id>-<2 hex
# flags>`. Only version 00 is accepted, because a later version may reorder
# the fields and reading it as 00 would fabricate ids.
_TRACEPARENT_RE = re.compile(r"\A00-([0-9a-f]{32})-([0-9a-f]{16})-[0-9a-f]{2}\Z")
_ALL_ZERO_TRACE_ID = "0" * 32
_ALL_ZERO_SPAN_ID = "0" * 16


def emit_for_decision(*, decision: policy.Decision, environ: Mapping[str, str]) -> str:
    """Emit one decision span, resolving endpoint and trace context from env.

    Returns `EMITTED`, `NO_ENDPOINT` or `UNDELIVERED`. No endpoint configured
    is the NORMAL case for a human session with no receiver, so it is a
    successful no-op rather than an error — the guard's verdict never depends
    on telemetry reaching anywhere.
    """
    endpoint = resolve_endpoint(environ=environ)
    if not endpoint:
        return NO_ENDPOINT
    trace_id, parent_span_id = trace_context(
        environ=environ, fallback_trace_id=_fresh_id(nbytes=_TRACE_ID_BYTES)
    )
    delivered = emit_decision_span(
        decision=decision,
        endpoint=endpoint,
        trace_id=trace_id,
        span_id=_fresh_id(nbytes=_SPAN_ID_BYTES),
        parent_span_id=parent_span_id,
        now_ns=time.time_ns(),
    )
    return EMITTED if delivered else UNDELIVERED


def resolve_endpoint(*, environ: Mapping[str, str]) -> str:
    """Return the configured sandbox OTLP endpoint, or empty when unset.

    Deliberately NO default. The dispatcher injects this variable per
    dispatch; outside a dispatch there is no receiver, and defaulting to the
    conventional address would make every decision in a human session attempt
    a post that cannot succeed.
    """
    return environ.get(ENDPOINT_ENV_VAR, "").strip()


def trace_context(*, environ: Mapping[str, str], fallback_trace_id: str) -> tuple[str, str]:
    """Resolve `(trace_id, parent_span_id)` from the W3C `TRACEPARENT`.

    An absent or malformed traceparent yields `(fallback_trace_id, "")` — a
    root span rather than a failure, since a decision worth recording must not
    be dropped because its context is missing. An all-zero trace or span id is
    invalid per the W3C spec and is treated as absent.
    """
    matched = _TRACEPARENT_RE.match(environ.get(TRACE_CONTEXT_ENV_VAR, "").strip().lower())
    if matched is None:
        return fallback_trace_id, ""
    trace_id, parent_span_id = matched.group(1), matched.group(2)
    if trace_id == _ALL_ZERO_TRACE_ID or parent_span_id == _ALL_ZERO_SPAN_ID:
        return fallback_trace_id, ""
    return trace_id, parent_span_id


def _fresh_id(*, nbytes: int) -> str:
    """Return a fresh random hex id of `nbytes` bytes."""
    return secrets.token_hex(nbytes)


def emit_decision_span(
    *,
    decision: policy.Decision,
    endpoint: str,
    trace_id: str,
    span_id: str,
    parent_span_id: str,
    now_ns: int,
) -> bool:
    """Post one decision span to `endpoint`; True iff the receiver accepted it.

    An EMPTY endpoint posts nothing and returns False — side-effect free, not
    an error. A rejecting or unreachable receiver also returns False rather
    than raising: the guard's verdict has already been decided and must not
    depend on telemetry reaching anywhere.
    """
    if not endpoint:
        return False
    body = decision_span_body(
        decision=decision,
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=parent_span_id,
        now_ns=now_ns,
    )
    request = urllib.request.Request(  # noqa: S310 — plaintext OTLP to the configured sandbox receiver
        f"{endpoint.rstrip('/')}{_TRACES_PATH}",
        data=body.encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=_POST_TIMEOUT_SECONDS) as response:  # noqa: S310 — same request, already constructed above
            return _HTTP_OK_FLOOR <= response.status < _HTTP_OK_CEILING
    except OSError:
        return False


def decision_span_body(
    *,
    decision: policy.Decision,
    trace_id: str,
    span_id: str,
    parent_span_id: str,
    now_ns: int,
) -> str:
    """Render one OTLP `ExportTraceServiceRequest` JSON body for a decision.

    A decision is instantaneous, so start and end timestamps are equal. An
    empty `parent_span_id` omits the field entirely rather than sending a
    zero-valued one, which an OTLP receiver would read as a malformed parent.
    """
    span: dict[str, object] = {
        "traceId": trace_id,
        "spanId": span_id,
        "name": SPAN_NAME,
        "kind": _SPAN_KIND_INTERNAL,
        "startTimeUnixNano": str(now_ns),
        "endTimeUnixNano": str(now_ns),
        "attributes": [
            _attribute(key=key, value=value)
            for key, value in _attributes(decision=decision).items()
        ],
    }
    if parent_span_id:
        span["parentSpanId"] = parent_span_id
    request: dict[str, object] = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        _attribute(key="service.name", value=SERVICE_NAME),
                        _attribute(key="service.namespace", value=SERVICE_NAMESPACE),
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": SCOPE_NAME, "version": SCOPE_VERSION},
                        "spans": [span],
                    }
                ],
            }
        ]
    }
    return json.dumps(request, separators=(",", ":"), sort_keys=True)


def _attributes(*, decision: policy.Decision) -> dict[str, str]:
    """Map one decision onto the five allowlisted `tdd.*` attribute keys."""
    return {
        "tdd.decision": decision.decision,
        "tdd.path": decision.path,
        "tdd.head_state": decision.head_state,
        "tdd.reason": decision.reason,
        "tdd.tool": decision.tool,
    }


def _attribute(*, key: str, value: str) -> dict[str, object]:
    """Build one OTLP/HTTP-JSON string attribute entry, scrubbed."""
    return {"key": key, "value": {"stringValue": _scrub(value=value)}}


def _scrub(*, value: str) -> str:
    """Replace a credential-shaped value wholesale; otherwise truncate.

    Fail-closed in the same direction the receive side chose: a value matching
    the credential shape is replaced ENTIRELY rather than shipped partially,
    and truncation runs only on a value that already cleared that check,
    because truncating a secret is not scrubbing it.
    """
    if CREDENTIAL_URL_RE.search(value) is not None:
        return REDACTION_MARKER
    return value[:ATTR_MAX_LEN]
