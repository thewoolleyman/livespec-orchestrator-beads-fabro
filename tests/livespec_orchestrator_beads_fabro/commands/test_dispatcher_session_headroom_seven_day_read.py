"""The seven-day allowance arrives on the SAME request as the five-hour one.

Binds the first sentence of the seven-day half of
`SPECIFICATION/contracts.md` section "Dispatcher admission, WIP cap, and
post-merge acceptance", paragraph "Admission filters candidates by projected
Claude session headroom": "From the same provider response it MUST also take
the seven-day utilization and the seven-day status where the provider reports
them." The governing scenario is `SPECIFICATION/scenarios.md` Scenario 231.

THE LOAD-BEARING ASSERTION IS THE REQUEST COUNT, not the figures. Both windows
are reported by one response's own headers, so a build that spent a SECOND
bounded request for the weekly half would return the identical reading and
satisfy every figure assertion here -- while doubling what admission costs the
provider on every evaluation, against a clause whose own words are "the same
provider response". Each case therefore reads the recorded call list.

THE REFUSED-RESPONSE CASE IS THE ONE THE CLAUSE EXISTS FOR. An account whose
weekly allowance is spent is exactly an account whose next request is REFUSED,
and this module's sibling already establishes that such a response's five-hour
header is graded rather than discarded. The weekly half has to survive the same
arm, or the reading that would skip the candidate is the one reading that never
carries a status.

THE SEVEN-DAY HEADER NAMES ARE SPELLED AS LITERALS and bound to the exported
constants by the first case, because this file's Red predates those constants
and a Red's test bytes are fixed across its Red-to-Green pair.

Everything is HERMETIC: the provider is reached through an injected `urlopen`,
and no credential value leaves this file.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from email.message import Message
from typing import Any, cast
from unittest.mock import MagicMock
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_session_headroom_io as headroom_io,
)

_NOW = "2026-10-22T02:00:00Z"
_TOKEN = "projected-oauth-token"

# The measured five-hour header this module's sibling pins, and the two
# seven-day headers that are its exact siblings in the provider's unified
# rate-limit family.
_FIVE_HOUR = "anthropic-ratelimit-unified-5h-utilization"
_SEVEN_DAY_UTILIZATION = "anthropic-ratelimit-unified-7d-utilization"
_SEVEN_DAY_STATUS = "anthropic-ratelimit-unified-7d-status"

_REJECTED = "rejected"


def _headers(**values: str) -> Message:
    message = Message()
    for name, value in values.items():
        message[name.replace("_", "-")] = value
    return message


def _spent_weekly_headers() -> Message:
    """One response from an account with five-hour room and no weekly room."""
    return _headers(
        **{
            _FIVE_HOUR: "0.10",
            _SEVEN_DAY_UTILIZATION: "1.0",
            _SEVEN_DAY_STATUS: _REJECTED,
        }
    )


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


def _refusing_urlopen(
    calls: list[tuple[Request, float]], *, status: int, headers: Message
) -> Callable[..., Any]:
    def _urlopen(request: Request, *, timeout: float) -> Any:
        calls.append((request, timeout))
        raise HTTPError(
            url=headroom_io.CLAUDE_SESSION_HEADROOM_URL,
            code=status,
            msg="refused",
            hdrs=cast("Message", headers),
            fp=io.BytesIO(b"{}"),
        )

    return _urlopen


def _seven_day(reading: object) -> Any:
    """The weekly half of one reading, or `None` where no build reports one."""
    return getattr(reading, "seven_day", None)


def test_one_request_carries_both_the_five_hour_and_the_seven_day_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both windows, one bounded request, on the credential the dispatch projects."""
    calls: list[tuple[Request, float]] = []
    monkeypatch.setattr(
        headroom_io, "urlopen", _recording_urlopen(calls, headers=_spent_weekly_headers())
    )

    reading = headroom_io.read_projected_session_headroom(token=_TOKEN, observed_at=_NOW)

    weekly = _seven_day(reading)
    assert getattr(weekly, "status", None) == _REJECTED
    assert getattr(weekly, "utilization_percent", None) == 100.0
    assert getattr(weekly, "unobservable", None) is None
    # The five-hour half of the SAME response is unchanged, and the weekly half
    # cost no second round trip.
    assert reading.utilization_percent == 10.0
    assert reading.remaining_percent == 90.0
    assert len(calls) == 1
    request, timeout = calls[0]
    assert request.get_header("Authorization") == f"Bearer {_TOKEN}"
    assert timeout == headroom_io.SESSION_HEADROOM_READ_TIMEOUT_SECONDS
    # The names the read asked for are the ones this module pins.
    assert getattr(headroom_io, "SEVEN_DAY_UTILIZATION_HEADER", None) == _SEVEN_DAY_UTILIZATION
    assert getattr(headroom_io, "SEVEN_DAY_STATUS_HEADER", None) == _SEVEN_DAY_STATUS


def test_a_response_refused_at_the_weekly_limit_still_grades_the_seven_day_half(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 429 is what a spent account answers, and it carries the status."""
    calls: list[tuple[Request, float]] = []
    monkeypatch.setattr(
        headroom_io,
        "urlopen",
        _refusing_urlopen(calls, status=429, headers=_spent_weekly_headers()),
    )

    reading = headroom_io.read_projected_session_headroom(token=_TOKEN, observed_at=_NOW)

    assert getattr(_seven_day(reading), "status", None) == _REJECTED
    assert reading.observable is True
    assert len(calls) == 1


def test_a_response_carrying_no_seven_day_headers_is_an_explicit_unobservable_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An absent weekly reading is named as absent, never numbered."""
    monkeypatch.setattr(
        headroom_io,
        "urlopen",
        _recording_urlopen([], headers=_headers(**{_FIVE_HOUR: "0.10"})),
    )

    reading = headroom_io.read_projected_session_headroom(token=_TOKEN, observed_at=_NOW)

    weekly = _seven_day(reading)
    assert getattr(weekly, "unobservable", None) is not None
    assert getattr(weekly, "utilization_percent", None) is None
    assert getattr(weekly, "status", None) is None
    # The five-hour half still read, so the weekly absence is the provider's
    # silence rather than a response nobody could read.
    assert reading.utilization_percent == 10.0


def test_a_transport_fault_leaves_the_seven_day_half_unobservable_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no response at all there is no weekly reading to take from one."""

    def _urlopen(request: Request, *, timeout: float) -> Any:
        _ = (request, timeout)
        raise URLError("down")

    monkeypatch.setattr(headroom_io, "urlopen", _urlopen)

    reading = headroom_io.read_projected_session_headroom(token=_TOKEN, observed_at=_NOW)

    assert reading.unobservable == headroom_io.TRANSPORT_FAILED_REASON
    assert getattr(_seven_day(reading), "unobservable", None) is not None
