"""HTTP transport for the Fabro server routes the pinned CLI cannot reach.

The pinned `fabro` CLI answers a run's pending interview only interactively
(`fabro attach`) and exposes no cancel verb at all, so the two routes the
run reconciler needs are reached over the server's own HTTP API instead.

Every route is mounted under `/api/v1`. The bare `/runs/...` form the server
does NOT serve answers 404, which this port's own fallback discipline then
reads as "this route did not work" — so the prefix being wrong is invisible
at the call site and costs the destructive last-resort route instead.

Authentication resolves through `_fabro_port_auth.resolve_bearer_token`:
the `FABRO_DEV_TOKEN__<factory>` environment variable that
`_config.resolve_fabro_factory` already folded into the target, else the
`~/.fabro/auth.json` entry `fabro auth login` wrote for the configured
server url. A target that resolves neither sends no authorization header and
is refused with 401 on every route, which is why the reconciler journals
that case by name rather than letting it read as a server that declined.

A target with NO server url yields a failed result rather than a request
against a guessed host. Building a bare target is the mis-aimed instrument
this reconciler exists to avoid, and the failure is returned as data so the
caller journals it rather than proceeding on a request nobody can name.

The request and response SHAPES here were recorded from a live `hp` server
on 2026-08-30 against a parked run, not inferred from handler names: a
questions listing is `{"data": [...], "meta": {...}}`, and an answer is the
typed `SubmitAnswerRequest` — `{"kind": "selected", "option_key": "A"}`. The
legacy `{"answer": ...}` / `{"value": ...}` bodies are rejected with 422.
Any non-2xx or unparsable answer is still treated as "this route did not
work" so the caller falls through to the next one.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field, replace
from typing import Protocol

from livespec_orchestrator_beads_fabro.commands._fabro_port_auth import resolve_bearer_token
from livespec_orchestrator_beads_fabro.commands._fabro_port_types import FabroTarget
from livespec_orchestrator_beads_fabro.effects import (
    AttemptFailure,
    JsonParseFailure,
    attempt,
    parse_json,
)

__all__: list[str] = [
    "SYSTEM_INFO_PATH",
    "FabroHttpPort",
    "FabroHttpResult",
    "FabroHttpTransport",
    "UrllibFabroHttpTransport",
    "fabro_http_request",
]

_HTTP_SUCCESS_FLOOR = 200
_HTTP_SUCCESS_CEILING = 300
# The server mounts the whole run API under this prefix; the bare `/runs/...`
# form 404s.
_API_PREFIX = "/api/v1"
# The build-identity route the ACP capability gate reads. PUBLIC because that
# gate's test asserts which url was requested, and a private constant would
# leave it asserting a literal that could drift from the one sent.
SYSTEM_INFO_PATH = f"{_API_PREFIX}/system/info"
# The `SubmitAnswerRequest` variant that picks one option of a multiple-choice
# question by its `key`.
_ANSWER_KIND_SELECTED = "selected"
_NO_SERVER_URL_ERROR = (
    "the factory target carries no server url; refusing to send a Fabro HTTP "
    "request against an unnamed host"
)


@dataclass(frozen=True, kw_only=True)
class FabroHttpResult:
    """One Fabro HTTP exchange, carried as data rather than as an exception.

    `status` is 0 when no response was received at all, which is why
    `succeeded` is a recorded field and not a comparison a caller repeats.
    """

    status: int
    body: str
    error: str | None
    payload: object | None
    succeeded: bool


class FabroHttpTransport(Protocol):
    """The single seam a Fabro HTTP request is sent through."""

    def send(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout_seconds: float,
    ) -> FabroHttpResult:
        """Send one request, returning the exchange (never raising)."""
        ...


@dataclass(frozen=True, kw_only=True)
class UrllibFabroHttpTransport:
    """Production transport: one stdlib urllib exchange, never raising.

    A non-2xx status arrives here as an `HTTPError`, which is a `URLError`
    subclass, so it lands on the same failure track as a network fault. That
    is the right collapse for this consumer: both mean "this route did not
    work", and the caller's remedy for either is the next route.
    """

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
            headers=headers,
        )
        sent = attempt(
            action=lambda: _exchange(request=request, timeout_seconds=timeout_seconds),
            exceptions=(urllib.error.URLError, OSError, ValueError),
        )
        if isinstance(sent, AttemptFailure):
            return FabroHttpResult(
                status=0,
                body="",
                error=f"{type(sent.error).__name__}: {sent.error}",
                payload=None,
                succeeded=False,
            )
        return sent


@dataclass(frozen=True, kw_only=True)
class FabroHttpPort:
    """One factory's SERVER-API face, beside the CLI port rather than in it.

    `FabroPort.server_api()` builds this from its OWN target, so a
    server-API call can only ever reach the factory its CLI port was
    constructed for. The verbs live here because they are a different
    transport with a different failure vocabulary — a status code and a
    body, not an exit code and two streams — and folding them into the CLI
    port mixed two concerns in one file.
    """

    target: FabroTarget
    transport: FabroHttpTransport = field(default_factory=UrllibFabroHttpTransport)

    def bearer_token(self) -> str | None:
        """This factory's resolved bearer credential, or `None` if it has none.

        Exposed because "no credential resolved" is a fact the CALLER has to
        record: from inside a request it is indistinguishable from a server
        that considered the act and refused it.
        """
        return resolve_bearer_token(target=self.target)

    def questions(self, *, run_id: str, timeout_seconds: float) -> FabroHttpResult:
        """List one run's pending interview questions."""
        return self._verb(
            method="GET",
            path=f"{_API_PREFIX}/runs/{run_id}/questions",
            payload=None,
            timeout_seconds=timeout_seconds,
        )

    def answer_question(
        self,
        *,
        run_id: str,
        question_id: str,
        option_key: str,
        timeout_seconds: float,
    ) -> FabroHttpResult:
        """Answer one pending question by selecting one of its option keys."""
        return self._verb(
            method="POST",
            path=f"{_API_PREFIX}/runs/{run_id}/questions/{question_id}/answer",
            payload={"kind": _ANSWER_KIND_SELECTED, "option_key": option_key},
            timeout_seconds=timeout_seconds,
        )

    def system_info(self, *, timeout_seconds: float) -> FabroHttpResult:
        """Read this factory's build identity, including its advertised capabilities.

        Sits beside the three run verbs because it is the same transport
        against the same target, and because the capability gate it serves
        FAILS CLOSED: a reader that built its own target could be pointed at a
        factory the dispatch is not using, and would then refuse or admit a
        chain on another server's advertisement.
        """
        return self._verb(
            method="GET",
            path=SYSTEM_INFO_PATH,
            payload=None,
            timeout_seconds=timeout_seconds,
        )

    def cancel(self, *, run_id: str, timeout_seconds: float) -> FabroHttpResult:
        """Cancel one run through the server's lifecycle route."""
        return self._verb(
            method="POST",
            path=f"{_API_PREFIX}/runs/{run_id}/cancel",
            payload=None,
            timeout_seconds=timeout_seconds,
        )

    def _verb(
        self,
        *,
        method: str,
        path: str,
        payload: dict[str, str] | None,
        timeout_seconds: float,
    ) -> FabroHttpResult:
        return fabro_http_request(
            target=self.target,
            transport=self.transport,
            method=method,
            path=path,
            payload=payload,
            timeout_seconds=timeout_seconds,
        )


def fabro_http_request(
    *,
    target: FabroTarget,
    transport: FabroHttpTransport,
    method: str,
    path: str,
    payload: dict[str, str] | None,
    timeout_seconds: float,
) -> FabroHttpResult:
    """Send one authenticated request to a named factory's Fabro server."""
    if target.server_url is None:
        return FabroHttpResult(
            status=0,
            body="",
            error=_NO_SERVER_URL_ERROR,
            payload=None,
            succeeded=False,
        )
    body = None if payload is None else json.dumps(payload, sort_keys=True).encode("utf-8")
    result = transport.send(
        method=method,
        url=f"{target.server_url.rstrip('/')}{path}",
        headers=_headers(target=target, carries_body=body is not None),
        body=body,
        timeout_seconds=timeout_seconds,
    )
    parsed = parse_json(text=result.body)
    return replace(result, payload=None if isinstance(parsed, JsonParseFailure) else parsed)


def _headers(*, target: FabroTarget, carries_body: bool) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if carries_body:
        headers["Content-Type"] = "application/json"
    token = resolve_bearer_token(target=target)
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _exchange(*, request: urllib.request.Request, timeout_seconds: float) -> FabroHttpResult:
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
        status = int(response.status)
        text = response.read().decode("utf-8", errors="replace")
    return FabroHttpResult(
        status=status,
        body=text,
        error=None,
        payload=None,
        succeeded=_HTTP_SUCCESS_FLOOR <= status < _HTTP_SUCCESS_CEILING,
    )
