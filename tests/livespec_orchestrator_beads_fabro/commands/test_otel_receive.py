"""Tests for the live OTLP/HTTP RECEIVE plane (29f E1 receive layer).

Covers `_otel_receive` — the live-ingest layer the 29f.5 file-tail DATA
plane (PR #39) was deferred from: a bound loopback OTLP/HTTP receiver the
Fabro sandbox (29f.3) ships its Claude-Code OTel to, plus the
metrics-heartbeat low-latency forward path 29f.6's oyg `LivenessProbe`
reads (telemetry-pipeline-architecture.md §3.2 / §4.4).

Every assertion runs OFFLINE and self-tears-down deterministically:

- The receiver binds an EPHEMERAL port (port 0) on loopback; tests POST
  synthetic OTLP/HTTP-JSON to the bound address over a real localhost
  socket, then stop the server in a `finally` — no long-lived daemon, no
  real Fabro run, no real sandbox, no real Honeycomb network call.
- The trace egress path is the SAME injected fake `SpanExporter` seam the
  29f.5 data plane uses (no real Honeycomb call); the metrics path writes
  a heartbeat to a `tmp_path` file.
- The dispatcher start-supervise path is exercised with the server launch
  mocked — `ensure_receiver_started` is driven against a fake server
  factory so no real receiver is ever started in a test.

Load-bearing invariants under test:

- Receiver accepts `POST /v1/traces` (ExportTraceServiceRequest JSON) and
  routes the spans through the SHARED enrich/scrub seam → exporter.
- Receiver accepts `POST /v1/metrics` (ExportMetricsServiceRequest JSON)
  and advances a per-run/session heartbeat (last-metric-emit timestamp).
- Fail-CLOSED scrub on BOTH planes: a credential-shaped value never
  egresses (the span is rejected; a metric data point's credential-shaped
  attribute does not reach the heartbeat sink as a plaintext value).
- Fail-OPEN toward the pipeline: a malformed body / unknown path / a
  forward error never crashes the handler (HTTP 200/4xx, never a 500 that
  takes down the receiver), and never raises out of the host machinery.
- Single-instance, idempotent start: `ensure_receiver_started` starts ONE
  receiver per host and is a no-op when one is already running (it does
  NOT spawn a second / collide on the port). A start failure is fail-open
  (returns without raising; never blocks a dispatch).
- Env-lever addr/port resolution with committed defaults (unset env never
  means unbound).
"""

from __future__ import annotations

import http.client
import json
import urllib.error
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from socket import create_connection
from typing import cast

import pytest
from livespec_orchestrator_beads_fabro.commands._otel_receive import (
    HeartbeatSink,
    OtelReceiver,
    ReceiverConfig,
    ensure_receiver_started,
    resolve_receiver_config,
)

_HTTP_OK = 200
_HTTP_BAD_REQUEST = 400
_HTTP_NOT_FOUND = 404


# --------------------------------------------------------------------------
# Fakes + builders (no network, no real fabro, no real Honeycomb)
# --------------------------------------------------------------------------


@dataclass(kw_only=True)
class _FakeExporter:
    """Records every export call; configurable success per call."""

    succeed: bool = True
    calls: list[tuple[tuple[dict[str, object], ...], str]] = field(default_factory=list)

    def export(self, *, spans: tuple[dict[str, object], ...], dataset: str) -> bool:
        self.calls.append((spans, dataset))
        return self.succeed


@dataclass(kw_only=True)
class _RaisingExporter:
    """An exporter whose export() raises — exercises the handler's fail-open catch."""

    def export(self, *, spans: tuple[dict[str, object], ...], dataset: str) -> bool:
        _ = (spans, dataset)
        raise RuntimeError("boom")


def _attr_entry(*, key: str, string_value: str) -> dict[str, object]:
    return {"key": key, "value": {"stringValue": string_value}}


def _post_oversized_content_length(*, host: str, port: int, path: str) -> int:
    """POST with a content-length far above the receiver's cap (fail-open 400)."""
    conn = http.client.HTTPConnection(host, port, timeout=5.0)
    try:
        conn.putrequest("POST", path, skip_accept_encoding=True)
        conn.putheader("content-length", str(64 * 1024 * 1024))
        conn.endheaders()
        conn.send(b"{}")
        return conn.getresponse().status
    finally:
        conn.close()


def _send_raw_http(*, host: str, port: int, payload: bytes) -> bytes:
    """Send a raw HTTP payload and return whatever response bytes arrive."""
    with create_connection((host, port), timeout=5.0) as conn:
        conn.sendall(payload)
        conn.shutdown(1)
        return conn.recv(4096)


def _resource(*, service_name: str = "cc-sandbox") -> dict[str, object]:
    return {"attributes": [_attr_entry(key="service.name", string_value=service_name)]}


def _trace_request(
    *,
    attrs: list[dict[str, object]],
    service_name: str = "cc-sandbox",
) -> dict[str, object]:
    """One OTLP/HTTP-JSON ExportTraceServiceRequest with a single span."""
    return {
        "resourceSpans": [
            {
                "resource": _resource(service_name=service_name),
                "scopeSpans": [
                    {
                        "scope": {"name": "claude-code", "version": "1.0"},
                        "spans": [
                            {
                                "name": "agent.turn",
                                "traceId": "0af7651916cd43dd8448eb211c80319c",
                                "spanId": "b7ad6b7169203331",
                                "attributes": attrs,
                            }
                        ],
                    }
                ],
            }
        ]
    }


def _metrics_request(
    *,
    data_point_attrs: list[dict[str, object]],
    metric_name: str = "claude_code.session.count",
    shape: str = "gauge",
    resource_attrs: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """One OTLP/HTTP-JSON ExportMetricsServiceRequest with a single metric."""
    resource: dict[str, object] = (
        {"attributes": resource_attrs} if resource_attrs is not None else _resource()
    )
    return {
        "resourceMetrics": [
            {
                "resource": resource,
                "scopeMetrics": [
                    {
                        "scope": {"name": "claude-code", "version": "1.0"},
                        "metrics": [
                            {
                                "name": metric_name,
                                shape: {
                                    "dataPoints": [
                                        {
                                            "asInt": "1",
                                            "timeUnixNano": "1700000000000000000",
                                            "attributes": data_point_attrs,
                                        }
                                    ]
                                },
                            }
                        ],
                    }
                ],
            }
        ]
    }


def _run_id_attrs(*, run_id: str) -> list[dict[str, object]]:
    return [_attr_entry(key="fabro.run_id", string_value=run_id)]


def _post_json(*, url: str, body: dict[str, object]) -> int:
    """POST a JSON body to a localhost URL; return the HTTP status."""
    request = urllib.request.Request(  # noqa: S310 — fixed http://127.0.0.1 test URL.
        url,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={"content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=5.0) as response:  # noqa: S310
            return cast("int", response.status)
    except urllib.error.HTTPError as exc:
        return exc.code


def _post_raw(*, url: str, body: bytes) -> int:
    request = urllib.request.Request(url, data=body, method="POST")  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=5.0) as response:  # noqa: S310
            return cast("int", response.status)
    except urllib.error.HTTPError as exc:
        return exc.code


def _post_without_content_length(*, host: str, port: int, path: str) -> int:
    """POST with NO body / NO content-length header (fail-open bad request)."""
    conn = http.client.HTTPConnection(host, port, timeout=5.0)
    try:
        conn.putrequest("POST", path, skip_accept_encoding=True)
        conn.endheaders()
        return conn.getresponse().status
    finally:
        conn.close()


def _post_bad_content_length(*, host: str, port: int, path: str) -> int:
    """POST with a non-integer content-length header (fail-open bad request)."""
    conn = http.client.HTTPConnection(host, port, timeout=5.0)
    try:
        conn.putrequest("POST", path, skip_accept_encoding=True)
        conn.putheader("content-length", "not-a-number")
        conn.endheaders()
        conn.send(b"{}")
        return conn.getresponse().status
    finally:
        conn.close()


@pytest.fixture
def receiver_factory(
    tmp_path: Path,
) -> Iterator[tuple[OtelReceiver, _FakeExporter, HeartbeatSink, str]]:
    """A started ephemeral-port receiver + its seams; torn down on exit."""
    exporter = _FakeExporter()
    heartbeat = HeartbeatSink(path=tmp_path / "hb.json")
    receiver = OtelReceiver(
        config=ReceiverConfig(host="127.0.0.1", port=0),
        exporter=exporter,
        heartbeat=heartbeat,
    )
    receiver.start()
    base = f"http://127.0.0.1:{receiver.bound_port}"
    try:
        yield receiver, exporter, heartbeat, base
    finally:
        receiver.stop()


# --------------------------------------------------------------------------
# Env-lever resolution
# --------------------------------------------------------------------------


def test_resolve_receiver_config_defaults_when_unset() -> None:
    """An unset env never means unbound: committed loopback addr/port apply."""
    config = resolve_receiver_config(environ={})
    assert config.host == "127.0.0.1"
    assert config.port == 4318


def test_resolve_receiver_config_honors_env_levers() -> None:
    """`LIVESPEC_OTEL_RECEIVER_*` override the committed defaults."""
    config = resolve_receiver_config(
        environ={
            "LIVESPEC_OTEL_RECEIVER_HOST": "127.0.0.5",
            "LIVESPEC_OTEL_RECEIVER_PORT": "4999",
        }
    )
    assert config.host == "127.0.0.5"
    assert config.port == 4999


def test_resolve_receiver_config_unparseable_port_falls_back() -> None:
    """An unparseable port falls back to the default rather than crashing."""
    config = resolve_receiver_config(environ={"LIVESPEC_OTEL_RECEIVER_PORT": "not-a-number"})
    assert config.port == 4318


def test_resolve_receiver_config_negative_port_falls_back() -> None:
    """A negative port falls back to the default (never an invalid bind)."""
    config = resolve_receiver_config(environ={"LIVESPEC_OTEL_RECEIVER_PORT": "-7"})
    assert config.port == 4318


def test_resolve_receiver_config_blank_host_falls_back() -> None:
    """A blank/whitespace host env falls back to the committed loopback."""
    config = resolve_receiver_config(environ={"LIVESPEC_OTEL_RECEIVER_HOST": "   "})
    assert config.host == "127.0.0.1"


def test_resolve_receiver_config_ephemeral_port_allowed() -> None:
    """An explicit port 0 (ephemeral) is honored, not overridden."""
    config = resolve_receiver_config(environ={"LIVESPEC_OTEL_RECEIVER_PORT": "0"})
    assert config.port == 0


# --------------------------------------------------------------------------
# Heartbeat sink (the §4.4 metrics-heartbeat consumable)
# --------------------------------------------------------------------------


def test_heartbeat_sink_writes_last_emit_per_run(tmp_path: Path) -> None:
    """The sink records a last-metric-emit timestamp keyed by run/session."""
    sink = HeartbeatSink(path=tmp_path / "heartbeat.json")
    sink.beat(key="run-a", at=100.0)
    sink.beat(key="run-b", at=200.0)
    sink.beat(key="run-a", at=300.0)
    assert sink.last_beat(key="run-a") == 300.0
    assert sink.last_beat(key="run-b") == 200.0
    assert sink.last_beat(key="run-missing") is None


def test_heartbeat_sink_advances_only(tmp_path: Path) -> None:
    """A stale re-delivery never moves a heartbeat backward (advancing-only)."""
    sink = HeartbeatSink(path=tmp_path / "heartbeat.json")
    sink.beat(key="run-a", at=300.0)
    sink.beat(key="run-a", at=100.0)
    assert sink.last_beat(key="run-a") == 300.0


def test_heartbeat_sink_persists_across_instances(tmp_path: Path) -> None:
    """A fresh sink over the same file reads back the persisted heartbeat
    (so 29f.6's out-of-process LivenessProbe can read it)."""
    path = tmp_path / "heartbeat.json"
    HeartbeatSink(path=path).beat(key="run-a", at=42.0)
    assert HeartbeatSink(path=path).last_beat(key="run-a") == 42.0


def test_heartbeat_sink_tolerates_corrupt_file(tmp_path: Path) -> None:
    """A corrupt heartbeat file reads as empty (fail-open), not a crash."""
    path = tmp_path / "heartbeat.json"
    _ = path.write_text("}{ not json", encoding="utf-8")
    sink = HeartbeatSink(path=path)
    assert sink.last_beat(key="run-a") is None
    sink.beat(key="run-a", at=5.0)
    assert sink.last_beat(key="run-a") == 5.0


def test_heartbeat_sink_tolerates_non_object_file(tmp_path: Path) -> None:
    """A JSON file whose top level is not an object reads as empty."""
    path = tmp_path / "heartbeat.json"
    _ = path.write_text("[1, 2, 3]", encoding="utf-8")
    assert HeartbeatSink(path=path).last_beat(key="run-a") is None


def test_heartbeat_sink_skips_non_numeric_and_bool_values(tmp_path: Path) -> None:
    """Non-numeric / bool persisted values are skipped (fail-open read)."""
    path = tmp_path / "heartbeat.json"
    _ = path.write_text(
        json.dumps({"run-a": "oops", "run-b": True, "run-c": 9.0}),
        encoding="utf-8",
    )
    sink = HeartbeatSink(path=path)
    assert sink.last_beat(key="run-a") is None
    assert sink.last_beat(key="run-b") is None
    assert sink.last_beat(key="run-c") == 9.0


# --------------------------------------------------------------------------
# Live receiver — traces plane (real loopback socket, ephemeral port)
# --------------------------------------------------------------------------


def test_receiver_traces_route_through_enrich_to_exporter(
    receiver_factory: tuple[OtelReceiver, _FakeExporter, HeartbeatSink, str],
) -> None:
    """POST /v1/traces enriches+scrubs each span and batches to the exporter."""
    _receiver, exporter, _heartbeat, base = receiver_factory
    body = _trace_request(attrs=[_attr_entry(key="work.item.id", string_value="li-29f.7")])
    assert _post_json(url=f"{base}/v1/traces", body=body) == _HTTP_OK
    assert len(exporter.calls) == 1
    spans, dataset = exporter.calls[0]
    assert dataset == "cc-sandbox"
    assert len(spans) == 1


def test_receiver_traces_batch_per_dataset(
    receiver_factory: tuple[OtelReceiver, _FakeExporter, HeartbeatSink, str],
) -> None:
    """Two resourceSpans with different service.name batch to two datasets."""
    _receiver, exporter, _heartbeat, base = receiver_factory
    body: dict[str, object] = {
        "resourceSpans": [
            cast(
                "dict[str, object]", _trace_request(attrs=[], service_name="svc-a")["resourceSpans"]
            )[0],
            cast(
                "dict[str, object]", _trace_request(attrs=[], service_name="svc-b")["resourceSpans"]
            )[0],
        ]
    }
    assert _post_json(url=f"{base}/v1/traces", body=body) == _HTTP_OK
    datasets = sorted(dataset for _spans, dataset in exporter.calls)
    assert datasets == ["svc-a", "svc-b"]


def test_receiver_traces_export_failure_is_swallowed(
    tmp_path: Path,
) -> None:
    """An export that returns False never raises out of the handler (fail-open)."""
    exporter = _FakeExporter(succeed=False)
    receiver = OtelReceiver(
        config=ReceiverConfig(host="127.0.0.1", port=0),
        exporter=exporter,
        heartbeat=HeartbeatSink(path=tmp_path / "hb.json"),
    )
    receiver.start()
    try:
        url = f"http://127.0.0.1:{receiver.bound_port}/v1/traces"
        body = _trace_request(attrs=[_attr_entry(key="work.item.id", string_value="li-x")])
        assert _post_json(url=url, body=body) == _HTTP_OK
    finally:
        receiver.stop()
    assert len(exporter.calls) == 1


def test_receiver_traces_fail_closed_on_credential_shape(
    receiver_factory: tuple[OtelReceiver, _FakeExporter, HeartbeatSink, str],
) -> None:
    """A credential-shaped value in an allowlisted attr REJECTS the span:
    nothing credential-shaped ever reaches the exporter."""
    _receiver, exporter, _heartbeat, base = receiver_factory
    body = _trace_request(
        attrs=[
            _attr_entry(
                key="repo",
                string_value="https://x-access-token:ghp_SECRET@github.com/o/r",
            )
        ]
    )
    # Fail-OPEN toward the pipeline: the POST itself still succeeds.
    assert _post_json(url=f"{base}/v1/traces", body=body) == _HTTP_OK
    forwarded = [span for spans, _ in exporter.calls for span in spans]
    assert forwarded == []


def test_receiver_traces_tolerates_unexpected_shapes(
    receiver_factory: tuple[OtelReceiver, _FakeExporter, HeartbeatSink, str],
) -> None:
    """Structurally-unexpected resourceSpans content is skipped fail-open."""
    _receiver, exporter, _heartbeat, base = receiver_factory
    body: dict[str, object] = {
        "resourceSpans": [
            "not-a-dict",
            {"resource": "not-a-dict", "scopeSpans": "not-a-list"},
            {"scopeSpans": ["not-a-dict", {"spans": "not-a-list"}, {"spans": ["not-a-dict"]}]},
        ]
    }
    assert _post_json(url=f"{base}/v1/traces", body=body) == _HTTP_OK
    assert exporter.calls == []


def test_receiver_traces_missing_resource_spans_is_ok(
    receiver_factory: tuple[OtelReceiver, _FakeExporter, HeartbeatSink, str],
) -> None:
    """A request whose resourceSpans is absent / not a list is a clean no-op."""
    _receiver, exporter, _heartbeat, base = receiver_factory
    assert _post_json(url=f"{base}/v1/traces", body={"resourceSpans": "nope"}) == _HTTP_OK
    assert exporter.calls == []


# --------------------------------------------------------------------------
# Live receiver — metrics plane (heartbeat)
# --------------------------------------------------------------------------


def test_receiver_metrics_advances_heartbeat(
    receiver_factory: tuple[OtelReceiver, _FakeExporter, HeartbeatSink, str],
) -> None:
    """POST /v1/metrics advances the per-run heartbeat (§4.4 liveness signal)."""
    _receiver, _exporter, heartbeat, base = receiver_factory
    body = _metrics_request(data_point_attrs=_run_id_attrs(run_id="run-xyz"))
    # Drive this happy path through the raw poster so its 2xx return is exercised.
    assert _post_raw(url=f"{base}/v1/metrics", body=json.dumps(body).encode("utf-8")) == _HTTP_OK
    assert heartbeat.last_beat(key="run-xyz") is not None


def test_receiver_metrics_sum_shape_advances_heartbeat(
    receiver_factory: tuple[OtelReceiver, _FakeExporter, HeartbeatSink, str],
) -> None:
    """A sum-shaped (not gauge) metric also advances the heartbeat."""
    _receiver, _exporter, heartbeat, base = receiver_factory
    body = _metrics_request(data_point_attrs=_run_id_attrs(run_id="run-sum"), shape="sum")
    assert _post_json(url=f"{base}/v1/metrics", body=body) == _HTTP_OK
    assert heartbeat.last_beat(key="run-sum") is not None


def test_receiver_metrics_resource_level_id_is_fallback(
    receiver_factory: tuple[OtelReceiver, _FakeExporter, HeartbeatSink, str],
) -> None:
    """A data point with no own correlation attr falls back to a resource id."""
    _receiver, _exporter, heartbeat, base = receiver_factory
    body = _metrics_request(
        data_point_attrs=[],
        resource_attrs=[
            _attr_entry(key="service.name", string_value="cc-sandbox"),
            _attr_entry(key="work.item.id", string_value="li-res"),
        ],
    )
    assert _post_json(url=f"{base}/v1/metrics", body=body) == _HTTP_OK
    assert heartbeat.last_beat(key="li-res") is not None


def test_receiver_metrics_no_keyable_id_is_skipped(
    receiver_factory: tuple[OtelReceiver, _FakeExporter, HeartbeatSink, str],
) -> None:
    """A data point carrying no correlation id is skipped (no anonymous beat)."""
    _receiver, _exporter, heartbeat, base = receiver_factory
    body = _metrics_request(
        data_point_attrs=[_attr_entry(key="host.name", string_value="ignored")],
    )
    assert _post_json(url=f"{base}/v1/metrics", body=body) == _HTTP_OK
    assert heartbeat.last_beat(key="ignored") is None


def test_receiver_metrics_prefers_most_specific_id(
    receiver_factory: tuple[OtelReceiver, _FakeExporter, HeartbeatSink, str],
) -> None:
    """When several ids are present, fabro.run_id wins (most-specific first)."""
    _receiver, _exporter, heartbeat, base = receiver_factory
    body = _metrics_request(
        data_point_attrs=[
            _attr_entry(key="work.item.id", string_value="li-loser"),
            _attr_entry(key="fabro.run_id", string_value="run-winner"),
        ]
    )
    assert _post_json(url=f"{base}/v1/metrics", body=body) == _HTTP_OK
    assert heartbeat.last_beat(key="run-winner") is not None
    assert heartbeat.last_beat(key="li-loser") is None


def test_receiver_metrics_tolerates_unexpected_shapes(
    receiver_factory: tuple[OtelReceiver, _FakeExporter, HeartbeatSink, str],
) -> None:
    """Structurally-unexpected metrics content is skipped fail-open."""
    _receiver, _exporter, heartbeat, base = receiver_factory
    body: dict[str, object] = {
        "resourceMetrics": [
            "not-a-dict",
            {"resource": "not-a-dict", "scopeMetrics": "not-a-list"},
            {
                "scopeMetrics": [
                    "not-a-dict",
                    {"metrics": "not-a-list"},
                    {"metrics": ["not-a-dict"]},
                ]
            },
            {
                "scopeMetrics": [
                    {"metrics": [{"gauge": "not-a-dict"}, {"gauge": {"dataPoints": "no"}}]}
                ]
            },
            {"scopeMetrics": [{"metrics": [{"gauge": {"dataPoints": ["not-a-dict"]}}]}]},
        ]
    }
    assert _post_json(url=f"{base}/v1/metrics", body=body) == _HTTP_OK


def test_receiver_metrics_missing_resource_metrics_is_ok(
    receiver_factory: tuple[OtelReceiver, _FakeExporter, HeartbeatSink, str],
) -> None:
    """A request whose resourceMetrics is absent / not a list is a clean no-op."""
    _receiver, _exporter, _heartbeat, base = receiver_factory
    assert _post_json(url=f"{base}/v1/metrics", body={"resourceMetrics": "nope"}) == _HTTP_OK


def test_receiver_metrics_data_point_attr_ignores_non_string(
    receiver_factory: tuple[OtelReceiver, _FakeExporter, HeartbeatSink, str],
) -> None:
    """A correlation attr with a non-string / non-dict value block is ignored."""
    _receiver, _exporter, heartbeat, base = receiver_factory
    body = _metrics_request(
        data_point_attrs=[
            {"key": "fabro.run_id", "value": {"intValue": "5"}},
            {"key": "work.item.id", "value": "not-a-dict"},
            "not-a-dict",
        ]
    )
    assert _post_json(url=f"{base}/v1/metrics", body=body) == _HTTP_OK
    # No string-valued correlation id present -> no heartbeat written.
    assert HeartbeatSink(path=_receiver.heartbeat.path).last_beat(key="5") is None


def test_receiver_metrics_fail_closed_on_credential_attr(tmp_path: Path) -> None:
    """A credential-shaped metric-attr value never lands in the heartbeat file
    as plaintext (fail-closed scrub on the metrics plane too)."""
    path = tmp_path / "hb.json"
    receiver = OtelReceiver(
        config=ReceiverConfig(host="127.0.0.1", port=0),
        exporter=_FakeExporter(),
        heartbeat=HeartbeatSink(path=path),
    )
    receiver.start()
    try:
        url = f"http://127.0.0.1:{receiver.bound_port}/v1/metrics"
        body = _metrics_request(
            data_point_attrs=_run_id_attrs(
                run_id="https://x-access-token:ghp_SECRET@github.com/o/r",
            ),
        )
        assert _post_json(url=url, body=body) == _HTTP_OK
    finally:
        receiver.stop()
    assert "ghp_SECRET" not in path.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# Live receiver — fail-open framing (malformed / unknown / no body)
# --------------------------------------------------------------------------


def test_receiver_malformed_body_is_fail_open(
    receiver_factory: tuple[OtelReceiver, _FakeExporter, HeartbeatSink, str],
) -> None:
    """A non-JSON body never 500s / crashes the receiver (fail-open)."""
    _receiver, exporter, _heartbeat, base = receiver_factory
    assert _post_raw(url=f"{base}/v1/traces", body=b"}{ not json at all") == _HTTP_BAD_REQUEST
    assert exporter.calls == []


def test_receiver_non_object_json_body_is_bad_request(
    receiver_factory: tuple[OtelReceiver, _FakeExporter, HeartbeatSink, str],
) -> None:
    """A JSON body that is not a top-level object is a clean 400."""
    _receiver, exporter, _heartbeat, base = receiver_factory
    assert _post_raw(url=f"{base}/v1/traces", body=b"[1,2,3]") == _HTTP_BAD_REQUEST
    assert exporter.calls == []


def test_receiver_invalid_utf8_body_is_bad_request(
    receiver_factory: tuple[OtelReceiver, _FakeExporter, HeartbeatSink, str],
) -> None:
    """A body that is not valid UTF-8 is a clean 400, not a crash."""
    _receiver, _exporter, _heartbeat, base = receiver_factory
    assert _post_raw(url=f"{base}/v1/traces", body=b"\xff\xfe\xfd") == _HTTP_BAD_REQUEST


def test_receiver_missing_content_length_is_bad_request(
    receiver_factory: tuple[OtelReceiver, _FakeExporter, HeartbeatSink, str],
) -> None:
    """A POST with no content-length header is a clean 400 (fail-open)."""
    receiver, _exporter, _heartbeat, _base = receiver_factory
    status = _post_without_content_length(
        host="127.0.0.1", port=receiver.bound_port, path="/v1/traces"
    )
    assert status == _HTTP_BAD_REQUEST


def test_receiver_bad_content_length_is_bad_request(
    receiver_factory: tuple[OtelReceiver, _FakeExporter, HeartbeatSink, str],
) -> None:
    """A non-integer content-length header is a clean 400 (fail-open)."""
    receiver, _exporter, _heartbeat, _base = receiver_factory
    status = _post_bad_content_length(host="127.0.0.1", port=receiver.bound_port, path="/v1/traces")
    assert status == _HTTP_BAD_REQUEST


def test_receiver_unknown_path_404(
    receiver_factory: tuple[OtelReceiver, _FakeExporter, HeartbeatSink, str],
) -> None:
    """An unknown path is a clean 404, not a crash."""
    _receiver, _exporter, _heartbeat, base = receiver_factory
    assert _post_json(url=f"{base}/v1/nonsense", body={}) == _HTTP_NOT_FOUND


def test_receiver_non_post_request_404(
    receiver_factory: tuple[OtelReceiver, _FakeExporter, HeartbeatSink, str],
) -> None:
    """A non-POST request is a clean 404 from the composed socket handler."""
    receiver, _exporter, _heartbeat, _base = receiver_factory
    conn = http.client.HTTPConnection("127.0.0.1", receiver.bound_port, timeout=5.0)
    try:
        conn.request("GET", "/v1/traces")
        assert conn.getresponse().status == _HTTP_NOT_FOUND
    finally:
        conn.close()


def test_receiver_malformed_request_line_closes_without_response(
    receiver_factory: tuple[OtelReceiver, _FakeExporter, HeartbeatSink, str],
) -> None:
    """A malformed request line closes cleanly without crashing the receiver."""
    receiver, _exporter, _heartbeat, _base = receiver_factory
    assert _send_raw_http(host="127.0.0.1", port=receiver.bound_port, payload=b"\r\n") == b""
    assert receiver.is_running() is True


def test_receiver_metrics_malformed_body_is_bad_request(
    receiver_factory: tuple[OtelReceiver, _FakeExporter, HeartbeatSink, str],
) -> None:
    """A non-JSON body on the metrics path is a clean 400 (fail-open)."""
    _receiver, _exporter, _heartbeat, base = receiver_factory
    assert _post_raw(url=f"{base}/v1/metrics", body=b"}{ not json") == _HTTP_BAD_REQUEST


def test_receiver_oversized_body_is_bad_request(
    receiver_factory: tuple[OtelReceiver, _FakeExporter, HeartbeatSink, str],
) -> None:
    """A content-length above the receiver's cap is rejected (fail-open 400)."""
    receiver, _exporter, _heartbeat, _base = receiver_factory
    status = _post_oversized_content_length(
        host="127.0.0.1", port=receiver.bound_port, path="/v1/traces"
    )
    assert status == _HTTP_BAD_REQUEST


def test_receiver_internal_error_is_caught_fail_open(tmp_path: Path) -> None:
    """An exporter that RAISES never 500s / crashes the receiver — the handler
    catches it and answers a bad request (fail-open toward the pipeline)."""
    receiver = OtelReceiver(
        config=ReceiverConfig(host="127.0.0.1", port=0),
        exporter=_RaisingExporter(),
        heartbeat=HeartbeatSink(path=tmp_path / "hb.json"),
    )
    receiver.start()
    try:
        url = f"http://127.0.0.1:{receiver.bound_port}/v1/traces"
        body = _trace_request(attrs=[_attr_entry(key="work.item.id", string_value="li-x")])
        assert _post_raw(url=url, body=json.dumps(body).encode("utf-8")) == _HTTP_BAD_REQUEST
        # The receiver is still alive after the caught error.
        assert receiver.is_running() is True
    finally:
        receiver.stop()


def test_receiver_does_not_double_reply_after_response_write_failure(tmp_path: Path) -> None:
    """A body write failure after headers are sent is not followed by a second reply."""

    class _BodyWriteFailure:
        def write(self, data: bytes) -> int:
            if data == b"{}":
                raise BrokenPipeError("client closed")
            return len(data)

    class _FailingHandler:
        def __init__(self, *, body: bytes) -> None:
            self.headers = {"content-length": str(len(body))}
            self.path = "/v1/traces"
            self.rfile = BytesIO(body)
            self.wfile = _BodyWriteFailure()
            self.statuses: list[int] = []

        def send_response(self, *, code: object) -> None:
            self.statuses.append(int(code))

        def send_header(self, *, keyword: str, value: str) -> None:
            _ = (keyword, value)

        def end_headers(self) -> None:
            return

    payload = json.dumps(
        _trace_request(attrs=[_attr_entry(key="work.item.id", string_value="li-x")])
    ).encode("utf-8")
    handler = _FailingHandler(body=payload)
    receiver = OtelReceiver(
        config=ReceiverConfig(host="127.0.0.1", port=0),
        exporter=_FakeExporter(),
        heartbeat=HeartbeatSink(path=tmp_path / "hb.json"),
    )

    receiver.handle_post(handler=handler)

    assert handler.statuses == [_HTTP_OK]


def test_receiver_traces_tolerates_malformed_resource_attrs(
    receiver_factory: tuple[OtelReceiver, _FakeExporter, HeartbeatSink, str],
) -> None:
    """Malformed resource.attributes entries are skipped fail-open; the span
    still forwards to the default-dataset (service.name absent)."""
    _receiver, exporter, _heartbeat, base = receiver_factory
    body: dict[str, object] = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        "not-a-dict",
                        {"value": {"stringValue": "no-key"}},
                        {"key": "service.name", "value": "not-a-dict"},
                        {"key": "service.namespace", "value": {"intValue": "7"}},
                    ]
                },
                "scopeSpans": [
                    {
                        "spans": [
                            {"name": "s", "attributes": [_attr_entry(key="repo", string_value="r")]}
                        ]
                    }
                ],
            },
            {
                "resource": {"attributes": "not-a-list"},
                "scopeSpans": [{"spans": [{"name": "s2", "attributes": []}]}],
            },
        ]
    }
    assert _post_json(url=f"{base}/v1/traces", body=body) == _HTTP_OK
    # Both spans cleared scrub (no credential shape) and forwarded to the
    # default dataset (no usable service.name resource attr).
    datasets = sorted(dataset for _spans, dataset in exporter.calls)
    assert datasets == ["livespec-unknown"]


def test_heartbeat_sink_write_failure_is_fail_open(tmp_path: Path) -> None:
    """A heartbeat write to an unwritable path never raises (fail-open)."""
    # Point the sink at a path whose PARENT is a file, so mkdir + write fail.
    blocker = tmp_path / "blocker"
    _ = blocker.write_text("i am a file", encoding="utf-8")
    sink = HeartbeatSink(path=blocker / "nested" / "hb.json")
    sink.beat(key="run-a", at=1.0)
    # The write failed silently; nothing was persisted, no exception escaped.
    assert sink.last_beat(key="run-a") is None


# --------------------------------------------------------------------------
# Lifecycle — idempotent start/stop, is_running
# --------------------------------------------------------------------------


def test_receiver_start_is_idempotent(tmp_path: Path) -> None:
    """A second start() on a running receiver is a no-op (same bound port)."""
    receiver = OtelReceiver(
        config=ReceiverConfig(host="127.0.0.1", port=0),
        exporter=_FakeExporter(),
        heartbeat=HeartbeatSink(path=tmp_path / "hb.json"),
    )
    receiver.start()
    try:
        first_port = receiver.bound_port
        assert receiver.is_running() is True
        receiver.start()
        assert receiver.bound_port == first_port
    finally:
        receiver.stop()
    assert receiver.is_running() is False


def test_receiver_stop_when_never_started_is_noop(tmp_path: Path) -> None:
    """stop() on a receiver that never started is a harmless no-op."""
    receiver = OtelReceiver(
        config=ReceiverConfig(host="127.0.0.1", port=0),
        exporter=_FakeExporter(),
        heartbeat=HeartbeatSink(path=tmp_path / "hb.json"),
    )
    assert receiver.is_running() is False
    receiver.stop()
    assert receiver.is_running() is False


# --------------------------------------------------------------------------
# Dispatcher start-supervise path (server factory mocked — no real receiver)
# --------------------------------------------------------------------------


@dataclass(kw_only=True)
class _FakeServer:
    """A startable fake (the `StartableServer` shape); never binds a socket."""

    started: int = 0

    def start(self) -> None:
        self.started += 1


def test_ensure_receiver_started_is_single_instance() -> None:
    """Two ensure calls start exactly ONE receiver (shared across dispatches)."""
    holder: dict[str, object] = {}
    created: list[_FakeServer] = []

    def _factory() -> _FakeServer:
        server = _FakeServer()
        created.append(server)
        return server

    first = ensure_receiver_started(holder=holder, factory=_factory)
    second = ensure_receiver_started(holder=holder, factory=_factory)
    assert first is second
    assert len(created) == 1
    assert created[0].started == 1


def test_ensure_receiver_started_is_fail_open() -> None:
    """A start failure never raises out toward a dispatch (fail-open)."""
    holder: dict[str, object] = {}

    def _exploding_factory() -> _FakeServer:
        raise RuntimeError("port already bound")

    result = ensure_receiver_started(holder=holder, factory=_exploding_factory)
    assert result is None
    # The holder is left clean so a later call can retry.
    assert "server" not in holder
