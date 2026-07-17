"""Socket-level OTLP/HTTP POST handling for the live receiver."""

from __future__ import annotations

from contextlib import ExitStack, suppress
from email.message import Message
from http import HTTPStatus
from http.client import parse_headers
from socket import SHUT_WR, socket
from typing import IO, TYPE_CHECKING, Protocol, cast

from livespec_orchestrator_beads_fabro.effects import (
    AttemptFailure,
    JsonParseFailure,
    attempt,
    parse_json,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._otel_receive import OtelReceiver

__all__: list[str] = [
    "HttpPostHandler",
    "SocketHttpPostHandler",
    "drain_socket_body",
    "read_json_body",
    "reply",
]

_MAX_BODY_BYTES = 8 * 1024 * 1024
_DRAIN_CHUNK_BYTES = 64 * 1024
_DRAIN_TIMEOUT_SECONDS = 2.0


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


class SocketHttpPostHandler:
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
        with ExitStack() as stack:
            _ = stack.callback(self._cleanup)
            self._serve_one()

    def _cleanup(self) -> None:
        with suppress(OSError):
            self._request.settimeout(_DRAIN_TIMEOUT_SECONDS)
            self._request.shutdown(SHUT_WR)
        _ = drain_socket_body(rfile=self.rfile, cap=_MAX_BODY_BYTES)
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
        reply(handler=self, status=HTTPStatus.NOT_FOUND)

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


def reply(*, handler: HttpPostHandler, status: HTTPStatus) -> None:
    """Send a tiny JSON OTLP-style response (empty partial-success)."""
    body = b"{}"
    sent = attempt(
        action=lambda: _send_reply(handler=handler, status=status, body=body),
        exceptions=(OSError,),
    )
    if isinstance(sent, AttemptFailure):
        return


def _send_reply(*, handler: HttpPostHandler, status: HTTPStatus, body: bytes) -> None:
    handler.send_response(code=status)
    handler.send_header(keyword="content-type", value="application/json")
    handler.send_header(keyword="content-length", value=str(len(body)))
    handler.end_headers()
    _ = handler.wfile.write(body[:0])
    _ = handler.wfile.write(body)


def read_json_body(*, handler: HttpPostHandler) -> dict[str, object] | None:  # noqa: PLR0911
    """Read + JSON-parse the request body; None on any malformed/oversized body."""
    raw_length = handler.headers.get("content-length")
    if raw_length is None:
        return None
    length = attempt(action=lambda: int(raw_length), exceptions=(ValueError,))
    if isinstance(length, AttemptFailure):
        return None
    if length < 0 or length > _MAX_BODY_BYTES:
        return None
    body = handler.rfile.read(length)
    decoded = attempt(action=lambda: body.decode("utf-8"), exceptions=(UnicodeDecodeError,))
    if isinstance(decoded, AttemptFailure):
        return None
    parsed = parse_json(text=decoded)
    if isinstance(parsed, JsonParseFailure):
        return None
    if not isinstance(parsed, dict):
        return None
    return cast("dict[str, object]", parsed)


def drain_socket_body(*, rfile: IO[bytes], cap: int) -> int:
    """Read + discard up to `cap` bytes of still-unread request body."""
    drained = 0
    while drained < cap:
        to_read = min(_DRAIN_CHUNK_BYTES, cap - drained)
        chunk = attempt(
            action=lambda to_read=to_read: rfile.read(to_read),
            exceptions=(OSError,),
        )
        if isinstance(chunk, AttemptFailure):
            return drained
        if not chunk:
            return drained
        drained += len(chunk)
    return drained
