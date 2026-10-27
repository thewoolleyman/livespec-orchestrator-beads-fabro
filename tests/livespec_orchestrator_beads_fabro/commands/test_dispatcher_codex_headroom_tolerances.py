"""Every shape a live journal and a live provider hand these two readers.

Sibling of `test_dispatcher_codex_headroom_journal.py`, which binds work-item
`bd-ib-4jdgcw`'s third assertion through the record a healthy evaluation writes.
This module owns the DEGRADED shapes neither a healthy record nor a healthy
response can produce, and both readers' clauses are explicit that they are
ordinary states rather than faults.

`SPECIFICATION/contracts.md` section "Provider spend containment", paragraph
"Admission filters Codex candidates by projected usage-window headroom", on the
read: "transport-failed, authentication-failed and timed-out reads ... MUST be
journaled as unobservable, never coerced to a numeric reading". And on the
history, through the Claude clause whose rules it applies: "The projection is
unavailable when no such baseline exists ... Each such case is a deliberate
fail-open of the projection only, and the floor still applies."

WHY A JOURNAL READER NEEDS THESE CASES AT ALL. The dispatch journal is
append-only and written by concurrent passes, so a truncated last line is an
ordinary state; it is also read by builds older and newer than the one that
wrote it, so a record carrying a key of the wrong type is a record from a
different build rather than a corrupt file. Every one of those must be PASSED
OVER, because raising would fail an admission evaluation over a figure no floor
depends on -- and every one of them must also be passed over WITHOUT becoming a
prior, because a value coerced out of the wrong type is subtracted from a real
reading to manufacture a drain rate nobody measured.

WHY THE WRONG-WINDOW CASE IS THE LOAD-BEARING ONE. A prior recorded for a
DIFFERENT window length is a perfectly well-formed reading of the same
credential, so a reader keyed on the credential alone finds it, measures the
weekly window's spend against the five-hour window's history, and reports the
difference as a rate. Nothing in the record looks wrong. It is asserted here
beside its positive control -- the same prior under the MATCHING length, which
must be found -- because an absence over a population that never contained a
match is no evidence at all.

EVERY TRANSPORT FAULT IS ITS OWN REASON. The four are distinct values rather
than one generic token because their remedies differ completely: an
authentication failure is a rotated or revoked credential, a transport failure
is the network or the provider, a timeout is neither, and an unreadable body is
a provider that answered with something this build cannot parse.
"""

from __future__ import annotations

import io
import json
from collections.abc import Callable
from email.message import Message
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _acp_session_headroom_records as headroom_records,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_codex_headroom_baseline as baseline,
)
from livespec_orchestrator_beads_fabro.commands import _dispatcher_codex_headroom_io as codex_io

_NOW = "2026-10-27T12:00:00Z"
_BASELINE_AT = "2026-10-27T11:00:00Z"
_FIVE_HOURS = 18000
_WEEK = 604800
_IDENTITY = "codex-identity"

# A reading the provider would serve: 1 percent used, the account allowed.
# Injected where a request must NOT happen, so that a request reaching the
# stub produces a clearly DIFFERENT answer from the one being asserted.
_HEALTHY_BODY = json.dumps(
    {
        "rate_limit": {
            "allowed": True,
            "limit_reached": False,
            "primary_window": {"used_percent": 1, "limit_window_seconds": _FIVE_HOURS},
        }
    }
).encode()


def _entry(**overrides: object) -> dict[str, object]:
    """One journaled Codex assessment entry, with any field overridden."""
    entry: dict[str, object] = {
        "credential_identity": _IDENTITY,
        "observed_at": _BASELINE_AT,
        "windows": [
            {
                "used_percent": 30.0,
                "limit_window_seconds": _FIVE_HOURS,
                "remaining_percent": 70.0,
            }
        ],
    }
    entry.update(overrides)
    return entry


def _write(*, path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _record_line(*, entries: object, stage: str | None = None) -> str:
    record: dict[str, object] = {
        "stage": headroom_records.SESSION_HEADROOM_STAGE if stage is None else stage,
        headroom_records.CODEX_ASSESSMENTS_KEY: entries,
    }
    return json.dumps(record)


def _baselines(*, path: Path, seconds: int = _FIVE_HOURS) -> dict[int, Any]:
    found: dict[int, Any] = baseline.codex_window_baselines(
        journal_path=path,
        credential_identity=_IDENTITY,
        window_seconds=(seconds,),
        now_iso=_NOW,
    )
    return found


def test_a_matching_prior_of_the_right_window_length_is_found(tmp_path: Path) -> None:
    """The positive control, without which every absence below is vacuous."""
    path = tmp_path / "journal.jsonl"
    _write(path=path, lines=[_record_line(entries=[_entry()])])

    found = _baselines(path=path)

    assert set(found) == {_FIVE_HOURS}
    assert found[_FIVE_HOURS].utilization_percent == 30.0
    assert found[_FIVE_HOURS].observed_at == _BASELINE_AT
    assert found[_FIVE_HOURS].elapsed_hours == pytest.approx(1.0)


def test_a_prior_recorded_for_another_window_length_is_never_a_baseline(
    tmp_path: Path,
) -> None:
    """The same credential, the same instant, a different window: no baseline."""
    path = tmp_path / "journal.jsonl"
    _write(path=path, lines=[_record_line(entries=[_entry()])])

    assert _baselines(path=path, seconds=_WEEK) == {}


@pytest.mark.parametrize(
    "lines",
    [
        pytest.param(["{ truncated"], id="unparseable-line"),
        pytest.param(["[1, 2]"], id="line-is-not-an-object"),
        pytest.param(
            [_record_line(entries=[_entry()], stage="acp-node-selection")], id="another-stage"
        ),
        pytest.param([_record_line(entries="not-a-list")], id="entries-not-a-list"),
        pytest.param([_record_line(entries=["not-a-mapping"])], id="entry-not-a-mapping"),
        pytest.param(
            [_record_line(entries=[_entry(credential_identity="someone-else")])],
            id="another-credential",
        ),
        pytest.param(
            [_record_line(entries=[_entry(observed_at=17)])], id="observed-at-not-a-string"
        ),
        pytest.param(
            [_record_line(entries=[_entry(windows="not-a-list")])], id="windows-not-a-list"
        ),
        pytest.param(
            [_record_line(entries=[_entry(windows=["not-a-mapping"])])],
            id="window-not-a-mapping",
        ),
        pytest.param(
            [
                _record_line(
                    entries=[_entry(windows=[{"used_percent": 30.0, "limit_window_seconds": True}])]
                )
            ],
            id="window-seconds-is-a-boolean",
        ),
        pytest.param(
            [
                _record_line(
                    entries=[
                        _entry(windows=[{"used_percent": 30.0, "limit_window_seconds": "18000"}])
                    ]
                )
            ],
            id="window-seconds-not-an-integer",
        ),
        pytest.param(
            [
                _record_line(
                    entries=[
                        _entry(
                            windows=[{"used_percent": True, "limit_window_seconds": _FIVE_HOURS}]
                        )
                    ]
                )
            ],
            id="used-percent-is-a-boolean",
        ),
        pytest.param(
            [
                _record_line(
                    entries=[
                        _entry(
                            windows=[{"used_percent": "high", "limit_window_seconds": _FIVE_HOURS}]
                        )
                    ]
                )
            ],
            id="used-percent-not-numeric",
        ),
        pytest.param([_record_line(entries=[_entry(windows=[])])], id="no-window-at-all"),
    ],
)
def test_every_degraded_journal_shape_is_passed_over_rather_than_coerced(
    tmp_path: Path, lines: list[str]
) -> None:
    """None of these is a prior, and none of them raises."""
    path = tmp_path / "journal.jsonl"
    _write(path=path, lines=lines)

    assert _baselines(path=path) == {}


def test_an_absent_or_unwritten_journal_holds_no_baseline(tmp_path: Path) -> None:
    """A fresh clone has no history, which the clause calls unavailable."""
    assert _baselines(path=tmp_path / "never-written.jsonl") == {}
    assert (
        baseline.codex_window_baselines(
            journal_path=None,
            credential_identity=_IDENTITY,
            window_seconds=(_FIVE_HOURS,),
            now_iso=_NOW,
        )
        == {}
    )


def _snapshot() -> str:
    return json.dumps({"tokens": {"access_token": "token", "account_id": "acct"}})


def _raising_urlopen(error: BaseException) -> Callable[..., Any]:
    def _urlopen(request: Request, *, timeout: float) -> Any:
        _ = (request, timeout)
        raise error

    return _urlopen


def _body_urlopen(*, body: bytes) -> Callable[..., Any]:
    def _urlopen(request: Request, *, timeout: float) -> MagicMock:
        _ = (request, timeout)
        response = MagicMock()
        response.read.return_value = body
        response.__enter__.return_value = response
        return response

    return _urlopen


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        pytest.param(TimeoutError("slow"), "timed-out", id="timed-out"),
        pytest.param(URLError("down"), "transport-failed", id="transport-failed"),
        pytest.param(OSError("socket"), "transport-failed", id="os-error"),
        pytest.param(
            HTTPError(
                url=codex_io.CODEX_USAGE_URL,
                code=500,
                msg="boom",
                hdrs=Message(),
                fp=io.BytesIO(b"{}"),
            ),
            "transport-failed",
            id="server-error",
        ),
        pytest.param(
            HTTPError(
                url=codex_io.CODEX_USAGE_URL,
                code=403,
                msg="forbidden",
                hdrs=Message(),
                fp=io.BytesIO(b"{}"),
            ),
            "authentication-failed",
            id="forbidden",
        ),
    ],
)
def test_every_transport_fault_is_its_own_unobservable_reason(
    monkeypatch: pytest.MonkeyPatch, error: BaseException, expected: str
) -> None:
    """A failure to measure is never coerced into a figure."""
    monkeypatch.setattr(codex_io, "urlopen", _raising_urlopen(error))

    reading = codex_io.read_projected_codex_usage(auth_json=_snapshot(), observed_at=_NOW)

    assert reading.unobservable == expected
    assert reading.windows == ()
    assert reading.governing_remaining_percent is None


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(b"not json", id="undecodable"),
        pytest.param(b"[1, 2]", id="not-an-object"),
        pytest.param(b"\xff\xfe", id="not-utf-8"),
    ],
)
def test_a_body_that_is_not_an_object_is_an_unreadable_response(
    monkeypatch: pytest.MonkeyPatch, body: bytes
) -> None:
    """The provider answered, and this build cannot read what it said."""
    monkeypatch.setattr(codex_io, "urlopen", _body_urlopen(body=body))

    reading = codex_io.read_projected_codex_usage(auth_json=_snapshot(), observed_at=_NOW)

    assert reading.unobservable == codex_io.UNREADABLE_RESPONSE_REASON


@pytest.mark.parametrize(
    "auth_json",
    [
        pytest.param("[1, 2]", id="snapshot-is-not-an-object"),
        pytest.param('{"tokens": "not-an-object"}', id="tokens-is-not-an-object"),
        pytest.param('{"tokens": {"access_token": 7, "account_id": "acct"}}', id="token-not-text"),
        pytest.param('{"tokens": {"access_token": "t", "account_id": ""}}', id="account-empty"),
        pytest.param('{"tokens": {"access_token": "", "account_id": "acct"}}', id="token-empty"),
    ],
)
def test_every_unusable_snapshot_shape_issues_no_request(
    monkeypatch: pytest.MonkeyPatch, auth_json: str
) -> None:
    """Nothing to authenticate with, so no round trip is spent on it.

    The injected provider answers a HEALTHY reading rather than recording a
    call count, and that is what makes the assertion able to fail for the right
    reason: a read that reached this stub would come back observable with 99
    points of headroom, so `absent-credential` is only reachable when no
    request was issued at all. A recording stub would instead need a body no
    passing case ever executes -- a fake that has stopped describing the seam.
    """
    monkeypatch.setattr(codex_io, "urlopen", _body_urlopen(body=_HEALTHY_BODY))

    reading = codex_io.read_projected_codex_usage(auth_json=auth_json, observed_at=_NOW)

    assert reading.unobservable == codex_io.ABSENT_CREDENTIAL_REASON
    assert reading.credential_identity == codex_io.ABSENT_CREDENTIAL_IDENTITY
    assert reading.governing_remaining_percent is None
