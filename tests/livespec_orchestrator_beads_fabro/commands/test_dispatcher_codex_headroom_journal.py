"""Every Codex assessment is journaled beside the Claude ones, with its projection.

Binds the third assertion of work-item `bd-ib-4jdgcw`'s Definition of Done, and
through it `SPECIFICATION/contracts.md` section "Provider spend containment",
paragraph "Admission filters Codex candidates by projected usage-window
headroom": "For each distinct projected Codex credential per admission
evaluation, the Dispatcher MUST issue exactly one bounded usage read to the
provider's account usage endpoint, `https://chatgpt.com/backend-api/wham/usage`,
authenticated by that snapshot's access token and account identifier"; "The read
MUST have a finite implementation-defined timeout and MUST NOT run a model turn
or spend any model allowance"; "For each affected work-item and assessed Codex
credential, the Dispatcher MUST journal ... the opaque non-secret credential
identity, `rate_limit.allowed` and `rate_limit.limit_reached`, each window's
`used_percent`, `limit_window_seconds` and remaining headroom, or an explicit
unobservable result, the local observation time, and exactly one projection
result per window in the Claude clause's form"; and "The journal MUST NOT contain
credential values, the account email, or raw provider responses."

HERMETIC. The provider is reached through an injected `urlopen` and the
credential arrives as `auth.json` TEXT, so no case here touches a network, a
host credential file or a real account.

THE NO-CREDENTIAL-VALUE CLAIM IS ASSERTED OVER THE RENDERED RECORD, not over
this module's care. The record is serialized and searched for the access token,
the account identifier and the account email, because a field added later that
happened to carry one of them would satisfy every key-by-key assertion while
putting a secret in the one file an operator greps.

THE PER-WINDOW BASELINE RULE IS ASSERTED WITH TWO WINDOW LENGTHS AND ONE
BASELINE. "applied per opaque credential identity AND per window length, so a
reading of one window is never a baseline for another" is unobservable from a
single-window fixture: a gate that keyed its history on the credential alone
answers correctly there and silently measures the weekly window's drain against
the five-hour window's history. So the journal seeded below carries a prior for
ONE of the two lengths, and the two projections must come back DIFFERENT -- one
projected, one unavailable naming the absent baseline.

THE CODEX ROW SITS BESIDE THE CLAUDE ROW IN ONE RECORD, which is the assertion's
own word "beside". One record per work-item per evaluation carries both, so a
reader sees every provider this evaluation assessed at one instant without a
join -- and the Codex-only case is asserted too, because a writer whose guard
tested the Claude list alone would drop every reading of a repository routed
wholly to Codex.
"""

from __future__ import annotations

import io
import json
from collections.abc import Callable
from email.message import Message
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
from urllib.error import HTTPError
from urllib.request import Request

import pytest
from livespec_orchestrator_beads_fabro.commands import _acp_candidate_preflight as preflight
from livespec_orchestrator_beads_fabro.commands import (
    _acp_session_headroom_records as headroom_records,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_session_headroom_gate as headroom_gate,
)
from livespec_orchestrator_beads_fabro.commands._acp_codex_headroom import CodexUsageReading
from livespec_orchestrator_beads_fabro.commands._acp_preflight_verdict import AcpPreflightVerdict
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom import (
    session_headroom_reading,
)

_COMMANDS = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)

_NOW = "2026-10-27T12:00:00Z"
_BASELINE_AT = "2026-10-27T11:00:00Z"
_FIVE_HOURS = 18000
_WEEK = 604800
_TOKEN = "codex-access-token-value"
_ACCOUNT = "acct-01JXYZ"
_EMAIL = "operator@example.com"
_AUTH_JSON = json.dumps(
    {
        "tokens": {"access_token": _TOKEN, "account_id": _ACCOUNT},
        "last_refresh": "2026-10-27T10:00:00Z",
        "email": _EMAIL,
    }
)


def _module(name: str) -> Any:
    import importlib

    return importlib.import_module(f"livespec_orchestrator_beads_fabro.commands.{name}")


def _usage_payload(
    *,
    allowed: bool = True,
    limit_reached: bool = False,
    primary_used: float = 60.0,
    secondary_used: float | None = None,
) -> dict[str, object]:
    rate_limit: dict[str, object] = {
        "allowed": allowed,
        "limit_reached": limit_reached,
        "primary_window": {
            "used_percent": primary_used,
            "limit_window_seconds": _FIVE_HOURS,
            "resets_in_seconds": 900,
        },
    }
    if secondary_used is not None:
        rate_limit["secondary_window"] = {
            "used_percent": secondary_used,
            "limit_window_seconds": _WEEK,
        }
    return {"rate_limit": rate_limit, "balance": {"credits": 500}, "email": _EMAIL}


def _response(*, body: bytes) -> MagicMock:
    response = MagicMock()
    response.status = 200
    response.headers = Message()
    response.read.return_value = body
    response.__enter__.return_value = response
    return response


def _recording_urlopen(
    calls: list[tuple[Request, float]], *, payload: dict[str, object]
) -> Callable[..., Any]:
    def _urlopen(request: Request, *, timeout: float) -> MagicMock:
        calls.append((request, timeout))
        return _response(body=json.dumps(payload).encode())

    return _urlopen


def _refusing_urlopen(*, status: int) -> Callable[..., Any]:
    def _urlopen(request: Request, *, timeout: float) -> Any:
        _ = (request, timeout)
        raise HTTPError(
            url=_module("_dispatcher_codex_headroom_io").CODEX_USAGE_URL,
            code=status,
            msg="refused",
            hdrs=Message(),
            fp=io.BytesIO(b"{}"),
        )

    return _urlopen


def _journal(*, path: Path, codex_entries: list[dict[str, object]]) -> None:
    """Seed the dispatch journal with one earlier assessment record."""
    record = {
        "at": _BASELINE_AT,
        "stage": headroom_records.SESSION_HEADROOM_STAGE,
        "work_item_id": "bd-ib-earlier",
        "session_headroom_floor_percent": 20,
        "assessments": [],
        headroom_records.CODEX_ASSESSMENTS_KEY: codex_entries,
        "node_selections": {},
    }
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")


def _prior(*, used: float, seconds: int) -> dict[str, object]:
    """One earlier Codex assessment entry, in the shape the record renders."""
    return {
        "credential_identity": _identity(),
        "observed_at": _BASELINE_AT,
        "allowed": True,
        "limit_reached": False,
        "unobservable": None,
        "windows": [
            {
                "used_percent": used,
                "limit_window_seconds": seconds,
                "remaining_percent": 100.0 - used,
            }
        ],
        "projections": [],
        "unverified_provider_reset_claim": None,
    }


def _identity() -> str:
    io_module = _module("_dispatcher_codex_headroom_io")
    identity: str = io_module.projected_codex_credential_identity(access_token=_TOKEN)
    return identity


class _Journal:
    """A journal writer that records what the gate appended, in order."""

    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def test_the_codex_gate_and_its_read_are_shipped_modules() -> None:
    """The bounded read, the per-window baseline and the policy are modules."""
    assert (_COMMANDS / "_dispatcher_codex_headroom_io.py").is_file()
    assert (_COMMANDS / "_dispatcher_codex_headroom_baseline.py").is_file()
    assert (_COMMANDS / "_dispatcher_codex_headroom_gate.py").is_file()


def test_the_read_spends_one_bounded_usage_request_on_the_projected_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One request, to the ratified endpoint, authenticated by the snapshot."""
    io_module = _module("_dispatcher_codex_headroom_io")
    calls: list[tuple[Request, float]] = []
    monkeypatch.setattr(io_module, "urlopen", _recording_urlopen(calls, payload=_usage_payload()))

    reading = io_module.read_projected_codex_usage(auth_json=_AUTH_JSON, observed_at=_NOW)

    assert len(calls) == 1
    request, timeout = calls[0]
    assert request.full_url == "https://chatgpt.com/backend-api/wham/usage"
    assert request.get_method() == "GET"
    assert request.data is None
    assert request.get_header("Authorization") == f"Bearer {_TOKEN}"
    assert request.get_header("Chatgpt-account-id") == _ACCOUNT
    assert timeout == io_module.CODEX_USAGE_READ_TIMEOUT_SECONDS
    assert timeout > 0
    assert reading.observable
    assert reading.allowed is True
    assert reading.limit_reached is False
    assert reading.governing_remaining_percent == 40.0


def test_the_credential_identity_is_a_one_way_digest_of_the_token() -> None:
    """Equality is the only question the journal asks of an identity."""
    io_module = _module("_dispatcher_codex_headroom_io")
    identity = io_module.projected_codex_credential_identity(access_token=_TOKEN)
    assert _TOKEN not in identity
    assert identity == io_module.projected_codex_credential_identity(access_token=_TOKEN)
    assert identity != io_module.projected_codex_credential_identity(
        access_token="other"  # noqa: S106 - a fixture string, not a credential.
    )
    assert (
        io_module.projected_codex_credential_identity(access_token=None)
        == io_module.ABSENT_CREDENTIAL_IDENTITY
    )


@pytest.mark.parametrize(
    ("auth_json", "expected"),
    [
        (None, "absent-credential"),
        ("{}", "absent-credential"),
        ('{"tokens": {"access_token": "t"}}', "absent-credential"),
        ("not json", "absent-credential"),
    ],
)
def test_an_unusable_snapshot_issues_no_request_and_is_journaled_unobservable(
    monkeypatch: pytest.MonkeyPatch, auth_json: str | None, expected: str
) -> None:
    """There is nothing to authenticate with, so no round trip is spent."""
    io_module = _module("_dispatcher_codex_headroom_io")
    calls: list[tuple[Request, float]] = []
    monkeypatch.setattr(io_module, "urlopen", _recording_urlopen(calls, payload=_usage_payload()))

    reading = io_module.read_projected_codex_usage(auth_json=auth_json, observed_at=_NOW)

    assert calls == []
    assert reading.unobservable == expected
    assert reading.windows == ()


def test_a_refused_read_is_unobservable_rather_than_a_number(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An authentication failure names itself and coerces no reading."""
    io_module = _module("_dispatcher_codex_headroom_io")
    monkeypatch.setattr(io_module, "urlopen", _refusing_urlopen(status=401))

    reading = io_module.read_projected_codex_usage(auth_json=_AUTH_JSON, observed_at=_NOW)

    assert reading.unobservable == "authentication-failed"
    assert reading.governing_remaining_percent is None


def test_the_policy_reads_once_and_attaches_a_projection_per_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two window lengths, one in-window baseline: two DIFFERENT results."""
    gate = _module("_dispatcher_codex_headroom_gate")
    codex_projection = _module("_acp_codex_headroom_projection")
    headroom = _module("_acp_session_headroom")
    journal_path = tmp_path / "journal.jsonl"
    _journal(path=journal_path, codex_entries=[_prior(used=30.0, seconds=_FIVE_HOURS)])
    reads: list[int] = []

    def read(*, auth_json: str | None, observed_at: str) -> CodexUsageReading:
        _ = auth_json
        reads.append(1)
        io_module = _module("_dispatcher_codex_headroom_io")
        return io_module.read_projected_codex_usage(auth_json=_AUTH_JSON, observed_at=observed_at)

    monkeypatch.setattr(
        _module("_dispatcher_codex_headroom_io"),
        "urlopen",
        _recording_urlopen([], payload=_usage_payload(primary_used=60.0, secondary_used=50.0)),
    )

    policy = gate.codex_headroom_policy(
        repo=tmp_path, now_iso=_NOW, journal_path=journal_path, read=read
    )
    first = policy.read()
    second = policy.read()

    assert sum(reads) == 1
    assert first is second
    assert policy.floor_percent == 20
    assert policy.horizon_minutes == 180
    by_window = {entry.limit_window_seconds: entry.projection for entry in first.projections}
    assert set(by_window) == {_FIVE_HOURS, _WEEK}
    assert by_window[_FIVE_HOURS].result == headroom.PROJECTED_RESULT
    assert by_window[_FIVE_HOURS].projected_exhaustion_at == "2026-10-27T13:20:00Z"
    assert by_window[_FIVE_HOURS].skip_applied
    assert by_window[_WEEK].result == headroom.UNAVAILABLE_RESULT
    assert by_window[_WEEK].reason == codex_projection.NO_BASELINE_REASON
    assert not by_window[_WEEK].skip_applied


def _journaled_record(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """The ONE record a Codex-and-Claude evaluation appends, as rendered.

    Shared by the three readings below rather than rebuilt per case, because
    they are three questions about ONE record: a per-case rebuild would let a
    build disagree with itself about which readings that evaluation took.
    """
    gate = _module("_dispatcher_codex_headroom_gate")
    journal_path = tmp_path / "journal.jsonl"
    _journal(path=journal_path, codex_entries=[_prior(used=30.0, seconds=_FIVE_HOURS)])
    monkeypatch.setattr(
        _module("_dispatcher_codex_headroom_io"),
        "urlopen",
        _recording_urlopen([], payload=_usage_payload(primary_used=60.0)),
    )

    def read(*, auth_json: str | None, observed_at: str) -> CodexUsageReading:
        _ = auth_json
        io_module = _module("_dispatcher_codex_headroom_io")
        return io_module.read_projected_codex_usage(auth_json=_AUTH_JSON, observed_at=observed_at)

    policy = gate.codex_headroom_policy(
        repo=tmp_path, now_iso=_NOW, journal_path=journal_path, read=read
    )
    verdict = AcpPreflightVerdict(
        fallback_enabled=True,
        session_headroom_floor_percent=20,
        session_headroom_horizon_minutes=180,
        headroom_assessments=(
            session_headroom_reading(
                credential_identity="claude-cred", observed_at=_NOW, utilization=10.0
            ),
        ),
        codex_headroom_assessments=(policy.read(),),
    )
    writer = _Journal()

    headroom_gate.journal_session_headroom(
        work_item_id="bd-ib-4jdgcw", verdict=verdict, journal=writer
    )

    [record] = writer.records
    return record


def _codex_row(*, record: dict[str, object]) -> dict[str, object]:
    rows = record[headroom_records.CODEX_ASSESSMENTS_KEY]
    assert isinstance(rows, list)
    assert len(rows) == 1
    assert isinstance(rows[0], dict)
    return rows[0]


def test_the_journal_record_carries_the_codex_rows_beside_the_claude_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One record, two providers, each reading named by its own credential."""
    record = _journaled_record(tmp_path=tmp_path, monkeypatch=monkeypatch)
    assert record["stage"] == headroom_records.SESSION_HEADROOM_STAGE
    claude_rows = record["assessments"]
    assert isinstance(claude_rows, list)
    assert claude_rows[0]["credential_identity"] == "claude-cred"
    row = _codex_row(record=record)
    assert row["credential_identity"] == _identity()
    assert row["observed_at"] == _NOW
    assert row["allowed"] is True
    assert row["limit_reached"] is False
    assert row["unobservable"] is None
    assert row["governing_remaining_percent"] == 40.0
    assert row["windows"] == [
        {"used_percent": 60.0, "limit_window_seconds": _FIVE_HOURS, "remaining_percent": 40.0}
    ]


def test_the_journaled_codex_row_carries_one_projection_per_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exactly one result, naming its window, its rate and its baseline."""
    headroom = _module("_acp_session_headroom")
    row = _codex_row(record=_journaled_record(tmp_path=tmp_path, monkeypatch=monkeypatch))
    projections = row["projections"]
    assert isinstance(projections, list)
    assert len(projections) == 1
    assert projections[0]["limit_window_seconds"] == _FIVE_HOURS
    assert projections[0]["result"] == headroom.PROJECTED_RESULT
    assert projections[0]["drain_percent_per_hour"] == 30.0
    assert projections[0]["baseline_observed_at"] == _BASELINE_AT
    assert projections[0]["projected_exhaustion_at"] == "2026-10-27T13:20:00Z"
    assert projections[0]["projection_skip_applied"] is True


def test_the_journaled_record_carries_no_credential_value_account_or_email(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The prohibition, asserted over the rendered bytes rather than key by key."""
    serialized = json.dumps(_journaled_record(tmp_path=tmp_path, monkeypatch=monkeypatch))
    assert _TOKEN not in serialized
    assert _ACCOUNT not in serialized
    assert _EMAIL not in serialized


def test_a_codex_only_evaluation_is_still_journaled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A repository routed wholly to Codex has readings to record too."""
    gate = _module("_dispatcher_codex_headroom_gate")
    monkeypatch.setattr(
        _module("_dispatcher_codex_headroom_io"),
        "urlopen",
        _recording_urlopen([], payload=_usage_payload(primary_used=10.0)),
    )

    def read(*, auth_json: str | None, observed_at: str) -> CodexUsageReading:
        _ = auth_json
        io_module = _module("_dispatcher_codex_headroom_io")
        return io_module.read_projected_codex_usage(auth_json=_AUTH_JSON, observed_at=observed_at)

    policy = gate.codex_headroom_policy(repo=tmp_path, now_iso=_NOW, journal_path=None, read=read)
    verdict = AcpPreflightVerdict(
        fallback_enabled=True,
        session_headroom_floor_percent=20,
        session_headroom_horizon_minutes=180,
        codex_headroom_assessments=(policy.read(),),
    )
    writer = _Journal()

    headroom_gate.journal_session_headroom(
        work_item_id="bd-ib-4jdgcw", verdict=verdict, journal=writer
    )

    [record] = writer.records
    assert record["assessments"] == []
    codex_rows = record[headroom_records.CODEX_ASSESSMENTS_KEY]
    assert isinstance(codex_rows, list)
    assert len(codex_rows) == 1
    assert codex_rows[0]["credential_identity"] == _identity()


def test_an_evaluation_that_assessed_nothing_writes_no_record() -> None:
    """The negative control: a row naming nothing is journal noise."""
    writer = _Journal()

    headroom_gate.journal_session_headroom(
        work_item_id="bd-ib-4jdgcw",
        verdict=AcpPreflightVerdict(fallback_enabled=True, session_headroom_floor_percent=20),
        journal=writer,
    )

    assert writer.records == []


def test_the_admission_pass_supplies_a_codex_policy() -> None:
    """A real dispatch's preflight has this clause's reading wired into it.

    Asserted over the ADMISSION path specifically, because every behavioural
    case above is driven through a policy the test itself built: a clause whose
    filter, record and gate are all correct and which no dispatch supplies a
    policy to is INERT, and inert is exactly what the measured defect this
    work-item closes looked like from every unit test.

    The seam is read off the RESOLVER'S SIGNATURE rather than from source text,
    because that is what a dispatch passes through; the admission module's own
    source is read only for the one thing a signature cannot show -- that it
    BUILDS a Codex policy and puts it there.
    """
    import inspect

    source = inspect.getsource(_module("_dispatcher_admission"))
    assert "codex=codex_headroom_policy(" in source
    preflight_module = _module("_dispatcher_acp_preflight")
    assert (
        "headroom_policies" in inspect.signature(preflight_module.resolve_acp_preflight).parameters
    )
    assert {
        field.name
        for field in __import__("dataclasses").fields(preflight_module.AdmissionHeadroomPolicies)
    } == {"claude", "codex"}
    assert "codex_headroom" in {
        field.name for field in __import__("dataclasses").fields(preflight.PreflightInputs)
    }
