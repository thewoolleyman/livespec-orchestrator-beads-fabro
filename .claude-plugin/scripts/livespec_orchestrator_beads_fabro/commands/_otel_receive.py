"""Live OTLP/HTTP RECEIVE plane + metrics-heartbeat path — 29f E1 (29f.7).

The live-ingest layer the 29f.5 file-tail DATA plane (`_otel_enrich`, PR
#39) was deferred from, per
`loop-reflection-gate/telemetry-pipeline-architecture.md` §3.2
(custom host-local OTLP processor, NOT otelcol) and §4.4 (the
metrics-heartbeat-vs-spans liveness subtlety). Two coupled pieces:

1. **Live OTLP/HTTP RECEIVER** (§3.2 (a)). A stdlib `http.server`
   (`ThreadingHTTPServer` + `BaseHTTPRequestHandler`) bound to a
   *configurable* loopback addr/port reachable from INSIDE the Fabro
   sandbox — the endpoint 29f.3 points the sandbox Claude-Code OTel at
   (`OTEL_EXPORTER_OTLP_PROTOCOL=http/json`, so protobuf is never
   required). It accepts `POST /v1/traces` (an OTLP/HTTP-JSON
   `ExportTraceServiceRequest`) and `POST /v1/metrics` (an
   `ExportMetricsServiceRequest`) — the same one-request shape the family
   capture script + the reflection emitter use. Trace spans flow straight
   into the SHARED 29f.5 seam (`CorrelationJoin` + `enrich_span` —
   allowlist + fail-closed scrub — + the injected `SpanExporter` egress);
   the receiver re-implements NOTHING of scrub / correlation / egress.

2. **METRICS-HEARTBEAT low-latency forward path** (§4.4). Spans emit on
   END, so a deadlocked/wedged run emits ZERO spans and a span-only signal
   is BLIND to a live-but-stuck run. CC's metrics heartbeat exports on a
   short interval and keeps advancing while a turn is alive, so it is the
   liveness signal 29f.6's oyg `LivenessProbe` reads. `POST /v1/metrics`
   advances a `HeartbeatSink` — a small persisted `{run/session-key ->
   last-emit-timestamp}` map 29f.6 reads OUT OF PROCESS — keyed on the
   correlation triple (`fabro.run_id` / `livespec.dispatch.id` /
   `work.item.id` / `session.id`) carried by the metric data points.

Posture (same dual posture as 29f.2 + the 29f.5 data plane):

- **Fail-OPEN toward the pipeline.** A malformed body, an unknown path, a
  parse / enrich / export error NEVER takes down the receiver and NEVER
  raises out toward a dispatch (the dispatcher already wrote the
  authoritative journal; egress is best-effort). The handler answers 400
  on a bad body / 404 on an unknown path, otherwise 200, and swallows
  internal errors rather than 500-ing the receiver down.
- **Fail-CLOSED toward credentials.** Every forwarded trace span passes
  through the shared `enrich_span` (a credential-shaped allowlisted value
  REJECTS the whole span). On the metrics path, the heartbeat KEY is run
  through the shared fail-closed `scrub` before it is recorded, so a
  credential-shaped run id never lands in the heartbeat file as plaintext.

Dispatcher supervision: `ensure_receiver_started` is **single-instance,
idempotently started** by the dispatcher at dispatch entry — ONE receiver
per host, SHARED across concurrent dispatches (it does NOT spawn one per
dispatch — that would collide on the port). A start failure is fail-open
(returns None, never raises, never blocks a dispatch). This is NOT a
separately-babysat daemon (§3.2 rejects "another daemon to babysit") — it
is an in-process server the dispatcher owns for its lifetime.

This module is stdlib-only — zero new dependencies, consistent with the
29f.5 stdlib-only modules and §3.2's stdlib-first stance.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from email.message import Message
from http import HTTPStatus
from http.client import parse_headers
from pathlib import Path
from socket import AF_INET, SHUT_RDWR, SO_REUSEADDR, SOCK_STREAM, SOL_SOCKET, socket
from typing import IO, Protocol, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_sink import CostSink
from livespec_orchestrator_beads_fabro.commands._otel_enrich import (
    CorrelationJoin,
    IngestedSpan,
    correlation_keys_from_attrs,
    enrich_span,
    honeycomb_dataset_for,
)
from livespec_orchestrator_beads_fabro.commands._otel_scrub import scrub

__all__: list[str] = [
    "HeartbeatSink",
    "OtelReceiver",
    "ReceiverConfig",
    "SpanExporter",
    "StartableServer",
    "ensure_receiver_started",
    "resolve_receiver_config",
]

# Env-var NAMES (not secret values) for the receiver addr/port levers,
# following the `_dispatcher_cost` committed-default discipline so an
# unset env never means UNBOUND. The default loopback addr/port is the
# one the Fabro sandbox is told to ship to (29f.3); a single-operator
# fleet keeps it on loopback (not a public interface). 4318 is the OTLP
# /HTTP conventional port.
_RECEIVER_HOST_ENV = "LIVESPEC_OTEL_RECEIVER_HOST"
_RECEIVER_PORT_ENV = "LIVESPEC_OTEL_RECEIVER_PORT"
_DEFAULT_RECEIVER_HOST = "127.0.0.1"
_DEFAULT_RECEIVER_PORT = 4318

# OTLP/HTTP routes the receiver answers; everything else is a clean 404.
_TRACES_PATH = "/v1/traces"
_METRICS_PATH = "/v1/metrics"

# Defense against an unbounded POST body (a wedged sender flooding the
# socket). Bodies above this are rejected fail-open as a bad request.
_MAX_BODY_BYTES = 8 * 1024 * 1024

# The correlation-triple + session keys a metric data point may carry; the
# heartbeat is keyed by the FIRST present (most-specific first) so 29f.6's
# probe can look the run up by whatever id it holds.
_HEARTBEAT_KEY_PREFERENCE = (
    "fabro.run_id",
    "livespec.dispatch.id",
    "work.item.id",
    "session.id",
)

# The holder slot `ensure_receiver_started` stores the live receiver in.
_HOLDER_SLOT = "server"


class SpanExporter(Protocol):
    """Egress seam: ship a batch of scrubbed spans for one dataset.

    Identical contract to the 29f.5 `_otel_enrich.SpanExporter`: returns
    True on success, False on a (retry-exhausted) failure, NEVER raises —
    the receiver is fail-open toward the pipeline. The real
    `HoneycombHttpExporter` from `_otel_enrich` satisfies this Protocol.
    """

    def export(self, *, spans: tuple[dict[str, object], ...], dataset: str) -> bool:
        """Export a batch of OTLP/HTTP-JSON spans to the given dataset."""
        ...


class StartableServer(Protocol):
    """The minimal shape `ensure_receiver_started` supervises.

    `OtelReceiver` satisfies it; the hermetic test tier injects a fake. The
    supervisor only needs to `start()` it — teardown is owned by whoever
    holds the holder for the process lifetime.
    """

    def start(self) -> None:
        """Bring the server up (idempotent)."""
        ...


class HttpPostHandler(Protocol):
    """Minimal HTTP handler surface consumed by `OtelReceiver`."""

    headers: Message
    path: str
    rfile: IO[bytes]
    wfile: IO[bytes]

    def send_response(self, *, code: HTTPStatus) -> None:
        """Start a response with `code`."""
        ...

    def send_header(self, *, keyword: str, value: str) -> None:
        """Add one response header."""
        ...

    def end_headers(self) -> None:
        """Flush the response status and headers."""
        ...


@dataclass(frozen=True, kw_only=True)
class ReceiverConfig:
    """The bound loopback addr/port for the live receiver.

    `port == 0` binds an EPHEMERAL port (used by the hermetic test tier so
    no fixed port is contended); production uses the committed default or
    the `LIVESPEC_OTEL_RECEIVER_*` override.
    """

    host: str
    port: int


class _SocketHttpPostHandler:
    """Composed request handler for the receiver's socket accept loop."""

    def __init__(
        self,
        *,
        receiver: OtelReceiver,
        request: socket,
        client_address: object,
        server: object,
    ) -> None:
        _ = (client_address, server)
        self._receiver = receiver
        self._request = request
        self.headers = Message()
        self.path = ""
        self.rfile = cast("IO[bytes]", request.makefile("rb"))
        self.wfile = cast("IO[bytes]", request.makefile("wb", buffering=0))
        self._status = HTTPStatus.OK
        self._headers: list[tuple[str, str]] = []
        try:
            self._serve_one()
        finally:
            self.rfile.close()
            self.wfile.close()
            self._request.close()

    def _serve_one(self) -> None:
        request_line = self.rfile.readline(65537).decode("iso-8859-1").strip()
        parts = request_line.split()
        if len(parts) < 2:  # noqa: PLR2004 - method + path are the minimum.
            return
        method, self.path = parts[0], parts[1]
        self.headers = parse_headers(self.rfile)
        if method == "POST":
            self._receiver.handle_post(handler=self)
            return
        _reply(handler=self, status=HTTPStatus.NOT_FOUND)

    def send_response(self, *, code: HTTPStatus) -> None:
        self._status = code

    def send_header(self, *, keyword: str, value: str) -> None:
        self._headers.append((keyword, value))

    def end_headers(self) -> None:
        status = f"HTTP/1.1 {self._status.value} {self._status.phrase}\r\n"
        _ = self.wfile.write(status.encode("ascii"))
        for keyword, value in self._headers:
            _ = self.wfile.write(f"{keyword}: {value}\r\n".encode("ascii"))
        _ = self.wfile.write(b"connection: close\r\n\r\n")


def resolve_receiver_config(*, environ: dict[str, str]) -> ReceiverConfig:
    """Resolve the receiver addr/port from env, with committed defaults.

    An unset env reads as the committed loopback default (never UNBOUND).
    An unparseable / non-positive port falls back to the default rather
    than crashing — same fail-soft discipline as the cost-cap levers.
    """
    host = environ.get(_RECEIVER_HOST_ENV, "").strip() or _DEFAULT_RECEIVER_HOST
    port = _resolve_port(raw=environ.get(_RECEIVER_PORT_ENV))
    return ReceiverConfig(host=host, port=port)


def _resolve_port(*, raw: str | None) -> int:
    if raw is None:
        return _DEFAULT_RECEIVER_PORT
    try:
        port = int(raw.strip())
    except ValueError:
        return _DEFAULT_RECEIVER_PORT
    if port < 0:
        return _DEFAULT_RECEIVER_PORT
    return port


@dataclass(kw_only=True)
class HeartbeatSink:
    """Persisted `{run/session-key -> last-metric-emit timestamp}` map (§4.4).

    The metrics-heartbeat consumable: 29f.6's oyg `LivenessProbe` reads the
    last-emit timestamp for a run OUT OF PROCESS, so the heartbeat is a
    small JSON file rather than in-memory state. `beat` records the latest
    timestamp for a key (monotonically advancing — a stale re-delivery
    never moves a heartbeat backward); `last_beat` reads it back. Both are
    fail-open: a corrupt / unreadable file reads as empty rather than
    crashing the metrics path.

    A `threading.Lock` serializes the read-modify-write so concurrent
    `ThreadingHTTPServer` worker threads never clobber the file.
    """

    path: Path
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def beat(self, *, key: str, at: float) -> None:
        """Record `at` as the last-emit timestamp for `key` (advancing only)."""
        with self._lock:
            current = self._read()
            existing = current.get(key)
            if existing is not None and existing >= at:
                return
            current[key] = at
            self._write(beats=current)

    def last_beat(self, *, key: str) -> float | None:
        """Return the last-emit timestamp for `key`, or None if never beaten."""
        with self._lock:
            return self._read().get(key)

    def _read(self) -> dict[str, float]:
        if not self.path.is_file():
            return {}
        try:
            raw: object = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(raw, dict):
            return {}
        beats: dict[str, float] = {}
        for key, value in cast("dict[str, object]", raw).items():
            if isinstance(value, bool):
                continue
            if isinstance(value, int | float):
                beats[key] = float(value)
        return beats

    def _write(self, *, beats: dict[str, float]) -> None:
        text = json.dumps(beats, separators=(",", ":"), sort_keys=True)
        tmp = self.path.with_name(f"{self.path.name}.tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            _ = tmp.write_text(text, encoding="utf-8")
            _ = tmp.replace(self.path)
        except OSError:
            # Fail-open: a heartbeat write failure never crashes the
            # metrics path (the watchdog degrades to coarse detection).
            return


@dataclass(kw_only=True)
class OtelReceiver:
    """The live OTLP/HTTP receiver — a stdlib `ThreadingHTTPServer`.

    Binds `config.host:config.port` (port 0 = ephemeral). `start()` brings
    the server up on a daemon thread; `bound_port` is the actual bound port
    (resolved from the listening socket). `stop()` shuts it down and joins
    the thread deterministically. Trace POSTs route into the injected
    `exporter` through the SHARED enrich/scrub seam AND accrue per-API-call
    token cost into the injected `cost` sink when one is wired (efj: the
    seam the y0m spend cap reads, keyed by `work.item.id` /
    `livespec.dispatch.id`; `cost=None` simply skips the accrual); metric
    POSTs advance `heartbeat`. `default_model` prices a token-bearing span
    that carries no resolvable `model` attribute (None → the pricing
    module's committed default, CC's own default model). The
    `CorrelationJoin` is process-scoped state shared across requests so a
    later span backfills the triple a dispatcher span taught earlier (§3.3).
    """

    config: ReceiverConfig
    exporter: SpanExporter
    heartbeat: HeartbeatSink
    cost: CostSink | None = None
    join: CorrelationJoin = field(default_factory=CorrelationJoin)
    default_model: str | None = None
    bound_port: int = 0
    _server: socket | None = field(default=None, init=False, repr=False)
    _thread: threading.Thread | None = field(default=None, init=False, repr=False)
    _stop_event: threading.Event = field(default_factory=threading.Event, init=False, repr=False)

    def start(self) -> None:
        """Bind the socket and serve on a daemon thread (idempotent)."""
        if self._server is not None:
            return
        server = socket(AF_INET, SOCK_STREAM)
        server.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        server.bind((self.config.host, self.config.port))
        server.listen()
        self.bound_port = int(server.getsockname()[1])
        self._stop_event.clear()
        thread = threading.Thread(target=self._serve, kwargs={"server": server}, daemon=True)
        thread.start()
        self._server = server
        self._thread = thread

    def stop(self) -> None:
        """Shut the server down and join its thread (deterministic teardown)."""
        server = self._server
        self._stop_event.set()
        if server is not None:
            with suppress(OSError):
                server.shutdown(SHUT_RDWR)
            server.close()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=5.0)
        self._server = None
        self._thread = None

    def is_running(self) -> bool:
        return self._server is not None

    def _serve(self, *, server: socket) -> None:
        while True:
            try:
                conn, addr = server.accept()
            except OSError:
                return
            thread = threading.Thread(
                target=self._serve_connection,
                kwargs={"conn": conn, "addr": addr},
                daemon=True,
            )
            thread.start()

    def _serve_connection(self, *, conn: socket, addr: object) -> None:
        _ = _SocketHttpPostHandler(receiver=self, request=conn, client_address=addr, server=self)

    def handle_post(self, *, handler: HttpPostHandler) -> None:
        """Route + handle one POST, fully fail-open (never raises / 500s)."""
        try:
            self._route(handler=handler)
        except Exception:
            # Fail-open toward the pipeline: any internal error answers a
            # bad request rather than 500-ing the receiver down.
            _reply(handler=handler, status=HTTPStatus.BAD_REQUEST)

    def _route(self, *, handler: HttpPostHandler) -> None:
        if handler.path == _TRACES_PATH:
            self._handle_traces(handler=handler)
            return
        if handler.path == _METRICS_PATH:
            self._handle_metrics(handler=handler)
            return
        _reply(handler=handler, status=HTTPStatus.NOT_FOUND)

    def _handle_traces(self, *, handler: HttpPostHandler) -> None:
        parsed = _read_json_body(handler=handler)
        if parsed is None:
            _reply(handler=handler, status=HTTPStatus.BAD_REQUEST)
            return
        spans = _ingested_spans_from_trace_request(request=parsed)
        # Learn the correlation triple from every span first so a later span
        # in the SAME request backfills from an earlier one (§3.3), and
        # accrue the per-API-call token cost (efj): each span's token vector
        # is priced + recorded in the cost sink keyed by `work.item.id` /
        # `livespec.dispatch.id`, deduped per `request_id` so a re-delivered
        # span counts once. A non-token-bearing span is a no-op in the sink.
        for ingested in spans:
            self.join.observe(keys=correlation_keys_from_attrs(span=ingested.span))
            if self.cost is not None:
                self.cost.accumulate_span(span=ingested.span, default_model=self.default_model)
        per_dataset: dict[str, list[dict[str, object]]] = {}
        for ingested in spans:
            keys = correlation_keys_from_attrs(span=ingested.span)
            triple = self.join.backfill(keys=keys)
            enriched = enrich_span(span=ingested.span, triple=triple)
            if enriched is None:
                # Fail-closed: a credential-shaped span is dropped.
                continue
            dataset = honeycomb_dataset_for(resource_attrs=ingested.resource_attrs)
            per_dataset.setdefault(dataset, []).append(enriched)
        for dataset, batch in per_dataset.items():
            # Fail-open: an export failure is swallowed (never raised).
            _ = self.exporter.export(spans=tuple(batch), dataset=dataset)
        _reply(handler=handler, status=HTTPStatus.OK)

    def _handle_metrics(self, *, handler: HttpPostHandler) -> None:
        parsed = _read_json_body(handler=handler)
        if parsed is None:
            _reply(handler=handler, status=HTTPStatus.BAD_REQUEST)
            return
        now = time.time()
        for key in _heartbeat_keys_from_metrics_request(request=parsed):
            # Fail-closed: the key is scrubbed before it is recorded, so a
            # credential-shaped run id never lands in the heartbeat file.
            self.heartbeat.beat(key=scrub(value=key), at=now)
        _reply(handler=handler, status=HTTPStatus.OK)


def _reply(*, handler: HttpPostHandler, status: HTTPStatus) -> None:
    """Send a tiny JSON OTLP-style response (empty partial-success)."""
    body = b"{}"
    try:
        handler.send_response(code=status)
        handler.send_header(keyword="content-type", value="application/json")
        handler.send_header(keyword="content-length", value=str(len(body)))
        handler.end_headers()
        _ = handler.wfile.write(body[:0])
        _ = handler.wfile.write(body)
    except OSError:
        return


def _read_json_body(*, handler: HttpPostHandler) -> dict[str, object] | None:
    """Read + JSON-parse the request body; None on any malformed/oversized body."""
    raw_length = handler.headers.get("content-length")
    if raw_length is None:
        return None
    try:
        length = int(raw_length)
    except ValueError:
        return None
    if length < 0 or length > _MAX_BODY_BYTES:
        return None
    body = handler.rfile.read(length)
    try:
        parsed: object = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(parsed, dict):
        return None
    return cast("dict[str, object]", parsed)


def _ingested_spans_from_trace_request(*, request: dict[str, object]) -> tuple[IngestedSpan, ...]:
    """Parse an OTLP/HTTP-JSON ExportTraceServiceRequest into IngestedSpans.

    Mirrors the 29f.5 file-tail parser's resourceSpans → scopeSpans → spans
    walk so the receiver hands the SAME `IngestedSpan` shape into the shared
    enrich seam. Structurally-unexpected sub-objects are skipped fail-open.
    """
    resource_spans = request.get("resourceSpans")
    if not isinstance(resource_spans, list):
        return ()
    ingested: list[IngestedSpan] = []
    for raw_rs in cast("list[object]", resource_spans):
        if not isinstance(raw_rs, dict):
            continue
        rs = cast("dict[str, object]", raw_rs)
        resource_attrs = _flatten_resource_attrs(resource=rs.get("resource"))
        scope_spans = rs.get("scopeSpans")
        if not isinstance(scope_spans, list):
            continue
        for raw_scope in cast("list[object]", scope_spans):
            if not isinstance(raw_scope, dict):
                continue
            spans = cast("dict[str, object]", raw_scope).get("spans")
            if not isinstance(spans, list):
                continue
            for raw_span in cast("list[object]", spans):
                if isinstance(raw_span, dict):
                    ingested.append(
                        IngestedSpan(
                            resource_attrs=resource_attrs,
                            span=cast("dict[str, object]", raw_span),
                        )
                    )
    return tuple(ingested)


def _heartbeat_keys_from_metrics_request(*, request: dict[str, object]) -> tuple[str, ...]:
    """Extract the per-data-point heartbeat keys from an ExportMetricsServiceRequest.

    Walks resourceMetrics → scopeMetrics → metrics → (gauge/sum/...)
    dataPoints and, for each data point, returns the MOST-specific
    correlation/session id present (`_HEARTBEAT_KEY_PREFERENCE` order). A
    data point lacking any keyable id is skipped (no anonymous heartbeat).
    Resource-level correlation attrs apply as a fallback for data points
    that carry none of their own.
    """
    resource_metrics = request.get("resourceMetrics")
    if not isinstance(resource_metrics, list):
        return ()
    keys: list[str] = []
    for raw_rm in cast("list[object]", resource_metrics):
        if not isinstance(raw_rm, dict):
            continue
        rm = cast("dict[str, object]", raw_rm)
        resource_ids = _correlation_ids_from_attrs(
            raw_attrs=_resource_attr_list(resource=rm.get("resource"))
        )
        keys.extend(
            _keys_from_scope_metrics(
                scope_metrics=rm.get("scopeMetrics"),
                resource_ids=resource_ids,
            )
        )
    return tuple(keys)


def _keys_from_scope_metrics(*, scope_metrics: object, resource_ids: dict[str, str]) -> list[str]:
    if not isinstance(scope_metrics, list):
        return []
    keys: list[str] = []
    for raw_sm in cast("list[object]", scope_metrics):
        if not isinstance(raw_sm, dict):
            continue
        metrics = cast("dict[str, object]", raw_sm).get("metrics")
        if not isinstance(metrics, list):
            continue
        for raw_metric in cast("list[object]", metrics):
            if isinstance(raw_metric, dict):
                keys.extend(
                    _keys_from_metric(
                        metric=cast("dict[str, object]", raw_metric),
                        resource_ids=resource_ids,
                    )
                )
    return keys


def _keys_from_metric(*, metric: dict[str, object], resource_ids: dict[str, str]) -> list[str]:
    keys: list[str] = []
    for data_point in _data_points_of(metric=metric):
        ids = dict(resource_ids)
        ids.update(_correlation_ids_from_attrs(raw_attrs=data_point.get("attributes")))
        chosen = _preferred_key(ids=ids)
        if chosen is not None:
            keys.append(chosen)
    return keys


def _data_points_of(*, metric: dict[str, object]) -> tuple[dict[str, object], ...]:
    """Return the dataPoints across whichever metric shape is present.

    OTLP metrics carry their points under `gauge` / `sum` / `histogram` /
    `summary` / `exponentialHistogram`; the heartbeat only needs the
    points' correlation attrs, so it scans every recognized shape.
    """
    points: list[dict[str, object]] = []
    for shape in ("gauge", "sum", "histogram", "summary", "exponentialHistogram"):
        block = metric.get(shape)
        if not isinstance(block, dict):
            continue
        data_points = cast("dict[str, object]", block).get("dataPoints")
        if not isinstance(data_points, list):
            continue
        for raw_point in cast("list[object]", data_points):
            if isinstance(raw_point, dict):
                points.append(cast("dict[str, object]", raw_point))
    return tuple(points)


def _preferred_key(*, ids: dict[str, str]) -> str | None:
    for candidate in _HEARTBEAT_KEY_PREFERENCE:
        value = ids.get(candidate)
        if value is not None and value != "":
            return value
    return None


def _resource_attr_list(*, resource: object) -> object:
    if not isinstance(resource, dict):
        return None
    return cast("dict[str, object]", resource).get("attributes")


def _correlation_ids_from_attrs(*, raw_attrs: object) -> dict[str, str]:
    """Extract string-valued correlation/session ids from an OTLP attrs list."""
    found: dict[str, str] = {}
    if not isinstance(raw_attrs, list):
        return found
    for raw in cast("list[object]", raw_attrs):
        if not isinstance(raw, dict):
            continue
        entry = cast("dict[str, object]", raw)
        key = entry.get("key")
        if not isinstance(key, str) or key not in _HEARTBEAT_KEY_PREFERENCE:
            continue
        value = entry.get("value")
        if not isinstance(value, dict):
            continue
        string_value = cast("dict[str, object]", value).get("stringValue")
        if isinstance(string_value, str):
            found[key] = string_value
    return found


def _flatten_resource_attrs(*, resource: object) -> dict[str, str]:
    """Flatten an OTLP `resource.attributes` block to a `key -> str` map.

    Only string-valued resource attributes are kept (the only ones the
    enrich seam consumes — `service.name` for the dataset). Mirrors the
    29f.5 file-tail parser's `_resource_attrs`.
    """
    out: dict[str, str] = {}
    raw_attrs = _resource_attr_list(resource=resource)
    if not isinstance(raw_attrs, list):
        return out
    for raw in cast("list[object]", raw_attrs):
        if not isinstance(raw, dict):
            continue
        entry = cast("dict[str, object]", raw)
        key = entry.get("key")
        value = entry.get("value")
        if not isinstance(key, str) or not isinstance(value, dict):
            continue
        string_value = cast("dict[str, object]", value).get("stringValue")
        if isinstance(string_value, str):
            out[key] = string_value
    return out


def ensure_receiver_started(
    *,
    holder: dict[str, object],
    factory: Callable[[], StartableServer],
) -> StartableServer | None:
    """Start ONE receiver per host, idempotently (single-instance, fail-open).

    The dispatcher calls this at dispatch entry. The receiver is SHARED
    across concurrent dispatches via the process-level `holder` dict (NOT
    one per dispatch — that would collide on the bound port). If a live
    receiver is already in the holder, it is returned unchanged. Otherwise
    `factory` is called to build one and its `start()` is invoked.

    **Fail-open:** any error building / starting the receiver is swallowed
    and None is returned — a receiver failure NEVER blocks or fails a
    dispatch (the dispatcher already wrote the authoritative journal). The
    holder is left clean on failure so a later dispatch can retry.
    """
    existing = holder.get(_HOLDER_SLOT)
    if existing is not None:
        return cast("StartableServer", existing)
    try:
        server = factory()
        server.start()
    except Exception:
        # Fail-open: never raise toward a dispatch; leave the holder clean
        # so a subsequent dispatch can retry the start.
        return None
    holder[_HOLDER_SLOT] = server
    return server
