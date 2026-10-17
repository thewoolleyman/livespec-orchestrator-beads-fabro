"""The SELECTION record a headroom skip leaves behind, per node.

Binds `SPECIFICATION/scenarios.md` Scenario 60's "Low session headroom on the
primary selects an uncovered fallback" together with the headroom sentence
added to `SPECIFICATION/contracts.md` section "Factory-configurable ACP
fallback priority"'s Per-node selection paragraph: "When headroom skips an
earlier candidate, the selection record MUST identify that candidate and
reference its headroom assessment and governing floor; it MUST NOT represent
that skip as an observed hold."

THE WHOLE RECORD IS ASSERTED, not a field at a time, and that is deliberate.
The record is read by a human triaging why a dispatch chose a fallback, and the
failure mode is a record that names the right facts in a shape nothing joins:
an extra key nobody reads, or a skipped candidate reported without the floor
that condemned it. One equality assertion over the whole object pins the shape
and catches an addition as readily as an omission.

THE NEGATIVE NODE MATTERS AS MUCH AS THE POSITIVE ONE. A node whose candidates
all passed must report an EMPTY skip list rather than be absent: a reader
cannot tell an absent node from a node that was never filtered, and "which
nodes did headroom touch" is the question the record exists to answer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import _acp_candidate_preflight as preflight
from livespec_orchestrator_beads_fabro.commands import _acp_session_headroom as headroom
from livespec_orchestrator_beads_fabro.commands import _dispatcher_admission as admission_module
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_admission_eligibility as eligibility_module,
)
from livespec_orchestrator_beads_fabro.commands._acp_builtin_candidates import ANTHROPIC_DOMAIN
from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import (
    AcpCandidate,
    AcpCandidateIdentity,
)
from livespec_orchestrator_beads_fabro.commands._acp_chain_resolution import ResolvedAcpChain
from livespec_orchestrator_beads_fabro.commands._acp_hold_ledger import read_acp_hold_ledger
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import AcpAdapter
from livespec_orchestrator_beads_fabro.commands._acp_preflight_verdict import (
    AcpPreflightVerdict,
    build_acp_preflight_verdict,
)
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom_records import (
    SESSION_HEADROOM_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_preflight import (
    ACP_PREFLIGHT_REFUSAL_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.types import WorkItem

_NOW = "2026-10-14T12:00:00Z"
_FLOOR = 20
_HORIZON = headroom.DEFAULT_SESSION_HEADROOM_HORIZON_MINUTES
# The attribution envelope `JournalFile.append` stamps onto every record. It is
# dropped before the whole-record comparison below because its `at` is the live
# clock and its `invoker` is the host: asserting them would bind this case to
# the machine it ran on rather than to the record the clause requires.
_ENVELOPE_KEYS = frozenset({"at", "invoker", "invoker_source"})
_CLAUDE_PAIR = (ANTHROPIC_DOMAIN, "builtin-anthropic-0123456789abcdef")
_BUILTIN_PAIRS = frozenset({_CLAUDE_PAIR})

_TWO_NODE_GRAPH = """
    start [shape=Mdiamond]
    exit  [shape=Msquare]
    implement [backend="acp", acp.command="a"]
    review    [backend="acp", acp.command="b"]
    start -> implement
    implement -> review
    review -> exit
"""


def _identity(*, availability_key: str, candidate_key: str) -> AcpCandidateIdentity:
    return AcpCandidateIdentity(
        display_name=f"{availability_key}/{candidate_key}",
        candidate_key=candidate_key,
        availability_key=availability_key,
    )


def _covered() -> AcpCandidate:
    return AcpCandidate(
        adapter=AcpAdapter(command="claude-adapter", env={}, args=()),
        identity=_identity(availability_key=_CLAUDE_PAIR[0], candidate_key=_CLAUDE_PAIR[1]),
    )


def _uncovered(*, candidate_key: str = "gpt-5-5") -> AcpCandidate:
    return AcpCandidate(
        adapter=AcpAdapter(command="codex-adapter", env={}, args=()),
        identity=_identity(availability_key="codex", candidate_key=candidate_key),
    )


def _chain(*, node: str, candidates: tuple[AcpCandidate, ...]) -> ResolvedAcpChain:
    return ResolvedAcpChain(
        node=node,
        primary=candidates[0],
        fallbacks=tuple(candidates[1:]),
        enabled=True,
        primary_generation=f"{node}-primary-digest",
        full_chain=f"{node}-chain-digest",
        redacted={},
    )


def _policy(*, utilization: object = 90) -> headroom.SessionHeadroomPolicy:
    reading = headroom.session_headroom_reading(
        credential_identity="cred-1", observed_at=_NOW, utilization=utilization
    )
    return headroom.SessionHeadroomPolicy(
        floor_percent=_FLOOR,
        horizon_minutes=headroom.DEFAULT_SESSION_HEADROOM_HORIZON_MINUTES,
        read=lambda: reading,
    )


def _verdict(*, chains: dict[str, ResolvedAcpChain]) -> AcpPreflightVerdict:
    return build_acp_preflight_verdict(
        chains=chains,
        graph_text=_TWO_NODE_GRAPH,
        ledger=read_acp_hold_ledger(journal_path=None, now_iso=_NOW),
        inputs=preflight.PreflightInputs(builtin_pairs=_BUILTIN_PAIRS, headroom=_policy()),
    )


def _item(**overrides: object) -> WorkItem:
    fields: dict[str, object] = {
        "id": "bd-ib-item",
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
    fields.update(overrides)
    return WorkItem(**fields)  # pyright: ignore[reportArgumentType]


@dataclass(frozen=True, kw_only=True)
class _Accounting:
    active_count: int = 0
    live_lock_active_ids: tuple[str, ...] = ()
    journal_unreadable_active_ids: tuple[str, ...] = ()
    green_terminal_active_ids: tuple[str, ...] = ()
    rework_pending_active_ids: tuple[str, ...] = ()


def _journal_records(*, path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _run_admission(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    verdict: AcpPreflightVerdict,
) -> tuple[list[WorkItem], list[dict[str, Any]]]:
    monkeypatch.setattr(admission_module, "resolve_acp_preflight", lambda **_: verdict)
    monkeypatch.setattr(admission_module, "store_config", lambda **_: tmp_path)
    monkeypatch.setattr(admission_module, "update_work_item_status", lambda **_: None)
    monkeypatch.setattr(admission_module, "claimed_active_accounting", lambda **_: _Accounting())
    monkeypatch.setattr(eligibility_module, "read_dispatch_labels", lambda **_: ())
    journal_path = tmp_path / "journal.jsonl"

    result = admission_module.admit_and_select(
        repo=tmp_path,
        items=[],
        candidates=[_item(id="bd-ib-ready")],
        journal=JournalFile(path=journal_path),
        enforce_cap=False,
    )

    return list(result.admitted), _journal_records(path=journal_path)


def _payload(*, record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key not in _ENVELOPE_KEYS}


def _reading_fields(*, utilization: float, remaining: float) -> dict[str, object]:
    return {
        "credential_identity": "cred-1",
        "utilization_percent": utilization,
        "remaining_percent": remaining,
        "unobservable": None,
        "observed_at": _NOW,
        "five_hour_drain_percent_per_hour": None,
        "projection": None,
        "unverified_provider_reset_claim": None,
    }


def test_a_skipped_primary_admits_the_item_on_its_fallback_and_says_why(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole record, asserted at once, for the scenario's own shape.

    `implement` has a covered primary below the floor and an eligible uncovered
    fallback; `review` has one uncovered candidate and is untouched. So the
    record must select the fallback for the first node, name the primary it
    skipped with that primary's own reading and the governing floor, and report
    the second node as filtered-and-unskipped rather than omitting it.
    """
    admitted, records = _run_admission(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        verdict=_verdict(
            chains={
                "implement": _chain(node="implement", candidates=(_covered(), _uncovered())),
                "review": _chain(node="review", candidates=(_uncovered(candidate_key="o4"),)),
            }
        ),
    )

    assert [item.id for item in admitted] == ["bd-ib-ready"]
    assert [record for record in records if record["stage"] == ACP_PREFLIGHT_REFUSAL_STAGE] == []
    [record] = [record for record in records if record["stage"] == SESSION_HEADROOM_STAGE]
    assert _payload(record=record) == {
        "stage": SESSION_HEADROOM_STAGE,
        "work_item_id": "bd-ib-ready",
        "session_headroom_floor_percent": _FLOOR,
        "assessments": [_reading_fields(utilization=90.0, remaining=10.0)],
        "node_selections": {
            "implement": {
                "selected_availability_key": "codex",
                "selected_candidate_key": "gpt-5-5",
                "headroom_skipped": [
                    {
                        "availability_key": _CLAUDE_PAIR[0],
                        "candidate_key": _CLAUDE_PAIR[1],
                        "session_headroom_floor_percent": _FLOOR,
                        "session_headroom_horizon_minutes": _HORIZON,
                        "headroom_skip_kind": "floor",
                        "headroom": _reading_fields(utilization=90.0, remaining=10.0),
                    }
                ],
            },
            "review": {
                "selected_availability_key": "codex",
                "selected_candidate_key": "o4",
                "headroom_skipped": [],
            },
        },
    }


def test_an_exhausted_node_reports_no_selected_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A node headroom emptied names its skip and selects nothing.

    `selected_candidate_key` is NULL rather than absent, for the same reason
    every reading field is written: an omitted key is what a record from a
    build predating this clause looks like.
    """
    _admitted, records = _run_admission(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        verdict=_verdict(
            chains={
                "implement": _chain(node="implement", candidates=(_covered(),)),
                "review": _chain(node="review", candidates=(_uncovered(),)),
            }
        ),
    )

    [record] = [record for record in records if record["stage"] == SESSION_HEADROOM_STAGE]
    selections = record["node_selections"]
    assert selections["implement"]["selected_candidate_key"] is None
    assert selections["implement"]["selected_availability_key"] is None
    assert [skip["candidate_key"] for skip in selections["implement"]["headroom_skipped"]] == [
        _CLAUDE_PAIR[1]
    ]


def test_the_skipped_entry_names_no_hold_identity_of_any_kind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ "It MUST NOT represent that skip as an observed hold" -- as a key set.

    Asserted on the KEYS rather than on their values, because a `hold_key` of
    `None` is still a record inviting a reader to join a headroom shortfall to
    the availability-hold ledger, where it will match nothing.
    """
    _admitted, records = _run_admission(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        verdict=_verdict(
            chains={
                "implement": _chain(node="implement", candidates=(_covered(), _uncovered())),
                "review": _chain(node="review", candidates=(_uncovered(),)),
            }
        ),
    )

    [record] = [record for record in records if record["stage"] == SESSION_HEADROOM_STAGE]
    [skip] = record["node_selections"]["implement"]["headroom_skipped"]
    assert set(skip) == {
        "availability_key",
        "candidate_key",
        "session_headroom_floor_percent",
        "session_headroom_horizon_minutes",
        "headroom_skip_kind",
        "headroom",
    }
