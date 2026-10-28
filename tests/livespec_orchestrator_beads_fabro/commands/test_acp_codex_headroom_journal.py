"""Each Codex assessment is journaled beside the Claude assessment records.

Binds the third Definition-of-Done assertion of the Codex-headroom work-item to
"Admission filters Codex candidates by projected usage-window headroom" in
`SPECIFICATION/contracts.md`: for each affected work-item and assessed Codex
credential the Dispatcher journals the opaque non-secret credential identity,
the utilization reading or an explicit unobservable result, the observation time
and exactly one projection result per window. The journal never carries a
credential value, the account email or a raw provider response.

The rows are produced through the PRODUCTION admission pass over the REAL
policy builder, with only the provider's HTTP call and the host credential file
replaced, so the journaled shape is the one an operator reads. The last case
closes the loop: the row the writer appends is the row the baseline reader
projects, which is what keeps the projection's history and the journal from
drifting onto two spellings of one key.
"""

from __future__ import annotations

import io
import json
from dataclasses import dataclass
from email.message import Message
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock
from urllib.error import HTTPError

import pytest
from livespec_orchestrator_beads_fabro.commands import _acp_candidate_preflight as preflight
from livespec_orchestrator_beads_fabro.commands import _acp_session_headroom as headroom
from livespec_orchestrator_beads_fabro.commands import _dispatcher_admission as admission_module
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_admission_eligibility as eligibility_module,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_codex_headroom_gate as codex_gate,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_codex_headroom_io as codex_io,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_session_headroom_gate as headroom_gate,
)
from livespec_orchestrator_beads_fabro.commands._acp_agent_catalog import (
    CLAUDE_AGENT_ID,
    CODEX_AGENT_ID,
)
from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import (
    AcpCandidate,
    AcpCandidateIdentity,
)
from livespec_orchestrator_beads_fabro.commands._acp_chain_resolution import ResolvedAcpChain
from livespec_orchestrator_beads_fabro.commands._acp_hold_ledger import read_acp_hold_ledger
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import AcpAdapter
from livespec_orchestrator_beads_fabro.commands._acp_preflight_verdict import (
    build_acp_preflight_verdict,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.types import WorkItem

_NOW = "2026-10-28T06:00:00Z"
_EARLIER = "2026-10-28T05:00:00Z"
_CODEX_STAGE = "acp-codex-session-headroom"
_CLAUDE_STAGE = "acp-session-headroom"
_TOKEN = "projected-access-token-value"
_ACCOUNT = "account-0123456789"
_EMAIL = "operator@example.com"
_GRAPH = """
    start [shape=Mdiamond]
    exit  [shape=Msquare]
    implement [backend="acp", acp.command="a"]
    start -> implement
    implement -> exit
"""


@dataclass(frozen=True)
class _Accounting:
    active_count: int = 0
    live_lock_active_ids: tuple[str, ...] = ()
    journal_unreadable_active_ids: tuple[str, ...] = ()
    green_terminal_active_ids: tuple[str, ...] = ()
    rework_pending_active_ids: tuple[str, ...] = ()


def _item(*, item_id: str) -> WorkItem:
    fields: dict[str, object] = {
        "id": item_id,
        "type": "task",
        "status": "ready",
        "title": "Task",
        "description": "Do it.",
        "origin": "freeform",
        "gap_id": None,
        "rank": "a1",
        "assignee": None,
        "depends_on": (),
        "captured_at": "2026-07-16T00:00:00Z",
        "resolution": None,
        "reason": None,
        "audit": None,
        "superseded_by": None,
        "admission_policy": None,
        "acceptance_policy": None,
    }
    return WorkItem(**fields)  # pyright: ignore[reportArgumentType]


def _candidate(*, agent_id: str) -> AcpCandidate:
    return AcpCandidate(
        adapter=AcpAdapter(command=f"{agent_id}-adapter", env={}, args=()),
        identity=AcpCandidateIdentity(
            display_name=agent_id, candidate_key=f"{agent_id}-key", availability_key=agent_id
        ),
        agent_id=agent_id,
    )


def _chain(*, agents: tuple[str, ...]) -> ResolvedAcpChain:
    candidates = tuple(_candidate(agent_id=agent) for agent in agents)
    return ResolvedAcpChain(
        node="implement",
        primary=candidates[0],
        fallbacks=candidates[1:],
        enabled=True,
        primary_generation="primary",
        full_chain="chain",
        redacted={},
    )


def _usage_body(*, used: float) -> bytes:
    return json.dumps(
        {
            "email": _EMAIL,
            "rate_limit": {
                "allowed": True,
                "limit_reached": False,
                "primary_window": {"used_percent": used, "limit_window_seconds": 18000},
                "secondary_window": None,
            },
            "credits": {"balance": "900"},
        }
    ).encode()


def _provider(monkeypatch: pytest.MonkeyPatch, *, tmp_path: Path, outcome: object) -> None:
    home = tmp_path / "codex-home"
    home.mkdir()
    _ = (home / "auth.json").write_text(
        json.dumps({"tokens": {"access_token": _TOKEN, "account_id": _ACCOUNT}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(home))

    def _urlopen(request: object, *, timeout: float) -> MagicMock:
        _ = (request, timeout)
        if isinstance(outcome, BaseException):
            raise outcome
        response = MagicMock()
        response.read.return_value = outcome
        response.__enter__.return_value = response
        return response

    monkeypatch.setattr(codex_io, "urlopen", _urlopen)


def _claude_untouched(*, token: str | None, observed_at: str) -> headroom.SessionHeadroomReading:
    _ = token
    return headroom.session_headroom_reading(
        credential_identity="claude-cred", observed_at=observed_at, utilization=0
    )


def _admit(
    monkeypatch: pytest.MonkeyPatch,
    *,
    tmp_path: Path,
    agents: tuple[str, ...] = (CODEX_AGENT_ID, CLAUDE_AGENT_ID),
    now: str = _NOW,
    item_ids: tuple[str, ...] = ("bd-ib-ready",),
) -> list[dict[str, Any]]:
    journal_path = tmp_path / "journal.jsonl"
    journal_path.touch()
    policy = headroom_gate.session_headroom_policy(
        repo=tmp_path, now_iso=now, journal_path=journal_path, read=_claude_untouched
    )
    verdict = build_acp_preflight_verdict(
        chains={"implement": _chain(agents=agents)},
        graph_text=_GRAPH,
        ledger=read_acp_hold_ledger(journal_path=None, now_iso=now),
        inputs=preflight.PreflightInputs(headroom=policy),
    )
    monkeypatch.setattr(admission_module, "resolve_acp_preflight", lambda **_: verdict)
    monkeypatch.setattr(admission_module, "store_config", lambda **_: tmp_path)
    monkeypatch.setattr(admission_module, "update_work_item_status", lambda **_: None)
    monkeypatch.setattr(admission_module, "claimed_active_accounting", lambda **_: _Accounting())
    monkeypatch.setattr(eligibility_module, "read_dispatch_labels", lambda **_: ())

    _ = admission_module.admit_and_select(
        repo=tmp_path,
        items=[],
        candidates=[_item(item_id=item_id) for item_id in item_ids],
        journal=JournalFile(path=journal_path),
        enforce_cap=False,
    )
    return [
        json.loads(line)
        for line in journal_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _codex_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [record for record in records if record.get("stage") == _CODEX_STAGE]


def test_a_codex_assessment_is_journaled_beside_the_claude_record(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _provider(monkeypatch, tmp_path=tmp_path, outcome=_usage_body(used=25.0))

    records = _admit(monkeypatch, tmp_path=tmp_path)

    codex_rows = _codex_rows(records)
    assert len(codex_rows) == 1
    row = codex_rows[0]
    assert row["work_item_id"] == "bd-ib-ready"
    assert row["session_headroom_floor_percent"] == 20
    [assessment] = row["assessments"]
    assert assessment["credential_identity"] == codex_io.codex_credential_identity(
        account_id=_ACCOUNT
    )
    assert assessment["observed_at"] == _NOW
    assert assessment["allowed"] is True
    assert assessment["limit_reached"] is False
    assert assessment["unobservable"] is None
    [window] = assessment["windows"]
    assert window["used_percent"] == 25.0
    assert window["remaining_percent"] == 75.0
    assert window["limit_window_seconds"] == 18000
    assert window["projection"]["result"] == "unavailable"
    assert window["projection"]["reason"] == "no-baseline"
    claude_rows = [record for record in records if record.get("stage") == _CLAUDE_STAGE]
    assert len(claude_rows) == 1
    assert records.index(claude_rows[0]) < records.index(row)


def test_each_affected_work_item_gets_its_own_codex_row(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _provider(monkeypatch, tmp_path=tmp_path, outcome=_usage_body(used=25.0))

    records = _admit(monkeypatch, tmp_path=tmp_path, item_ids=("bd-ib-one", "bd-ib-two"))

    assert [row["work_item_id"] for row in _codex_rows(records)] == ["bd-ib-one", "bd-ib-two"]


@pytest.mark.parametrize(
    ("outcome", "reason"),
    [
        (TimeoutError(), "timed-out"),
        (
            HTTPError(
                url=codex_io.CODEX_USAGE_URL,
                code=401,
                msg="no",
                hdrs=cast("Message", Message()),
                fp=io.BytesIO(b"raw provider words"),
            ),
            "authentication-failed",
        ),
        (b"not json", "unreadable-response"),
    ],
)
def test_an_unobservable_codex_reading_is_journaled_as_such_and_never_as_a_number(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, outcome: object, reason: str
) -> None:
    _provider(monkeypatch, tmp_path=tmp_path, outcome=outcome)

    records = _admit(monkeypatch, tmp_path=tmp_path)

    rows = _codex_rows(records)
    assert len(rows) == 1
    [assessment] = rows[0]["assessments"]
    assert assessment["unobservable"] == reason
    assert assessment["windows"] == []
    assert assessment["allowed"] is None
    assert assessment["projection"]["result"] == "not-projected"
    assert assessment["projection"]["reason"] == "unobservable"
    assert "raw provider words" not in json.dumps(records)


def test_no_credential_value_account_email_or_raw_response_is_journaled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _provider(monkeypatch, tmp_path=tmp_path, outcome=_usage_body(used=25.0))

    records = _admit(monkeypatch, tmp_path=tmp_path)

    text = json.dumps(records)
    for secret in (_TOKEN, _ACCOUNT, _EMAIL, "credits", "900"):
        assert secret not in text


def test_a_chain_with_no_codex_candidate_journals_no_codex_row(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _provider(monkeypatch, tmp_path=tmp_path, outcome=_usage_body(used=25.0))

    records = _admit(monkeypatch, tmp_path=tmp_path, agents=(CLAUDE_AGENT_ID,))

    assert _codex_rows(records) == []
    assert [r for r in records if r.get("stage") == _CLAUDE_STAGE]


def test_a_floor_of_zero_still_journals_the_reading(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _ = (tmp_path / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "dispatcher": {"session_headroom_floor_percent": 0}
                }
            }
        ),
        encoding="utf-8",
    )
    _provider(monkeypatch, tmp_path=tmp_path, outcome=_usage_body(used=99.0))

    records = _admit(monkeypatch, tmp_path=tmp_path)

    rows = _codex_rows(records)
    assert len(rows) == 1
    assert rows[0]["session_headroom_floor_percent"] == 0
    [assessment] = rows[0]["assessments"]
    assert assessment["windows"][0]["projection"]["reason"] == "floor-zero"


def test_the_journaled_row_is_the_row_the_baseline_reader_projects(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _provider(monkeypatch, tmp_path=tmp_path, outcome=_usage_body(used=30.0))
    _ = _admit(monkeypatch, tmp_path=tmp_path, now=_EARLIER)
    identity = codex_io.codex_credential_identity(account_id=_ACCOUNT)

    baseline = codex_gate.codex_window_baseline(
        journal_path=tmp_path / "journal.jsonl",
        credential_identity=identity,
        window_seconds=18000,
        now_iso=_NOW,
    )

    assert baseline is not None
    assert baseline.utilization_percent == 30.0
    assert baseline.observed_at == _EARLIER
    assert baseline.elapsed_hours == 1.0
