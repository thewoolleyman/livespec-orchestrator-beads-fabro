"""Bounded host-session telemetry: catalogs, rendering and degradation.

Scenario 159 of `SPECIFICATION/scenarios.md` asks that wait, inventory and
recovery events reach Honeycomb through the existing host-local route WITHOUT
ever controlling liveness, and that export outage, partial rejection and queue
saturation are visible locally and never recursive. Inspecting an emit file
proves none of that, so these tests drive the real exporter against real
sockets: a real `OtelReceiver` is the positive control that delivery works at
all, and an export held open until the test releases it is the blocked-exporter
control that nothing waits on delivery.
"""

from __future__ import annotations

import json
import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import pytest
from livespec_orchestrator_beads_fabro.commands._otel_receive import (
    HeartbeatSink,
    OtelReceiver,
    ReceiverConfig,
)
from livespec_orchestrator_beads_fabro.commands._session_telemetry_events import (
    RECOVERY_EVENT_NAMES,
    SCOPE_NAME,
    SCOPE_VERSION,
    WAIT_EVENT_NAMES,
    SessionEvent,
    request_payload,
    rfc3339,
    session_event,
    trace_parent_from_environ,
)
from livespec_orchestrator_beads_fabro.commands._session_telemetry_export import (
    ENDPOINT_ENV,
    STATE_CONFIGURED,
    STATE_LOCAL_ONLY,
    STATE_REFUSED,
    PostOutcome,
    SessionTelemetry,
    TelemetryConfig,
    config_from_environ,
    http_post,
)

_TRACE_ID = "0af7651916cd43dd8448eb211c80319c"
_SPAN_ID = "b7ad6b7169203331"


@dataclass(kw_only=True)
class _Reports:
    lines: list[str] = field(default_factory=list)

    def __call__(self, *, text: str) -> None:
        self.lines.append(text)


@dataclass(kw_only=True)
class _CapturingExporter:
    calls: list[tuple[tuple[dict[str, object], ...], str]] = field(default_factory=list)

    def export(self, *, spans: tuple[dict[str, object], ...], dataset: str) -> bool:
        self.calls.append((spans, dataset))
        return True


def _event(
    *, name: str = "session.wait.armed", attributes: dict[str, object | None] | None = None
) -> SessionEvent:
    return session_event(
        name=name, at=1_700_000_000.0, trace_key="repo:s:w", attributes=attributes or {}
    )


# A hang guard only: every wait below ends on its event long before this, and a
# loaded host stretches the event, never the verdict.
_HANG_GUARD_SECONDS = 30.0


def _config(*, url: str, queue_limit: int = 64, batch_limit: int = 16) -> TelemetryConfig:
    return TelemetryConfig(
        state=STATE_CONFIGURED,
        url=url,
        reason=None,
        queue_limit=queue_limit,
        batch_limit=batch_limit,
        timeout_seconds=0.3,
        attempts=2,
        shutdown_seconds=0.3,
    )


def _values(*, span: dict[str, object]) -> dict[str, dict[str, object]]:
    return {
        cast("str", entry["key"]): cast("dict[str, object]", entry["value"])
        for entry in cast("list[dict[str, object]]", span["attributes"])
    }


def _refused_port() -> int:
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = int(probe.getsockname()[1])
    probe.close()
    return port


@contextmanager
def _answering_server(*, body: bytes) -> Iterator[str]:
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(8)
    response = (
        b"HTTP/1.1 200 OK\r\ncontent-type: application/json\r\n"
        + f"content-length: {len(body)}\r\nconnection: close\r\n\r\n".encode()
        + body
    )

    def serve() -> None:
        connection, _ = listener.accept()
        with connection:
            _ = connection.recv(65536)
            connection.sendall(response)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{listener.getsockname()[1]}/v1/traces"
    finally:
        thread.join(timeout=5.0)
        listener.close()


def test_an_unset_endpoint_is_visibly_local_only() -> None:
    reports = _Reports()
    calls: list[str] = []

    def post(*, url: str, body: bytes, timeout_seconds: float) -> PostOutcome:
        calls.append(url)
        del body, timeout_seconds
        return PostOutcome(delivered=True)

    telemetry = SessionTelemetry(
        config=config_from_environ(environ={}), post=post, reporter=reports
    )
    telemetry.emit(event=_event())
    report = telemetry.close()

    assert telemetry.config.state == STATE_LOCAL_ONLY
    assert calls == []
    assert report.exported == 0
    assert len(reports.lines) == 1
    assert "local-only" in reports.lines[0]
    assert ENDPOINT_ENV in reports.lines[0]
    assert "nothing was exported" in reports.lines[0]

    configured = SessionTelemetry(
        config=_config(url="http://127.0.0.1:1/v1/traces"), post=post, reporter=reports
    )
    configured.emit(event=_event())
    _ = configured.close()
    assert calls == ["http://127.0.0.1:1/v1/traces"]


@pytest.mark.parametrize(
    "endpoint",
    ["https://api.honeycomb.io", "https://api.eu1.honeycomb.io/v1/traces", "not a url", "ftp://h"],
)
def test_a_direct_or_malformed_endpoint_is_refused_and_reported(endpoint: str) -> None:
    reports = _Reports()
    telemetry = SessionTelemetry(
        config=config_from_environ(environ={ENDPOINT_ENV: endpoint}), reporter=reports
    )
    telemetry.emit(event=_event())
    _ = telemetry.close()

    assert telemetry.config.state == STATE_REFUSED
    assert telemetry.config.url is None
    assert len(reports.lines) == 1
    assert "refused" in reports.lines[0]


def test_the_endpoint_is_normalised_to_the_traces_surface() -> None:
    for raw in (
        "http://127.0.0.1:4318",
        "http://127.0.0.1:4318/",
        "http://127.0.0.1:4318/v1/traces",
    ):
        config = config_from_environ(environ={ENDPOINT_ENV: raw})
        assert config.state == STATE_CONFIGURED
        assert config.url == "http://127.0.0.1:4318/v1/traces"


def test_a_real_receiver_delivers_the_typed_scrubbed_event(tmp_path: Path) -> None:
    exporter = _CapturingExporter()
    receiver = OtelReceiver(
        config=ReceiverConfig(host="127.0.0.1", port=0),
        exporter=exporter,
        heartbeat=HeartbeatSink(path=tmp_path / "beats.json"),
    )
    receiver.start()
    reports = _Reports()
    try:
        telemetry = SessionTelemetry(
            config=config_from_environ(
                environ={ENDPOINT_ENV: f"http://127.0.0.1:{receiver.bound_port}"}
            ),
            reporter=reports,
        )
        telemetry.emit(
            event=_event(
                attributes={
                    "session.wait.id": "wait-1",
                    "session.wait.elapsed_seconds": 1.5,
                    "session.inventory.wait_count": 0,
                    "session.observation.unavailable": ["record"],
                    "session.wait.command": "rm -rf /",
                }
            )
        )
        report = telemetry.close()
    finally:
        receiver.stop()

    assert report.exported == 1
    assert not report.degraded
    assert reports.lines == []
    assert [dataset for _, dataset in exporter.calls] == ["livespec-dispatcher"]
    span = exporter.calls[0][0][0]
    assert span["name"] == "session.wait.armed"
    values = _values(span=span)
    assert values["session.wait.elapsed_seconds"] == {"doubleValue": 1.5}
    assert values["session.inventory.wait_count"] == {"intValue": "0"}
    assert values["session.observation.unavailable"] == {
        "arrayValue": {"values": [{"stringValue": "record"}]}
    }
    assert values["session.export.dropped_count"] == {"intValue": "0"}
    assert "session.wait.command" not in values


def test_a_blocked_exporter_never_delays_emit_and_close_is_bounded() -> None:
    """Emit and close both return while the export they started is still blocked.

    The bound is an ORDERING, not a stopwatch: the post is held until the test
    releases it, so an emit that waited on the export, or a close that waited
    for it rather than abandoning it after its shutdown allowance, could only
    return after the release. The hold's own timeout is a hang guard, far
    longer than any healthy return, and never the bound under test.
    """
    entered = threading.Event()
    release = threading.Event()
    post_returned = threading.Event()

    def blocked_post(*, url: str, body: bytes, timeout_seconds: float) -> PostOutcome:
        del url, body, timeout_seconds
        entered.set()
        _ = release.wait(timeout=_HANG_GUARD_SECONDS)
        post_returned.set()
        return PostOutcome(delivered=False)

    reports = _Reports()
    telemetry = SessionTelemetry(
        config=_config(url="http://127.0.0.1:1/v1/traces"), post=blocked_post, reporter=reports
    )
    for _ in range(3):
        telemetry.emit(event=_event())
    emits_returned_while_blocked = not post_returned.is_set()
    assert entered.wait(timeout=_HANG_GUARD_SECONDS), "the export never started"
    report = telemetry.close()
    close_returned_while_blocked = not post_returned.is_set()
    release.set()
    # The abandoned post still finishes once released; waiting for it keeps the
    # worker from outliving the case. A hang guard, never the verdict.
    assert post_returned.wait(timeout=_HANG_GUARD_SECONDS)

    assert emits_returned_while_blocked
    assert close_returned_while_blocked
    assert report.abandoned >= 1
    assert report.exported == 0
    assert len(reports.lines) == 1
    assert reports.lines[0].startswith("session telemetry degraded")


def test_an_unavailable_receiver_is_counted_failed_after_bounded_attempts() -> None:
    attempts: list[str] = []

    def counting_post(*, url: str, body: bytes, timeout_seconds: float) -> PostOutcome:
        attempts.append(url)
        return http_post(url=url, body=body, timeout_seconds=timeout_seconds)

    reports = _Reports()
    telemetry = SessionTelemetry(
        config=_config(url=f"http://127.0.0.1:{_refused_port()}/v1/traces"),
        post=counting_post,
        reporter=reports,
    )
    telemetry.emit(event=_event())
    report = telemetry.close()

    assert len(attempts) == 2
    assert report.failed == 1
    assert report.exported == 0
    assert len(reports.lines) == 1
    assert reports.lines[0].startswith(
        "session telemetry degraded: exported=0 dropped=0 failed=1 rejected=0 abandoned=0;"
    )
    assert reports.lines[0].endswith("local results are unaffected")


def test_a_partially_rejecting_receiver_is_counted_rejected() -> None:
    reports = _Reports()
    with _answering_server(body=b'{"partialSuccess":{"rejectedSpans":"1"}}') as url:
        telemetry = SessionTelemetry(config=_config(url=url), reporter=reports)
        telemetry.emit(event=_event())
        report = telemetry.close()

    assert report.rejected == 1
    assert report.exported == 0
    assert report.failed == 0
    assert "rejected=1" in reports.lines[0]


def test_queue_saturation_drops_without_blocking_and_the_count_rides_later_events() -> None:
    entered = threading.Event()
    release = threading.Event()
    returned = threading.Event()
    bodies: list[bytes] = []

    def gated_post(*, url: str, body: bytes, timeout_seconds: float) -> PostOutcome:
        del url, timeout_seconds
        bodies.append(body)
        entered.set()
        _ = release.wait(timeout=_HANG_GUARD_SECONDS)
        returned.set()
        return PostOutcome(delivered=True)

    reports = _Reports()
    telemetry = SessionTelemetry(
        config=_config(url="http://127.0.0.1:1/v1/traces", queue_limit=2, batch_limit=1),
        post=gated_post,
        reporter=reports,
    )
    telemetry.emit(event=_event())
    assert entered.wait(timeout=_HANG_GUARD_SECONDS)
    for _ in range(10):
        telemetry.emit(event=_event())
    # Every emit returned while the export is still held, so none of them
    # blocked on the full queue: a blocking put could only return after the post.
    assert not returned.is_set()
    release.set()
    deadline = time.monotonic() + _HANG_GUARD_SECONDS
    while len(bodies) < 3 and time.monotonic() < deadline:
        time.sleep(0.01)
    telemetry.emit(event=_event(name="session.wait.returned"))
    report = telemetry.close()

    assert report.dropped == 8
    assert "dropped=8" in reports.lines[0]
    last = json.loads(bodies[-1])["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    assert last["name"] == "session.wait.returned"
    assert _values(span=last)["session.export.dropped_count"] == {"intValue": "8"}


def test_the_event_catalogs_are_closed_and_absent_values_are_omitted() -> None:
    assert WAIT_EVENT_NAMES == (
        "session.wait.armed",
        "session.wait.observed",
        "session.wait.returned",
        "session.wait.acknowledged",
        "session.wait.inventory",
    )
    assert RECOVERY_EVENT_NAMES == (
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
    with pytest.raises(ValueError, match="closed session event catalogs"):
        _ = session_event(name="session.wait.invented", at=1.0, trace_key="k", attributes={})

    event = _event(
        attributes={
            "session.wait.id": "w",
            "session.wait.remaining_seconds": 0.0,
            "session.wait.overdue_seconds": None,
            "session.observation.age_seconds": float("nan"),
        }
    )

    assert event.attributes == {"session.wait.id": "w", "session.wait.remaining_seconds": 0.0}


def test_a_wait_has_one_stable_trace_and_distinct_spans_under_the_versioned_scope() -> None:
    first = _event(attributes={"session.observation.sequence": 1})
    second = _event(name="session.wait.returned", attributes={"session.observation.sequence": 2})
    other = session_event(
        name="session.wait.armed", at=1.0, trace_key="repo:s:other", attributes={}
    )

    payload = request_payload(events=(first, second, other), parent=None)

    resource = cast("list[dict[str, object]]", payload["resourceSpans"])[0]
    resource_values = _values(span=cast("dict[str, object]", resource["resource"]))
    assert resource_values["service.name"] == {"stringValue": "livespec-dispatcher"}
    assert resource_values["service.namespace"] == {"stringValue": "livespec-family"}
    scope = cast("list[dict[str, object]]", resource["scopeSpans"])[0]
    assert scope["scope"] == {"name": SCOPE_NAME, "version": SCOPE_VERSION}
    assert SCOPE_NAME == "livespec.orchestrator.session_wait"
    spans = cast("list[dict[str, object]]", scope["spans"])
    assert spans[0]["traceId"] == spans[1]["traceId"] != spans[2]["traceId"]
    assert spans[0]["spanId"] != spans[1]["spanId"]
    assert len(cast("str", spans[0]["traceId"])) == 32
    assert len(cast("str", spans[0]["spanId"])) == 16


def test_an_existing_trace_parent_is_used_and_an_invalid_one_is_ignored() -> None:
    parent = trace_parent_from_environ(environ={"TRACEPARENT": f"00-{_TRACE_ID}-{_SPAN_ID}-01"})
    assert parent is not None
    payload = request_payload(events=(_event(),), parent=parent)
    span = cast(
        "list[dict[str, object]]",
        cast(
            "list[dict[str, object]]",
            cast("list[dict[str, object]]", payload["resourceSpans"])[0]["scopeSpans"],
        )[0]["spans"],
    )[0]
    assert span["traceId"] == _TRACE_ID
    assert span["parentSpanId"] == _SPAN_ID

    zero = "0" * 32
    for invalid in (f"00-{zero}-{_SPAN_ID}-01", f"00-{_TRACE_ID}-{'0' * 16}-01", "garbage", ""):
        assert trace_parent_from_environ(environ={"TRACEPARENT": invalid}) is None


def test_instants_render_as_utc_rfc3339() -> None:
    assert rfc3339(at=1_700_000_000.0) == "2023-11-14T22:13:20Z"
