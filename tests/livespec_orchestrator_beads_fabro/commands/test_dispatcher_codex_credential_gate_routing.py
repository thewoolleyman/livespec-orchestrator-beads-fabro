"""The pre-claim Codex credential gate, scoped to dispatches that route Codex.

`bd-ib-meejjz`. `SPECIFICATION/contracts.md` section "Worker credential
projection" requires the freshness gate for every PROJECTED credential it
covers, and leaves WHICH projected credentials it covers to the implementation;
`SPECIFICATION/scenarios.md` Scenario 19 is the refusal itself, which this
module asserts is unchanged for a dispatch that does route a node to Codex.

WHAT WAS WRONG. The gate graded the host Codex credential for EVERY selection.
Since every factory node in this repository resolves to `claude-acp`, dispatches
were refused as that token aged although no run would have used it, and the
credential-lifetime floor the grade is taken against -- a sum over every node
timeout -- capped how long any node could be given.

THE MEASUREMENT HERE IS THE INTERACTION LOG, NOT THE RETURN VALUE, and that is
the whole point of this file. A gate that read the credential, spent the bounded
provider renewal, graded the result and then discarded it would return `None`
exactly as a gate that never looked does -- so an end-state assertion cannot
tell "not applied" from "applied and ignored". The provider request is the
expensive half and the one an operator is billed for, so each case below counts
reads, renewals and clock readings.

AND BOTH DIRECTIONS ARE DRIVEN OVER THE SAME CREDENTIAL. The stale credential
these cases hand the gate is one it WOULD refuse, which is what makes the
all-Claude arm a control rather than a restatement of a benign fixture: a gate
left armed returns a refusal there, and an instrument given a credential that
cannot be refused could not have returned a hit either way.
"""

from __future__ import annotations

import argparse
import base64
import importlib
import json
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_codex_auth,
    _dispatcher_codex_credential_gate,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_deadline import (
    CredentialLifetimeRequirement,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_projection import (
    CODEX_FRESHNESS_MARGIN_SECONDS,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_WALL_MODULE = f"{_PACKAGE}._dispatcher_pre_dispatch_wall"
_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMMANDS = (
    _REPO_ROOT / ".claude-plugin" / "scripts" / "livespec_orchestrator_beads_fabro" / "commands"
)
_ROUTING_MODULE_PATH = _COMMANDS / "_dispatcher_codex_routing.py"

_NOW = 1_000_000
_REQUIRED_REMAINING = 18_000
_REQUIREMENT = CredentialLifetimeRequirement(
    allowance_seconds=_REQUIRED_REMAINING - CODEX_FRESHNESS_MARGIN_SECONDS,
    margin_seconds=CODEX_FRESHNESS_MARGIN_SECONDS,
    detail="test-resolved requirement",
)

_CLAUDE_KEY = "claude-acp/anthropic/claude-opus-5"
_CODEX_KEY = "codex-acp/openai/gpt-5.5"


class _StubOutcome:
    """A stand-in `CodexRenewalOutcome` carrying the two fields diagnostics read."""

    def __init__(self, *, answered: bool, detail: str) -> None:
        self.answered = answered
        self.detail = detail


class _RecordingJournal:
    """A journal that keeps what was appended instead of serializing it."""

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def append(self, *, record: dict[str, Any]) -> None:
        self.records.append(record)


def _auth_json_with_exp(*, exp: int) -> str:
    """A host Codex `auth.json` whose access-token JWT carries `exp`."""
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return json.dumps(
        {
            "auth_mode": "chatgpt",
            "tokens": {
                "access_token": f"header.{payload}.sig",
                "refresh_token": "host-refresh-token",
                "id_token": "id-token-value",
                "account_id": "acct-123",
            },
        }
    )


def _stub_credential_source(*, monkeypatch: pytest.MonkeyPatch, log: list[str]) -> None:
    """Stand in the host credential and the bounded renewal, logging every touch.

    ONE log carries all three interactions, so "the gate was not applied" is
    read off an empty log rather than off a `None` return a fully-applied gate
    also produces.
    """
    stale = _auth_json_with_exp(exp=_NOW - 10)

    def _read() -> str:
        log.append("read-credential")
        return stale

    def _renew() -> _StubOutcome:
        log.append("renew")
        return _StubOutcome(answered=True, detail="answered by the host Codex app-server")

    monkeypatch.setattr(_dispatcher_codex_auth, "read_host_codex_auth", _read)
    monkeypatch.setattr(
        _dispatcher_codex_auth, "renew_host_codex_credential", _renew, raising=False
    )


def _routing(*, codex: bool) -> Any:
    """The routing value the gate is handed, built through the real predicate."""
    assert _ROUTING_MODULE_PATH.is_file(), "_dispatcher_codex_routing.py is not implemented yet"
    return importlib.import_module(f"{_PACKAGE}._dispatcher_codex_routing").codex_routing_for(
        candidates=_candidates(codex=codex)
    )


def _candidates(*, codex: bool) -> tuple[Any, ...]:
    """A resolved candidate set, all-Claude or carrying one pinned Codex entry."""
    keys = (_CLAUDE_KEY, _CODEX_KEY) if codex else (_CLAUDE_KEY,)
    coverage = importlib.import_module(f"{_PACKAGE}._acp_dispatch_coverage")
    schema = importlib.import_module(f"{_PACKAGE}._acp_candidate_schema")
    adapters = importlib.import_module(f"{_PACKAGE}._acp_node_adapters")
    return tuple(
        coverage.RenderedCandidate(
            candidate=schema.AcpCandidate(
                adapter=adapters.AcpAdapter(command="adapter", env={}, args=()),
                identity=schema.AcpCandidateIdentity(
                    display_name="candidate",
                    candidate_key=key,
                    availability_key="codex" if key == _CODEX_KEY else "anthropic",
                ),
            ),
            builtin=False,
        )
        for key in keys
    )


def test_an_all_claude_dispatch_is_neither_graded_nor_charged_a_renewal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No read, no bounded provider request, no refusal on remaining lifetime.

    The credential handed in has already expired, so a gate still applied here
    returns a refusal and appears in the log. The empty log is what says the
    host credential was never touched -- which is the half an operator is
    billed for, and the half a discarded-grade implementation would still spend.
    """
    gate = _dispatcher_codex_credential_gate
    log: list[str] = []
    _stub_credential_source(monkeypatch=monkeypatch, log=log)

    refusal = gate.codex_credential_refusal_for_items(
        work_item_ids=("bd-ib-meejjz",),
        requirement=_REQUIREMENT,
        routing=_routing(codex=False),
        clock=lambda: _NOW,
    )

    assert refusal is None
    assert log == []


def test_the_gate_journals_that_it_was_not_applied_and_names_the_routing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The durable record, carrying the routing rather than a bare "skipped".

    A pass that is not refused leaves no `active` row and no run to read, so the
    journal is the only surface the decision survives on. "Not applied" on its
    own cannot be audited: the question a reader has is WHICH routing decided
    it, which is why the record carries the resolved candidate keys the
    predicate read.
    """
    gate = _dispatcher_codex_credential_gate
    log: list[str] = []
    _stub_credential_source(monkeypatch=monkeypatch, log=log)
    journal = _RecordingJournal()

    refusal = gate.codex_credential_refusal_for_items(
        work_item_ids=("bd-ib-meejjz", "bd-ib-qieqc6"),
        requirement=_REQUIREMENT,
        routing=_routing(codex=False),
        clock=lambda: _NOW,
        journal=journal,
    )

    assert refusal is None
    assert len(journal.records) == 1
    record = journal.records[0]
    assert record["stage"] == gate.CODEX_CREDENTIAL_GATE_NOT_APPLIED_STAGE
    assert record["unclaimed_work_item_ids"] == ["bd-ib-meejjz", "bd-ib-qieqc6"]
    assert _CLAUDE_KEY in record["routing"]
    # The record is an audit line, never a credential copy.
    assert "host-refresh-token" not in json.dumps(record, sort_keys=True)


def test_a_codex_routing_dispatch_is_graded_refused_and_renewed_exactly_as_before(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario 19 is untouched where a node does route to Codex.

    One candidate separates this case from the one above -- same credential,
    same requirement, same clock -- so a build that disabled the gate outright
    passes that test and fails this one, and a build that ignored the routing
    passes this one and fails that.
    """
    gate = _dispatcher_codex_credential_gate
    log: list[str] = []
    _stub_credential_source(monkeypatch=monkeypatch, log=log)
    journal = _RecordingJournal()

    refusal = gate.codex_credential_refusal_for_items(
        work_item_ids=("bd-ib-meejjz",),
        requirement=_REQUIREMENT,
        routing=_routing(codex=True),
        clock=lambda: _NOW,
        journal=journal,
    )

    assert refusal is not None
    # Read, renewed once, read back: the whole bounded-renewal sequence.
    assert log == ["read-credential", "renew", "read-credential"]
    assert [record["stage"] for record in journal.records] == [gate.CODEX_CREDENTIAL_GATE_STAGE]


def test_an_unmeasured_routing_grades_the_credential_as_it_always_did() -> None:
    """A caller wiring no routing inherits the protected answer.

    Every pre-existing caller and test of this gate passes no routing at all, so
    the default decides what happens to them. It has to be the grading one: a
    default that exempted an unmeasured dispatch would make forgetting to wire
    the routing indistinguishable from establishing that no node routes to
    Codex, which is the fail-OPEN direction.
    """
    routing_module = importlib.import_module(f"{_PACKAGE}._dispatcher_codex_routing")
    gate = _dispatcher_codex_credential_gate
    journal = _RecordingJournal()

    # The autouse hermetic Codex credential is far-future, so the ordinary pass
    # is the admitted one -- and the instrument that it was GRADED rather than
    # skipped is the absence of the not-applied record.
    admitted = gate.codex_credential_refusal_for_items(
        work_item_ids=("bd-ib-meejjz",),
        requirement=_REQUIREMENT,
        journal=journal,
    )

    assert admitted is None
    assert routing_module.UNMEASURED_CODEX_ROUTING.routes_codex is True
    assert journal.records == []


def _work_item() -> WorkItem:
    return WorkItem(
        id="bd-ib-meejjz",
        type="bug",
        status="ready",
        title="Scope the Codex credential gate to dispatches that route Codex",
        description="Three surfaces applied the gate to every dispatch.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-14T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def test_the_wall_resolves_this_dispatch_routing_and_hands_it_to_the_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The wiring: the ONE wall both dispatch paths run reads the routing itself.

    Asserted at the wall rather than only at the gate because the gate's default
    is the protected one -- so a wall that resolved no routing at all would
    leave every surface exactly as it was while every gate-level case above
    still passed.

    The requirement derivation is stood in, not exercised: it reads the selected
    workflow's registry entry, run config and graph plus each item's ledger
    labels, none of which a `tmp_path` repository has, and none of which this
    case is about.
    """
    wall = importlib.import_module(_WALL_MODULE)
    captured: dict[str, Any] = {}

    def _capture(**kwargs: Any) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(wall, "pre_dispatch_criteria_refusal", lambda **_kwargs: None)
    monkeypatch.setattr(wall, "proof_assets_refusal_for_items", lambda **_kwargs: None)
    monkeypatch.setattr(wall, "proof_credentials_refusal_for_items", lambda **_kwargs: None)
    monkeypatch.setattr(wall, "credential_wrapper_text", lambda **_kwargs: "")
    monkeypatch.setattr(wall, "selection_credential_requirement", lambda **_kwargs: _REQUIREMENT)
    monkeypatch.setattr(
        wall, "resolve_dispatch_candidates", lambda **_kwargs: _candidates(codex=False)
    )
    monkeypatch.setattr(wall, "codex_credential_refusal_for_items", _capture)
    journal_path = tmp_path / "tmp" / "fabro-dispatch-journal.jsonl"
    journal_path.parent.mkdir(parents=True, exist_ok=True)

    exit_code = wall.pre_dispatch_wall_exit(
        args=argparse.Namespace(
            repo=str(tmp_path),
            journal=str(journal_path),
            item="bd-ib-meejjz",
            as_json=False,
            skip_ledger_check=True,
            workflow_name=None,
        ),
        repo=tmp_path,
        items=[_work_item()],
        journal=_RecordingJournal(),
        reclaim_publish_branches=False,
    )

    assert exit_code is None
    assert captured["routing"].routes_codex is False
    assert _CLAUDE_KEY in captured["routing"].detail
