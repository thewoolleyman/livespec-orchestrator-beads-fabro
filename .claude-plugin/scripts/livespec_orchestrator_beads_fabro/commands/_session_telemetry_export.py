"""Bounded, asynchronous export of host-session events to the host-local receiver.

The wait command and the recovery path publish through the EXISTING host-local
enrichment/scrub/egress route: events are POSTed as OTLP/HTTP-JSON to the
configured receiver's `/v1/traces` surface, and the host-owned stage scrubs
them and ships them to Honeycomb with the credential the host wrapper already
supplies. This module therefore holds NO Honeycomb credential and refuses an
endpoint that names Honeycomb directly: a second, credentialed route is exactly
what the contract forbids.

Telemetry never controls liveness. `emit` only enqueues, on a bounded queue,
and never blocks or raises; one daemon worker owns every transport call under a
per-call timeout and a fixed attempt count; `close` waits a bounded shutdown
allowance and then abandons what remains. A caller computes its result BEFORE
it closes, so nothing here can move a wait's deadline.

Failure is visible but not recursive. Absent configuration is reported once as
local-only; a refused endpoint, transport failure, partial rejection, queue
overflow or abandoned tail is reported once by `close` as a single bounded
line, and the counters ride later events as numeric fields. The report is a
plain local write and never becomes a telemetry event itself.
"""

from __future__ import annotations

import json
import queue
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, replace
from typing import Protocol, cast

from livespec_orchestrator_beads_fabro.commands._session_telemetry_events import (
    SessionEvent,
    TraceParent,
    request_payload,
    trace_parent_from_environ,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.io import write_stderr

__all__: list[str] = [
    "ENDPOINT_ENV",
    "STATE_CONFIGURED",
    "STATE_LOCAL_ONLY",
    "STATE_REFUSED",
    "DegradationReport",
    "PostOutcome",
    "SessionTelemetry",
    "TelemetryConfig",
    "config_from_environ",
    "http_post",
]

ENDPOINT_ENV = "OTEL_EXPORTER_OTLP_ENDPOINT"
STATE_LOCAL_ONLY = "local-only"
STATE_CONFIGURED = "configured"
STATE_REFUSED = "refused"

_TRACES_PATH = "/v1/traces"
_DIRECT_BACKEND_SUFFIX = ".honeycomb.io"
_WORKER_POLL_SECONDS = 0.05
_REASON_UNSET = f"{ENDPOINT_ENV} is not set"
_REASON_DIRECT = "the endpoint names Honeycomb directly; only the host-local receiver is allowed"
_REASON_MALFORMED = "the endpoint is not an http(s) URL with a host"


@dataclass(frozen=True, kw_only=True)
class TelemetryConfig:
    """Where and how hard to export; every bound is explicit and finite."""

    state: str
    url: str | None
    reason: str | None
    queue_limit: int = 64
    batch_limit: int = 16
    timeout_seconds: float = 2.0
    attempts: int = 2
    shutdown_seconds: float = 2.0
    parent: TraceParent | None = None


def config_from_environ(*, environ: dict[str, str]) -> TelemetryConfig:
    """Resolve the receiver from the environment: configured, refused or local-only."""
    parent = trace_parent_from_environ(environ=environ)
    raw = environ.get(ENDPOINT_ENV, "").strip()
    if raw == "":
        return TelemetryConfig(
            state=STATE_LOCAL_ONLY, url=None, reason=_REASON_UNSET, parent=parent
        )
    parts = urllib.parse.urlsplit(raw)
    host = (parts.hostname or "").lower()
    if parts.scheme not in {"http", "https"} or host == "":
        return TelemetryConfig(
            state=STATE_REFUSED, url=None, reason=_REASON_MALFORMED, parent=parent
        )
    if host.endswith(_DIRECT_BACKEND_SUFFIX):
        return TelemetryConfig(state=STATE_REFUSED, url=None, reason=_REASON_DIRECT, parent=parent)
    path = parts.path.rstrip("/")
    if not path.endswith(_TRACES_PATH):
        path += _TRACES_PATH
    url = urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, "", ""))
    return TelemetryConfig(state=STATE_CONFIGURED, url=url, reason=None, parent=parent)


@dataclass(frozen=True, kw_only=True)
class PostOutcome:
    delivered: bool
    rejected_spans: int = 0


class Poster(Protocol):
    def __call__(self, *, url: str, body: bytes, timeout_seconds: float) -> PostOutcome: ...


class Reporter(Protocol):
    def __call__(self, *, text: str) -> None: ...


@dataclass(frozen=True, kw_only=True)
class DegradationReport:
    """What this process's export actually did, as plain counters."""

    state: str
    reason: str | None
    exported: int
    dropped: int
    failed: int
    rejected: int
    abandoned: int

    @property
    def degraded(self) -> bool:
        return (self.dropped + self.failed + self.rejected + self.abandoned) > 0


def http_post(*, url: str, body: bytes, timeout_seconds: float) -> PostOutcome:
    """POST one request; a transport fault or non-2xx answer is an undelivered outcome."""
    request = urllib.request.Request(  # noqa: S310 — the scheme is validated http(s).
        url,
        data=body,
        method="POST",
        headers={"content-type": "application/json"},
    )
    answer = attempt(
        action=lambda: _read_answer(request=request, timeout_seconds=timeout_seconds),
        exceptions=(urllib.error.URLError, OSError, ValueError),
    )
    if isinstance(answer, AttemptFailure):
        return PostOutcome(delivered=False)
    return PostOutcome(delivered=True, rejected_spans=_rejected_spans(text=answer))


def _read_answer(*, request: urllib.request.Request, timeout_seconds: float) -> str:
    # `urlopen` raises `HTTPError` for every non-2xx answer, so a returned
    # response IS an accepting one.
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
        return response.read().decode("utf-8", "replace")


def _rejected_spans(*, text: str) -> int:
    """The `partialSuccess.rejectedSpans` an accepting receiver reports, else 0."""
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        return 0
    if not isinstance(loaded, dict):
        return 0
    partial = cast("dict[str, object]", loaded).get("partialSuccess")
    if not isinstance(partial, dict):
        return 0
    rejected = cast("dict[str, object]", partial).get("rejectedSpans")
    try:
        return max(0, int(str(rejected)))
    except ValueError:
        return 0


def _stderr_reporter(*, text: str) -> None:
    _ = write_stderr(text=text + "\n")


@dataclass(kw_only=True)
class SessionTelemetry:
    """The bounded exporter one command invocation owns."""

    config: TelemetryConfig
    post: Poster = http_post
    reporter: Reporter = _stderr_reporter
    _queue: queue.Queue[SessionEvent] = field(init=False, repr=False)
    _stop: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _thread: threading.Thread | None = field(default=None, init=False, repr=False)
    _counts: dict[str, int] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        self._queue = queue.Queue(maxsize=self.config.queue_limit)
        self._counts = {"exported": 0, "dropped": 0, "failed": 0, "rejected": 0, "inflight": 0}

    @classmethod
    def from_environ(cls, *, environ: dict[str, str]) -> SessionTelemetry:
        return cls(config=config_from_environ(environ=environ))

    @property
    def configured(self) -> bool:
        return self.config.state == STATE_CONFIGURED

    def emit(self, *, event: SessionEvent) -> None:
        """Enqueue one event, or count it dropped; never blocks, never raises."""
        if not self.configured:
            return
        stamped = replace(event, attributes={**event.attributes, **self._export_counts()})
        self._start_worker()
        try:
            self._queue.put_nowait(stamped)
        except queue.Full:
            self._count(name="dropped", amount=1)

    def close(self) -> DegradationReport:
        """Wait the bounded shutdown allowance, abandon the rest, report once."""
        thread = self._thread
        if thread is not None:
            self._stop.set()
            thread.join(timeout=self.config.shutdown_seconds)
        report = self._report(alive=thread is not None and thread.is_alive())
        text = _report_text(report=report)
        if text is not None:
            self.reporter(text=text)
        return report

    def _export_counts(self) -> dict[str, object]:
        with self._lock:
            return {
                "session.export.dropped_count": self._counts["dropped"],
                "session.export.rejected_count": self._counts["rejected"],
                "session.export.failed_count": self._counts["failed"],
            }

    def _count(self, *, name: str, amount: int) -> None:
        with self._lock:
            self._counts[name] += amount

    def _report(self, *, alive: bool) -> DegradationReport:
        with self._lock:
            leftover = self._queue.qsize() + (self._counts["inflight"] if alive else 0)
            return DegradationReport(
                state=self.config.state,
                reason=self.config.reason,
                exported=self._counts["exported"],
                dropped=self._counts["dropped"],
                failed=self._counts["failed"],
                rejected=self._counts["rejected"],
                abandoned=leftover,
            )

    def _start_worker(self) -> None:
        with self._lock:
            if self._thread is not None:
                return
            thread = threading.Thread(target=self._run, daemon=True)
            self._thread = thread
        thread.start()

    def _run(self) -> None:
        while True:
            batch = self._next_batch()
            if batch:
                self._send(batch=batch)
            elif self._stop.is_set():
                return

    def _next_batch(self) -> list[SessionEvent]:
        try:
            batch = [self._queue.get(timeout=_WORKER_POLL_SECONDS)]
        except queue.Empty:
            return []
        while len(batch) < self.config.batch_limit:
            try:
                batch.append(self._queue.get_nowait())
            except queue.Empty:
                break
        self._count(name="inflight", amount=len(batch))
        return batch

    def _send(self, *, batch: list[SessionEvent]) -> None:
        body = json.dumps(
            request_payload(events=tuple(batch), parent=self.config.parent),
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        outcome = PostOutcome(delivered=False)
        for _ in range(self.config.attempts):
            outcome = self.post(
                url=cast("str", self.config.url),
                body=body,
                timeout_seconds=self.config.timeout_seconds,
            )
            if outcome.delivered:
                break
        rejected = min(outcome.rejected_spans, len(batch)) if outcome.delivered else 0
        self._count(name="exported", amount=len(batch) - rejected if outcome.delivered else 0)
        self._count(name="rejected", amount=rejected)
        self._count(name="failed", amount=0 if outcome.delivered else len(batch))
        self._count(name="inflight", amount=-len(batch))


def _report_text(*, report: DegradationReport) -> str | None:
    if report.state != STATE_CONFIGURED:
        return (
            f"session telemetry {report.state}: {report.reason}; "
            "wait, inventory and recovery results stay local and nothing was exported"
        )
    if not report.degraded:
        return None
    return (
        "session telemetry degraded: "
        f"exported={report.exported} dropped={report.dropped} failed={report.failed} "
        f"rejected={report.rejected} abandoned={report.abandoned}; "
        "local results are unaffected"
    )
