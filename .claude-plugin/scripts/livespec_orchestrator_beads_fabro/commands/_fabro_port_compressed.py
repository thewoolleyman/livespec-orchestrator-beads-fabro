"""A Fabro HTTP transport that asks for a compressed body and bounds the WHOLE read.

WHY COMPRESSION. A run's record carries every stage's captured command output,
and that output is text. Measured 2026-11-03 on petri run
01M6G8QJR80VH8T53MBGVEBP9E (bd-ib-fhmpik): `/api/v1/runs/{id}/state` returned
10.4 MB, 8.6 MB of it one stage's output, and took 27.7-30.4 s. The same request
carrying `Accept-Encoding: gzip` took 0.92 s for 1.0 MB on the wire. The server
was already able to compress; the 30 s was transfer, not server work, and the
engine CLI's `inspect` never asks for it.

WHY A WHOLE-READ DEADLINE. urllib's `timeout` bounds each socket operation, not
the exchange: a body that keeps trickling in never trips it, so a "bounded" read
of a large record could still take minutes. This transport reads the body in
chunks and abandons it once the elapsed time passes the bound, which it reports
as a `TimeoutError` -- status 0, the transport-fault answer, exactly as
`_fabro_port_http` defines it.

The plain transport in `_fabro_port_http` is left as it is. Its callers read
small bodies, and changing what every request asks for is a wider change than
the one this record read needs.
"""

from __future__ import annotations

import gzip
import time
import urllib.error
import urllib.request
import zlib
from collections.abc import Callable
from dataclasses import dataclass, field

from livespec_orchestrator_beads_fabro.commands._fabro_port_http import FabroHttpResult
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

__all__: list[str] = ["CompressedUrllibTransport"]

_CHUNK_BYTES = 65536
_GZIP = "gzip"
_HTTP_SUCCESS_FLOOR = 200
_HTTP_SUCCESS_CEILING = 300


@dataclass(frozen=True, kw_only=True)
class CompressedUrllibTransport:
    """One urllib exchange that asks for gzip, never raising, bounded end to end."""

    clock: Callable[[], float] = field(default=time.monotonic)

    def send(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout_seconds: float,
    ) -> FabroHttpResult:
        request = urllib.request.Request(  # noqa: S310 - url is a configured factory server.
            url,
            data=body,
            method=method,
            headers={**headers, "Accept-Encoding": _GZIP},
        )
        sent = attempt(
            action=lambda: self._exchange(request=request, timeout_seconds=timeout_seconds),
            exceptions=(urllib.error.URLError, OSError, ValueError, EOFError, zlib.error),
        )
        if isinstance(sent, AttemptFailure):
            return _failed(error=sent.error)
        return sent

    def _exchange(
        self, *, request: urllib.request.Request, timeout_seconds: float
    ) -> FabroHttpResult:
        deadline = self.clock() + timeout_seconds
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
            status = int(response.status)
            chunks: list[bytes] = []
            while chunk := response.read(_CHUNK_BYTES):
                if self.clock() > deadline:
                    message = f"the read exceeded its {timeout_seconds} s bound"
                    raise TimeoutError(message)
                chunks.append(chunk)
            raw = b"".join(chunks)
            if response.headers.get("Content-Encoding") == _GZIP:
                raw = gzip.decompress(raw)
        return FabroHttpResult(
            status=status,
            body=raw.decode("utf-8", errors="replace"),
            error=None,
            payload=None,
            succeeded=_HTTP_SUCCESS_FLOOR <= status < _HTTP_SUCCESS_CEILING,
        )


def _failed(*, error: Exception) -> FabroHttpResult:
    """The exchange a raised error describes: the server's refusal, or no answer at all."""
    described = f"{type(error).__name__}: {error}"
    status = int(error.code) if isinstance(error, urllib.error.HTTPError) else 0
    return FabroHttpResult(status=status, body="", error=described, payload=None, succeeded=False)
