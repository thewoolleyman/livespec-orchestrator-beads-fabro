"""Live OTLP/HTTP receive plane plus metrics-heartbeat path.

`OtelReceiver` accepts OTLP/HTTP JSON trace and metric POSTs from Fabro
sandboxes, enriches and exports trace spans through the shared scrubbed span
pipeline, and records low-latency metric heartbeats for the watchdog. The
receiver is fail-open toward dispatch work and fail-closed toward credentials.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from http import HTTPStatus
from pathlib import Path
from socket import AF_INET, SHUT_RDWR, SO_REUSEADDR, SOCK_STREAM, SOL_SOCKET, socket
from typing import Protocol, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_sink import CostSink
from livespec_orchestrator_beads_fabro.commands._otel_enrich import (
    CorrelationJoin,
    correlation_keys_from_attrs,
    enrich_span,
    honeycomb_dataset_for,
)
from livespec_orchestrator_beads_fabro.commands._otel_heartbeat import read_beats, write_beats
from livespec_orchestrator_beads_fabro.commands._otel_http_handler import (
    HttpPostHandler,
    SocketHttpPostHandler,
    read_json_body,
    reply,
)
from livespec_orchestrator_beads_fabro.commands._otel_parse import (
    heartbeat_keys_from_metrics_request,
    ingested_spans_from_trace_request,
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

_RECEIVER_HOST_ENV = "LIVESPEC_OTEL_RECEIVER_HOST"
_RECEIVER_PORT_ENV = "LIVESPEC_OTEL_RECEIVER_PORT"
# The Docker default-bridge gateway, SYMMETRIC with the sandbox egress target
# (`_dispatcher_projection.DEFAULT_SANDBOX_OTEL_ENDPOINT` = http://172.17.0.1:4318).
# A Fabro sandbox POSTs its Claude-Code OTel to `172.17.0.1` (inside the
# container `127.0.0.1` is the sandbox's OWN loopback, so the host is reached via
# the bridge gateway); a receiver bound to `127.0.0.1` would refuse those
# bridge-interface connections. NOT `0.0.0.0` — this is a shared multi-tenant
# host, so 4318 is bound to the bridge interface only, never all interfaces. A
# non-docker host (no `172.17.0.1` interface) sets `LIVESPEC_OTEL_RECEIVER_HOST`
# to `127.0.0.1`; if unset there, the bind fails fail-open (the driver still
# egresses the host span files — see `_otel_enrich_driver`).
_DEFAULT_RECEIVER_HOST = "172.17.0.1"
_DEFAULT_RECEIVER_PORT = 4318

_TRACES_PATH = "/v1/traces"
_METRICS_PATH = "/v1/metrics"

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


@dataclass(frozen=True, kw_only=True)
class ReceiverConfig:
    """The bound host addr/port for the live receiver.

    `port == 0` binds an EPHEMERAL port (used by the hermetic test tier so
    no fixed port is contended); production uses the committed default (the
    Docker bridge gateway) or the `LIVESPEC_OTEL_RECEIVER_*` override.
    """

    host: str
    port: int


def resolve_receiver_config(*, environ: dict[str, str]) -> ReceiverConfig:
    """Resolve the receiver addr/port from env, with committed defaults.

    An unset env reads as the committed Docker-bridge default (never UNBOUND).
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
        return read_beats(path=self.path)

    def _write(self, *, beats: dict[str, float]) -> None:
        write_beats(path=self.path, beats=beats)


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

    def start(self) -> None:
        """Bind the socket and serve on a daemon thread (idempotent)."""
        if self._server is not None:
            return
        server = socket(AF_INET, SOCK_STREAM)
        server.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        server.bind((self.config.host, self.config.port))
        server.listen()
        self.bound_port = int(server.getsockname()[1])
        self._thread = threading.Thread(target=self._serve, kwargs={"server": server}, daemon=True)
        self._thread.start()
        self._server = server

    def stop(self) -> None:
        """Shut the server down and join its thread (deterministic teardown)."""
        server = self._server
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
            threading.Thread(
                target=self._serve_connection,
                kwargs={"conn": conn, "addr": addr},
                daemon=True,
            ).start()

    def _serve_connection(self, *, conn: socket, addr: object) -> None:
        _ = SocketHttpPostHandler(receiver=self, request=conn, client_address=addr, server=self)

    def handle_post(self, *, handler: HttpPostHandler) -> None:
        """Route + handle one POST, returning bad request for parse errors."""
        self._route(handler=handler)

    def _route(self, *, handler: HttpPostHandler) -> None:
        if handler.path == _TRACES_PATH:
            self._handle_traces(handler=handler)
            return
        if handler.path == _METRICS_PATH:
            self._handle_metrics(handler=handler)
            return
        reply(handler=handler, status=HTTPStatus.NOT_FOUND)

    def _handle_traces(self, *, handler: HttpPostHandler) -> None:
        parsed = read_json_body(handler=handler)
        if parsed is None:
            reply(handler=handler, status=HTTPStatus.BAD_REQUEST)
            return
        spans = ingested_spans_from_trace_request(request=parsed)
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
                continue
            dataset = honeycomb_dataset_for(resource_attrs=ingested.resource_attrs)
            per_dataset.setdefault(dataset, []).append(enriched)
        for dataset, batch in per_dataset.items():
            _ = self.exporter.export(spans=tuple(batch), dataset=dataset)
        reply(handler=handler, status=HTTPStatus.OK)

    def _handle_metrics(self, *, handler: HttpPostHandler) -> None:
        parsed = read_json_body(handler=handler)
        if parsed is None:
            reply(handler=handler, status=HTTPStatus.BAD_REQUEST)
            return
        now = time.time()
        for key in heartbeat_keys_from_metrics_request(request=parsed):
            self.heartbeat.beat(key=scrub(value=key), at=now)
        reply(handler=handler, status=HTTPStatus.OK)


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
    except (OSError, RuntimeError):
        return None
    holder[_HOLDER_SLOT] = server
    return server
