"""The admission session-headroom READ: which request it spends and how it grades.

Binds the "Admission filters candidates by projected Claude session headroom"
paragraph of `SPECIFICATION/contracts.md` section "Dispatcher admission, WIP
cap, and post-merge acceptance" -- "It MUST read the provider's five-hour
session utilization using the exact credential snapshot that the dispatch would
project" -- to the request that can actually answer for that credential.

WHY THE MESSAGES API AND NOT THE OAUTH USAGE ENDPOINT, which is the regression
this file exists to keep dead (`bd-ib-nzp5ln`). Measured 2026-10-15 on this
host: `GET /api/oauth/usage` with the projected subscription token returned 403
`permission_error`, "OAuth token does not meet scope requirement user:profile",
then 429 on every retry, so EVERY admission evaluation graded the reading
unobservable and skipped every covered candidate. The same token on a one-token
`POST /v1/messages` returned 200 carrying
`anthropic-ratelimit-unified-5h-utilization: 0.0`. The header is a FRACTION of
the allowance, so the read multiplies it by 100 before the shared grader sees
it; forgetting that turns 95% used into a reading of 0.95%.

A 403 permission refusal IS still covered below, deliberately: a later scope
change on the Messages API must surface as `authentication-failed`, never as a
silent numeric reading.

Everything is HERMETIC: the provider is reached through an injected `urlopen`,
and no credential value leaves this file.
"""

from __future__ import annotations

import io
import json
from collections.abc import Callable
from email.message import Message
from typing import Any, cast
from unittest.mock import MagicMock
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest
from livespec_orchestrator_beads_fabro.commands import _acp_session_headroom as headroom
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_session_headroom_io as headroom_io,
)

_NOW = "2026-10-15T02:00:00Z"
_TOKEN = "projected-oauth-token"
_OTHER_TOKEN = "a-different-projected-token"
_HEADER = "anthropic-ratelimit-unified-5h-utilization"


def _headers(**values: str) -> Message:
    message = Message()
    for name, value in values.items():
        message[name] = value
    return message


def _response(*, headers: Message) -> MagicMock:
    response = MagicMock()
    response.status = 200
    response.headers = headers
    response.read.return_value = b'{"type":"message"}'
    response.__enter__.return_value = response
    return response


def _recording_urlopen(
    calls: list[tuple[Request, float]], *, headers: Message
) -> Callable[..., Any]:
    def _urlopen(request: Request, *, timeout: float) -> MagicMock:
        calls.append((request, timeout))
        return _response(headers=headers)

    return _urlopen


def _refusing_urlopen(*, status: int, headers: Message | None, body: bytes) -> Callable[..., Any]:
    def _urlopen(request: Request, *, timeout: float) -> Any:
        _ = (request, timeout)
        raise HTTPError(
            url=headroom_io.CLAUDE_SESSION_HEADROOM_URL,
            code=status,
            msg="refused",
            hdrs=cast("Message", headers),
            fp=io.BytesIO(body),
        )

    return _urlopen


def test_the_read_spends_one_bounded_messages_request_on_the_projected_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[Request, float]] = []
    monkeypatch.setattr(
        headroom_io, "urlopen", _recording_urlopen(calls, headers=_headers(**{_HEADER: "0.75"}))
    )

    reading = headroom_io.read_projected_session_headroom(token=_TOKEN, observed_at=_NOW)

    assert reading.observable is True
    assert reading.utilization_percent == 75.0
    assert reading.remaining_percent == 25.0
    assert len(calls) == 1
    request, timeout = calls[0]
    assert request.full_url == "https://api.anthropic.com/v1/messages"
    assert request.get_method() == "POST"
    assert request.get_header("Authorization") == f"Bearer {_TOKEN}"
    assert timeout == headroom_io.SESSION_HEADROOM_READ_TIMEOUT_SECONDS
    assert isinstance(request.data, bytes)
    payload = json.loads(request.data)
    assert payload["max_tokens"] == 1


@pytest.mark.parametrize(("fraction", "percent"), [("0.0", 0.0), ("1.0", 100.0), ("0.95", 95.0)])
def test_the_fractional_header_is_graded_as_a_percentage(
    monkeypatch: pytest.MonkeyPatch, fraction: str, percent: float
) -> None:
    monkeypatch.setattr(
        headroom_io, "urlopen", _recording_urlopen([], headers=_headers(**{_HEADER: fraction}))
    )

    reading = headroom_io.read_projected_session_headroom(token=_TOKEN, observed_at=_NOW)

    assert reading.utilization_percent == percent


@pytest.mark.parametrize("headers", [_headers(), _headers(**{_HEADER: "soon"})])
def test_a_response_without_a_parseable_header_is_unobservable(
    monkeypatch: pytest.MonkeyPatch, headers: Message
) -> None:
    monkeypatch.setattr(headroom_io, "urlopen", _recording_urlopen([], headers=headers))

    reading = headroom_io.read_projected_session_headroom(token=_TOKEN, observed_at=_NOW)

    assert reading.observable is False
    assert reading.unobservable == headroom.UNREADABLE_UTILIZATION
    assert reading.utilization_percent is None


@pytest.mark.parametrize("status", [401, 403])
def test_an_authentication_refusal_without_the_header_is_authentication_failed(
    monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    body = b'{"type":"error","error":{"type":"permission_error","message":"scope"}}'
    monkeypatch.setattr(
        headroom_io, "urlopen", _refusing_urlopen(status=status, headers=_headers(), body=body)
    )

    reading = headroom_io.read_projected_session_headroom(token=_TOKEN, observed_at=_NOW)

    assert reading.observable is False
    assert reading.unobservable == headroom_io.AUTHENTICATION_FAILED_REASON


def test_a_refusal_carrying_no_headers_at_all_is_graded_by_its_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        headroom_io, "urlopen", _refusing_urlopen(status=403, headers=None, body=b"{}")
    )

    reading = headroom_io.read_projected_session_headroom(token=_TOKEN, observed_at=_NOW)

    assert reading.unobservable == headroom_io.AUTHENTICATION_FAILED_REASON


def test_a_rate_limited_response_carrying_the_header_is_graded_from_the_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 429 at the session limit still says how much of the window is used."""
    monkeypatch.setattr(
        headroom_io,
        "urlopen",
        _refusing_urlopen(status=429, headers=_headers(**{_HEADER: "1.0"}), body=b"{}"),
    )

    reading = headroom_io.read_projected_session_headroom(token=_TOKEN, observed_at=_NOW)

    assert reading.observable is True
    assert reading.utilization_percent == 100.0
    assert reading.remaining_percent == 0.0


def test_a_server_refusal_without_the_header_is_transport_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        headroom_io, "urlopen", _refusing_urlopen(status=500, headers=_headers(), body=b"{}")
    )

    reading = headroom_io.read_projected_session_headroom(token=_TOKEN, observed_at=_NOW)

    assert reading.unobservable == headroom_io.TRANSPORT_FAILED_REASON


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (TimeoutError("slow"), "timed-out"),
        (URLError("down"), "transport-failed"),
        (OSError("reset"), "transport-failed"),
    ],
)
def test_a_transport_fault_is_its_own_unobservable_result(
    monkeypatch: pytest.MonkeyPatch, error: Exception, reason: str
) -> None:
    def fake_urlopen(request: Request, *, timeout: float) -> Any:
        _ = (request, timeout)
        raise error

    monkeypatch.setattr(headroom_io, "urlopen", fake_urlopen)

    reading = headroom_io.read_projected_session_headroom(token=_TOKEN, observed_at=_NOW)

    assert reading.observable is False
    assert reading.unobservable == reason


def test_an_absent_projected_credential_is_unobservable_without_a_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[Request, float]] = []
    monkeypatch.setattr(
        headroom_io, "urlopen", _recording_urlopen(calls, headers=_headers(**{_HEADER: "0.1"}))
    )

    reading = headroom_io.read_projected_session_headroom(token=None, observed_at=_NOW)

    assert calls == []
    assert reading.unobservable == headroom_io.ABSENT_CREDENTIAL_REASON
    assert reading.credential_identity == headroom_io.ABSENT_CREDENTIAL_IDENTITY


def test_the_credential_identity_is_opaque_stable_and_credential_specific() -> None:
    first = headroom_io.projected_credential_identity(token=_TOKEN)

    assert first == headroom_io.projected_credential_identity(token=_TOKEN)
    assert first != headroom_io.projected_credential_identity(token=_OTHER_TOKEN)
    assert _TOKEN not in first
