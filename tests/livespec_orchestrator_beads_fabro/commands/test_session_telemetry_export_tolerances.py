"""Tolerances of the bounded session exporter: odd receiver answers and defaults.

A receiver that answers badly must degrade the export, never the caller. These
cases pin the answers `test_session_telemetry_export` does not reach: a non-2xx
status, bodies that are not an OTLP partial-success, the default stderr report
and the idle worker that must keep polling until it is told to stop.
"""

from __future__ import annotations

import socket
import threading
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from livespec_orchestrator_beads_fabro.commands._session_telemetry_events import (
    SessionEvent,
    session_event,
    trace_parent_from_environ,
)
from livespec_orchestrator_beads_fabro.commands._session_telemetry_export import (
    ENDPOINT_ENV,
    PostOutcome,
    SessionTelemetry,
    config_from_environ,
    http_post,
)

# The poll that can only happen after an idle one: event, then empty, then this.
_IDLE_PROOF_POLLS = 3


@contextmanager
def _answering_server(*, status: int, body: bytes) -> Iterator[str]:
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(8)
    response = (
        f"HTTP/1.1 {status} X\r\ncontent-length: {len(body)}\r\nconnection: close\r\n\r\n".encode()
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


def test_a_non_success_status_is_an_undelivered_outcome() -> None:
    with _answering_server(status=503, body=b"") as url:
        outcome = http_post(url=url, body=b"{}", timeout_seconds=1.0)

    assert not outcome.delivered
    assert outcome.rejected_spans == 0


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        b"[1]",
        b'{"partialSuccess": 3}',
        b'{"partialSuccess": {"rejectedSpans": "x"}}',
        b"{}",
    ],
)
def test_an_accepting_answer_without_a_usable_rejection_count_rejects_nothing(
    body: bytes,
) -> None:
    with _answering_server(status=200, body=body) as url:
        outcome = http_post(url=url, body=b"{}", timeout_seconds=1.0)

    assert outcome.delivered
    assert outcome.rejected_spans == 0


def test_the_default_report_goes_to_stderr_and_an_idle_worker_keeps_polling(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unset = SessionTelemetry.from_environ(environ={})
    _ = unset.close()
    assert "local-only" in capsys.readouterr().err

    with _answering_server(status=200, body=b"{}") as url:
        posted = threading.Event()

        def observed_post(*, url: str, body: bytes, timeout_seconds: float) -> PostOutcome:
            outcome = http_post(url=url, body=body, timeout_seconds=timeout_seconds)
            posted.set()
            return outcome

        # The worker's THIRD batch poll proves it polled once idle and kept
        # going: the first poll takes the one event, the second finds the queue
        # empty with no stop requested, and only a worker that keeps polling
        # makes a third. Waiting on that event, rather than sleeping and hoping
        # the worker idled meanwhile, is what keeps a loaded host from deciding
        # either the verdict or which branch the run exercised.
        polls: list[None] = []
        third_poll = threading.Event()
        next_batch = SessionTelemetry._next_batch  # noqa: SLF001

        def counted_next_batch(self: SessionTelemetry) -> list[SessionEvent]:
            polls.append(None)
            if len(polls) == _IDLE_PROOF_POLLS:
                third_poll.set()
            return next_batch(self)

        monkeypatch.setattr(SessionTelemetry, "_next_batch", counted_next_batch)
        telemetry = SessionTelemetry(
            config=config_from_environ(environ={ENDPOINT_ENV: url}), post=observed_post
        )
        telemetry.emit(
            event=session_event(name="session.wait.armed", at=1.0, trace_key="k", attributes={})
        )
        # Closed only once the delivery has landed and the worker has idled, so
        # the export is decided by events. The timeouts are hang guards only.
        assert posted.wait(timeout=30.0), "the export was never posted"
        assert third_poll.wait(timeout=30.0), "the idle worker stopped polling"
        report = telemetry.close()

    assert report.exported == 1
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize(
    "traceparent",
    [
        "00-zzaf7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01",
        "00-0af7651916cd43dd8448eb211c80319c-zzad6b7169203331-01",
        "00-0af7651916cd43dd8448eb211c80319-b7ad6b7169203331-01",
    ],
)
def test_a_trace_parent_with_a_non_hex_or_short_id_is_ignored(traceparent: str) -> None:
    assert trace_parent_from_environ(environ={"TRACEPARENT": traceparent}) is None
