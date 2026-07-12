"""Tests for the file-tail OTLP egress DRIVER (`_otel_enrich_driver`).

The 29f.5 `EnrichStage` data plane was built but never driven, so the host span
files the dispatcher + reflector write had ZERO egress. `OtelEnrichDriver` is the
missing production pump: a periodic daemon-thread that tails each span-file kind
and forwards it to Honeycomb, with an `atexit`/`stop()` FINAL flush so spans
written at dispatch END (after the last periodic poll) still egress.

Every assertion runs OFFLINE and deterministically — the Honeycomb egress is the
injected `SpanExporter` fake (no real network), the span files are `tmp_path`
JSONL, and the background thread is observed via a bounded `threading.Event`
signal (never a fixed sleep), so nothing here is timing-flaky:

- `forward_all` tails EVERY span-file stage and batches each to the exporter
  (proves the three host span-file kinds egress).
- the periodic daemon thread drives `forward_all` while running (bounded-signal
  observed), and `stop()`/atexit FINAL-flushes spans written just before
  shutdown — the load-bearing timing fix for the end-written reflection spans.
- lifecycle: idempotent start, no-op stop when never started, `is_running`.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._otel_enrich import EnrichStage
from livespec_orchestrator_beads_fabro.commands._otel_enrich_driver import OtelEnrichDriver

_SIGNAL_TIMEOUT = 5.0


@dataclass(kw_only=True)
class _FakeExporter:
    """Records every export call; optionally signals an Event when called.

    Satisfies the `SpanExporter` Protocol (`export(*, spans, dataset) -> bool`),
    so a real `EnrichStage` forwards through it with no network. The optional
    `signal` lets a test observe the background thread's forward pass via a
    bounded `Event.wait` rather than a flaky fixed sleep.
    """

    calls: list[tuple[tuple[dict[str, object], ...], str]] = field(default_factory=list)
    signal: threading.Event | None = None

    def export(self, *, spans: tuple[dict[str, object], ...], dataset: str) -> bool:
        self.calls.append((spans, dataset))
        if self.signal is not None:
            self.signal.set()
        return True


def _span_line(*, service_name: str) -> str:
    """One OTLP/HTTP-JSON ExportTraceServiceRequest line (the file-tail format)."""
    request: dict[str, object] = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": service_name}}]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "livespec.dispatcher", "version": "1.0"},
                        "spans": [
                            {
                                "name": "dispatch.reflect",
                                "traceId": "0af7651916cd43dd8448eb211c80319c",
                                "spanId": "b7ad6b7169203331",
                                "attributes": [],
                            }
                        ],
                    }
                ],
            }
        ]
    }
    return json.dumps(request) + "\n"


def _write_span_file(*, path: Path, service_name: str) -> None:
    _ = path.write_text(_span_line(service_name=service_name), encoding="utf-8")


def _stage(*, path: Path, exporter: _FakeExporter) -> EnrichStage:
    return EnrichStage(spans_path=path, exporter=exporter)


def test_forward_all_forwards_each_span_file(tmp_path: Path) -> None:
    """A forward pass tails EVERY span-file stage and batches each to Honeycomb.

    This is the core of the fix: the three per-journal host span-file kinds
    (reflection / reflector-oob / cost-report) each egress to their own dataset
    instead of staying dark."""
    exporter = _FakeExporter()
    kinds = {
        tmp_path / "j-reflection-spans.jsonl": "livespec-dispatcher",
        tmp_path / "j-reflector-oob-spans.jsonl": "livespec-rgr",
        tmp_path / "j-cost-report-spans.jsonl": "livespec-dispatcher-cost",
    }
    for path, service_name in kinds.items():
        _write_span_file(path=path, service_name=service_name)
    driver = OtelEnrichDriver(stages=tuple(_stage(path=path, exporter=exporter) for path in kinds))

    driver.forward_all()

    datasets = sorted(dataset for _spans, dataset in exporter.calls)
    assert datasets == sorted(kinds.values())


def test_forward_all_skips_absent_span_files(tmp_path: Path) -> None:
    """A stage whose span file does not exist yet is a clean fail-open no-op."""
    exporter = _FakeExporter()
    driver = OtelEnrichDriver(
        stages=(_stage(path=tmp_path / "never-written.jsonl", exporter=exporter),)
    )

    driver.forward_all()

    assert exporter.calls == []


def test_periodic_thread_forwards_while_running(tmp_path: Path) -> None:
    """The daemon thread drives `forward_all` on its poll cadence while running.

    Observed via a bounded `Event` signal (not a sleep): a span file present at
    start is forwarded within the tiny poll interval."""
    signal = threading.Event()
    exporter = _FakeExporter(signal=signal)
    path = tmp_path / "j-reflection-spans.jsonl"
    _write_span_file(path=path, service_name="livespec-dispatcher")
    driver = OtelEnrichDriver(stages=(_stage(path=path, exporter=exporter),), interval_seconds=0.01)
    driver.start()
    try:
        assert signal.wait(timeout=_SIGNAL_TIMEOUT) is True
    finally:
        driver.stop()
    assert exporter.calls != []


def test_stop_final_flush_egresses_end_written_spans(tmp_path: Path) -> None:
    """`stop()` FINAL-flushes spans written after the last periodic poll.

    This is the load-bearing timing fix: the reflection / reflector span files
    are written at dispatch END, so a dispatch that returns before the next poll
    still egresses them via the flush `stop()` (and the `atexit` hook it mirrors)
    runs. A LARGE interval guarantees NO periodic poll fires during the test, so
    the flush in `stop()` is unambiguously what forwards the span."""
    exporter = _FakeExporter()
    path = tmp_path / "j-reflection-spans.jsonl"
    driver = OtelEnrichDriver(
        stages=(_stage(path=path, exporter=exporter),), interval_seconds=3600.0
    )
    driver.start()
    try:
        # Written AFTER start; the 3600s-interval poll cannot have fired.
        _write_span_file(path=path, service_name="livespec-dispatcher")
        assert exporter.calls == []
    finally:
        driver.stop()
    # Only the FINAL flush in stop() could have forwarded it.
    assert [dataset for _spans, dataset in exporter.calls] == ["livespec-dispatcher"]


def test_start_is_idempotent(tmp_path: Path) -> None:
    """A second start() on a running driver is a no-op early-return, not a
    second thread; a single stop() then cleanly winds the driver down."""
    exporter = _FakeExporter()
    driver = OtelEnrichDriver(
        stages=(_stage(path=tmp_path / "j.jsonl", exporter=exporter),), interval_seconds=3600.0
    )
    driver.start()
    try:
        assert driver.is_running() is True
        driver.start()
        assert driver.is_running() is True
    finally:
        driver.stop()
    assert driver.is_running() is False


def test_stop_when_never_started_is_noop(tmp_path: Path) -> None:
    """stop() on a driver that never started is a harmless no-op (still flushes)."""
    exporter = _FakeExporter()
    driver = OtelEnrichDriver(stages=(_stage(path=tmp_path / "absent.jsonl", exporter=exporter),))
    assert driver.is_running() is False
    driver.stop()
    assert driver.is_running() is False
    assert exporter.calls == []
