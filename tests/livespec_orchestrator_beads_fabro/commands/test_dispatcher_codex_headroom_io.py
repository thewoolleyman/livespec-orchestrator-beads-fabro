"""The Codex usage READ: which request it spends and how it grades the answer.

Binds "For each distinct projected Codex credential per admission evaluation, the
Dispatcher MUST issue exactly one bounded usage read to the provider's account
usage endpoint ... authenticated by that snapshot's access token and account
identifier" in `SPECIFICATION/contracts.md`. The read has a finite timeout, runs
no model turn, and every transport, authentication and timeout failure is an
explicit unobservable result, never a number.

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
from livespec_orchestrator_beads_fabro.commands import _dispatcher_codex_headroom_io as codex_io

_NOW = "2026-10-28T06:00:00Z"
_TOKEN = "projected-access-token"
_ACCOUNT = "account-0123"
_REFRESHED = "a-refreshed-access-token"


def _auth(*, token: object = _TOKEN, account: object = _ACCOUNT) -> str:
    return json.dumps({"tokens": {"access_token": token, "account_id": account}})


def _body(*, used: float = 25.0) -> bytes:
    return json.dumps(
        {
            "rate_limit": {
                "allowed": True,
                "limit_reached": False,
                "primary_window": {"used_percent": used, "limit_window_seconds": 18000},
                "secondary_window": None,
            },
            "credits": {"balance": "900"},
        }
    ).encode()


def _response(*, body: bytes) -> MagicMock:
    response = MagicMock()
    response.read.return_value = body
    response.__enter__.return_value = response
    return response


def _recording(calls: list[tuple[Request, float]], *, body: bytes) -> Callable[..., Any]:
    def _urlopen(request: Request, *, timeout: float) -> MagicMock:
        calls.append((request, timeout))
        return _response(body=body)

    return _urlopen


def _raising(error: BaseException) -> Callable[..., Any]:
    def _urlopen(request: Request, *, timeout: float) -> Any:
        _ = (request, timeout)
        raise error

    return _urlopen


def _http_error(*, status: int) -> HTTPError:
    return HTTPError(
        url=codex_io.CODEX_USAGE_URL,
        code=status,
        msg="refused",
        hdrs=cast("Message", Message()),
        fp=io.BytesIO(b"provider words that must never be journaled"),
    )


def test_the_read_spends_one_bounded_get_with_the_token_and_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[Request, float]] = []
    monkeypatch.setattr(codex_io, "urlopen", _recording(calls, body=_body(used=25.0)))

    reading = codex_io.read_projected_codex_headroom(auth_json=_auth(), observed_at=_NOW)

    assert reading.observable is True
    assert reading.windows[0].remaining_percent == 75.0
    assert len(calls) == 1
    request, timeout = calls[0]
    assert request.full_url == "https://chatgpt.com/backend-api/wham/usage"
    assert request.get_method() == "GET"
    assert request.data is None
    assert request.get_header("Authorization") == f"Bearer {_TOKEN}"
    assert request.get_header("Chatgpt-account-id") == _ACCOUNT
    assert timeout == codex_io.CODEX_HEADROOM_READ_TIMEOUT_SECONDS
    assert 0 < timeout < float("inf")


def test_the_identity_is_a_one_way_digest_of_the_account_and_not_the_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(codex_io, "urlopen", _recording([], body=_body()))

    first = codex_io.read_projected_codex_headroom(auth_json=_auth(), observed_at=_NOW)
    rotated = codex_io.read_projected_codex_headroom(
        auth_json=_auth(token=_REFRESHED), observed_at=_NOW
    )
    other = codex_io.read_projected_codex_headroom(
        auth_json=_auth(account="another-account"), observed_at=_NOW
    )

    assert first.credential_identity == rotated.credential_identity
    assert first.credential_identity != other.credential_identity
    for identity in (first.credential_identity, other.credential_identity):
        assert _TOKEN not in identity
        assert _ACCOUNT not in identity
        assert len(identity) == 16


@pytest.mark.parametrize(
    "auth_json",
    [
        None,
        "not json",
        "[]",
        json.dumps({}),
        json.dumps({"tokens": "nope"}),
        _auth(token=""),
        _auth(account=""),
        _auth(token=None),
        _auth(account=5),
    ],
)
def test_an_absent_or_unusable_credential_issues_no_request(
    monkeypatch: pytest.MonkeyPatch, auth_json: str | None
) -> None:
    calls: list[tuple[Request, float]] = []
    monkeypatch.setattr(codex_io, "urlopen", _recording(calls, body=_body()))

    reading = codex_io.read_projected_codex_headroom(auth_json=auth_json, observed_at=_NOW)

    assert calls == []
    assert reading.observable is False
    assert reading.unobservable == "absent-credential"


def test_the_identity_of_an_absent_account_is_the_literal_absent() -> None:
    assert codex_io.codex_credential_identity(account_id=None) == "absent"
    assert codex_io.codex_credential_identity(account_id="") == "absent"


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (_http_error(status=401), "authentication-failed"),
        (_http_error(status=403), "authentication-failed"),
        (_http_error(status=500), "transport-failed"),
        (_http_error(status=429), "transport-failed"),
        (TimeoutError(), "timed-out"),
        (URLError("unreachable"), "transport-failed"),
        (ConnectionResetError(), "transport-failed"),
    ],
)
def test_every_failed_read_is_an_explicit_unobservable_reason(
    monkeypatch: pytest.MonkeyPatch, error: BaseException, reason: str
) -> None:
    monkeypatch.setattr(codex_io, "urlopen", _raising(error))

    reading = codex_io.read_projected_codex_headroom(auth_json=_auth(), observed_at=_NOW)

    assert reading.observable is False
    assert reading.unobservable == reason
    assert reading.windows == ()
    assert "provider words" not in repr(reading)


@pytest.mark.parametrize("body", [b"\xff\xfe not utf-8", b"not json", b"[]", b'{"rate_limit": 3}'])
def test_an_undecodable_or_malformed_body_is_unobservable(
    monkeypatch: pytest.MonkeyPatch, body: bytes
) -> None:
    monkeypatch.setattr(codex_io, "urlopen", _recording([], body=body))

    reading = codex_io.read_projected_codex_headroom(auth_json=_auth(), observed_at=_NOW)

    assert reading.observable is False
    assert reading.unobservable == "unreadable-response"
