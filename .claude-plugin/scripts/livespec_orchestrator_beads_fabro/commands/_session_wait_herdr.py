"""Bounded native transport for one Herdr socket-API observation."""

from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import cast

__all__: list[str] = [
    "DIAGNOSTIC_MISSING",
    "DIAGNOSTIC_UNAVAILABLE",
    "DIAGNOSTIC_UNREADABLE",
    "HerdrChannel",
    "HerdrReply",
    "herdr_socket_generation",
]

# The three ends a reply can reach that are not a pane state. They are
# SEPARATE values rather than one shared diagnostic because each names a
# different repair: a pane the server no longer holds is gone for good, a
# reply that could not be read is a protocol or version fault, and an
# unreachable server is a transport fault that may clear on its own.
DIAGNOSTIC_MISSING = "MISSING"
DIAGNOSTIC_UNAVAILABLE = "UNAVAILABLE"
DIAGNOSTIC_UNREADABLE = "UNREADABLE"

# Every error code with which this server reports that the target itself is
# not there. Anything else it names is a measurement that failed rather than a
# verdict about the pane, so it stays UNAVAILABLE.
_MISSING_ERROR_CODES = frozenset(
    {
        "agent_not_found",
        "pane_not_found",
        "terminal_not_found",
    }
)

_AGENT_METHOD = "agent.get"
_REQUEST_ID = "livespec-session-wait"
_RECEIVE_BYTES = 65536
# A reply this probe will accumulate before it stops reading. The shared
# deadline already bounds how LONG a peer may stream, but not how MANY bytes
# it streams inside that budget, and a peer that never sends a newline would
# otherwise grow this buffer for the whole budget. A truncated buffer does not
# parse, so hitting the ceiling surfaces as an unreadable reply.
_REPLY_CEILING_BYTES = 1 << 20


@dataclass(frozen=True, kw_only=True)
class HerdrReply:
    agent: dict[str, object] | None
    diagnostic: str | None


def herdr_socket_generation(*, socket_path: Path) -> str | None:
    """This server instance's generation, or None when its socket is absent.

    A Herdr server binds a FRESH socket file every time it starts, so the
    socket's own identity plus its creation time distinguish one server
    instance from the next at the SAME path. Measured on herdr 0.9.3: across a
    restart the inode NUMBER was reused while the creation time moved, so the
    inode alone is not a generation and would report a different server as the
    one that was armed. The triple is what actually changes.
    """
    try:
        status = socket_path.stat()
    except OSError:
        return None
    return f"{status.st_dev}:{status.st_ino}:{status.st_ctime_ns}"


@dataclass(kw_only=True)
class HerdrChannel:
    """One bounded request to a Herdr server over its unix socket API."""

    socket_path: Path
    timeout_seconds: float

    def agent_info(self, *, pane_id: str) -> HerdrReply:
        """Ask this server for one pane's agent record, within the budget."""
        request = json.dumps(
            {
                "id": _REQUEST_ID,
                "method": _AGENT_METHOD,
                "params": {"target": pane_id},
            }
        )
        try:
            raw = self._exchange(request=request)
        except OSError:
            # Connect, send, receive and the expiry of this socket's own
            # timeout all surface as OSError, and none of them is a verdict
            # about the pane: they say this probe could not reach the server.
            # Reporting that as unavailable rather than as a pane state is
            # what keeps an unreachable server from reading as a finished one.
            return HerdrReply(agent=None, diagnostic=DIAGNOSTIC_UNAVAILABLE)
        return _parse_reply(raw=raw)

    def _exchange(self, *, request: str) -> str:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
            channel.settimeout(self.timeout_seconds)
            channel.connect(str(self.socket_path))
            channel.sendall(request.encode("utf-8") + b"\n")
            return _read_line(channel=channel)


def _read_line(*, channel: socket.socket) -> str:
    """The first reply line, bounded in bytes as well as by the socket budget."""
    buffer = bytearray()
    while b"\n" not in buffer and len(buffer) <= _REPLY_CEILING_BYTES:
        chunk = channel.recv(_RECEIVE_BYTES)
        if not chunk:
            break
        buffer.extend(chunk)
    return bytes(buffer).split(b"\n", 1)[0].decode("utf-8", errors="replace")


def _mapping(*, value: object) -> dict[str, object] | None:
    return cast("dict[str, object]", value) if isinstance(value, dict) else None


def _parse_reply(*, raw: str) -> HerdrReply:
    """One reply, read as either an agent record or exactly one diagnostic.

    The ORDER is load-bearing. A well-formed ERROR object is read before the
    success shape, because an error reply has no `result` and would otherwise
    fall through to the unreadable arm — which would report a server that
    answered clearly, naming the pane as absent, as a server whose reply
    could not be parsed.
    """
    payload = _mapping(value=_decoded(raw=raw))
    if payload is None:
        return HerdrReply(agent=None, diagnostic=DIAGNOSTIC_UNREADABLE)
    error = _mapping(value=payload.get("error"))
    if error is not None:
        return HerdrReply(agent=None, diagnostic=_error_diagnostic(error=error))
    result = _mapping(value=payload.get("result"))
    agent = None if result is None else _mapping(value=result.get("agent"))
    if agent is None:
        return HerdrReply(agent=None, diagnostic=DIAGNOSTIC_UNREADABLE)
    return HerdrReply(agent=agent, diagnostic=None)


def _decoded(*, raw: str) -> object | None:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _error_diagnostic(*, error: dict[str, object]) -> str:
    """Whether a named server error is about the TARGET or the measurement."""
    code = error.get("code")
    if isinstance(code, str) and code in _MISSING_ERROR_CODES:
        return DIAGNOSTIC_MISSING
    return DIAGNOSTIC_UNAVAILABLE
