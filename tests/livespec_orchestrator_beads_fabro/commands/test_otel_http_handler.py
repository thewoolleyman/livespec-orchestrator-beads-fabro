"""Tests for the socket-level OTLP/HTTP handler helpers."""

from __future__ import annotations

from io import BytesIO

from livespec_orchestrator_beads_fabro.commands._otel_http_handler import drain_socket_body


def test_drain_socket_body_stops_at_eof_below_cap() -> None:
    """The drain reads + discards all remaining bytes, stopping at EOF."""
    source = BytesIO(b"ab")
    assert drain_socket_body(rfile=source, cap=1 << 20) == 2


def test_drain_socket_body_stops_at_cap_without_over_reading() -> None:
    """The drain never reads past the cap (the oversized-body DoS bound holds)."""
    source = BytesIO(b"0123456789")
    assert drain_socket_body(rfile=source, cap=4) == 4
    # The bytes beyond the cap are left untouched -- the drain stopped exactly
    # at the cap rather than swallowing the whole (potentially huge) body.
    assert source.read() == b"456789"


def test_drain_socket_body_is_fail_open_on_oserror() -> None:
    """A read that raises OSError (timed-out / reset socket) never propagates."""

    class _RaisingReader:
        def read(self, size: int = -1) -> bytes:
            _ = size
            raise OSError("connection reset during drain")

    assert drain_socket_body(rfile=_RaisingReader(), cap=1 << 20) == 0
