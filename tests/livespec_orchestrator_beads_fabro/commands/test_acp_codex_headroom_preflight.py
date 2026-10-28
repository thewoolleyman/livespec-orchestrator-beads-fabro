"""Where the Codex headroom filter sits, and what it leaves untouched.

Binds the carry-over rules of "Admission filters Codex candidates by projected
usage-window headroom" in `SPECIFICATION/contracts.md`: every Codex skip is
ephemeral and candidate-local, a policy carrying no Codex read leaves Codex
candidates exactly as they were before the clause, a reading is recorded whether
or not it skipped anything, one credential contributes one verdict row, and a
Claude candidate is never assessed by the Codex read.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands import _acp_candidate_preflight as preflight
from livespec_orchestrator_beads_fabro.commands import _acp_codex_headroom as codex
from livespec_orchestrator_beads_fabro.commands import _acp_session_headroom as headroom
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

_NOW = "2026-10-28T06:00:00Z"
_GRAPH = """
    start [shape=Mdiamond]
    exit  [shape=Msquare]
    implement [backend="acp", acp.command="a"]
    review [backend="acp", acp.command="b"]
    start -> implement
    implement -> review
    review -> exit
"""


def _candidate(*, agent_id: str, key: str) -> AcpCandidate:
    return AcpCandidate(
        adapter=AcpAdapter(command=f"{agent_id}-adapter", env={}, args=()),
        identity=AcpCandidateIdentity(
            display_name=key, candidate_key=key, availability_key=f"{agent_id}-account"
        ),
        agent_id=agent_id,
    )


def _chain(*, node: str, agents: tuple[str, ...]) -> ResolvedAcpChain:
    candidates = tuple(_candidate(agent_id=agent, key=f"{node}-{agent}") for agent in agents)
    return ResolvedAcpChain(
        node=node,
        primary=candidates[0],
        fallbacks=candidates[1:],
        enabled=True,
        primary_generation="primary",
        full_chain="chain",
        redacted={},
    )


def _codex_reading(**limits: object) -> codex.CodexHeadroomReading:
    return codex.codex_headroom_reading(
        credential_identity="codex-cred",
        observed_at=_NOW,
        response={
            "rate_limit": {
                "allowed": True,
                "limit_reached": False,
                "primary_window": {"used_percent": 10, "limit_window_seconds": 18000},
                **limits,
            }
        },
    )


def _policy(
    *, reading: codex.CodexHeadroomReading | None, calls: list[str], floor: int = 20
) -> headroom.SessionHeadroomPolicy:
    def _claude() -> headroom.SessionHeadroomReading:
        calls.append("claude")
        return headroom.session_headroom_reading(
            credential_identity="claude-cred", observed_at=_NOW, utilization=0
        )

    def _codex() -> codex.CodexHeadroomReading:
        calls.append("codex")
        assert reading is not None
        return reading

    return headroom.SessionHeadroomPolicy(
        floor_percent=floor,
        horizon_minutes=180,
        read=_claude,
        codex_read=None if reading is None else _codex,
    )


def _filter(*, policy: headroom.SessionHeadroomPolicy | None) -> preflight.NodePreflight:
    return preflight.filter_node_candidates(
        chain=_chain(node="implement", agents=(CODEX_AGENT_ID, CLAUDE_AGENT_ID)),
        inputs=preflight.PreflightInputs(headroom=policy),
        assessed={},
    )


def test_a_policy_carrying_no_codex_read_leaves_a_codex_candidate_unassessed() -> None:
    calls: list[str] = []

    node = _filter(policy=_policy(reading=None, calls=calls))

    assert [c.agent_id for c in node.candidates] == [CODEX_AGENT_ID, CLAUDE_AGENT_ID]
    assert node.codex_assessments == ()
    assert calls == ["claude"]


def test_no_policy_at_all_assesses_nothing() -> None:
    node = _filter(policy=None)

    assert [c.agent_id for c in node.candidates] == [CODEX_AGENT_ID, CLAUDE_AGENT_ID]
    assert node.assessments == ()
    assert node.codex_assessments == ()


def test_a_limit_reached_codex_account_selects_the_fallback() -> None:
    calls: list[str] = []

    node = _filter(policy=_policy(reading=_codex_reading(limit_reached=True), calls=calls))

    assert [c.agent_id for c in node.candidates] == [CLAUDE_AGENT_ID]
    skip = node.skipped[0]
    assert skip.reason == preflight.HEADROOM_SKIP
    assert skip.headroom_skip_kind == codex.CODEX_LIMIT_SKIP_KIND
    assert skip.headroom_floor_percent == 20
    assert skip.headroom_horizon_minutes == 180
    assert skip.cause is None
    assert skip.hold_key is None
    assert skip.condition is None


def test_a_window_below_the_floor_selects_the_fallback() -> None:
    primary = {"used_percent": 85, "limit_window_seconds": 18000}

    node = _filter(policy=_policy(reading=_codex_reading(primary_window=primary), calls=[]))

    assert [c.agent_id for c in node.candidates] == [CLAUDE_AGENT_ID]
    assert node.skipped[0].headroom_skip_kind == "floor"


def test_a_floor_of_zero_skips_nothing_but_still_records_the_reading() -> None:
    reading = _codex_reading(limit_reached=True)

    node = _filter(policy=_policy(reading=reading, calls=[], floor=0))

    assert [c.agent_id for c in node.candidates] == [CODEX_AGENT_ID, CLAUDE_AGENT_ID]
    assert node.codex_assessments == (reading,)


def test_a_reading_that_skips_nothing_is_still_recorded() -> None:
    reading = _codex_reading()

    node = _filter(policy=_policy(reading=reading, calls=[]))

    assert node.skipped == ()
    assert node.codex_assessments == (reading,)


def test_a_chain_without_a_codex_candidate_never_reads_the_codex_window() -> None:
    calls: list[str] = []

    node = preflight.filter_node_candidates(
        chain=_chain(node="implement", agents=(CLAUDE_AGENT_ID,)),
        inputs=preflight.PreflightInputs(headroom=_policy(reading=_codex_reading(), calls=calls)),
        assessed={},
    )

    assert calls == ["claude"]
    assert node.codex_assessments == ()


def test_the_verdict_carries_one_codex_row_per_credential_across_nodes() -> None:
    reading = _codex_reading()
    calls: list[str] = []
    verdict: Any = build_acp_preflight_verdict(
        chains={
            "implement": _chain(node="implement", agents=(CODEX_AGENT_ID, CLAUDE_AGENT_ID)),
            "review": _chain(node="review", agents=(CODEX_AGENT_ID, CLAUDE_AGENT_ID)),
        },
        graph_text=_GRAPH,
        ledger=read_acp_hold_ledger(journal_path=None, now_iso=_NOW),
        inputs=preflight.PreflightInputs(headroom=_policy(reading=reading, calls=calls)),
    )

    assert verdict.codex_headroom_assessments == (reading,)
    assert [r.credential_identity for r in verdict.headroom_assessments] == ["claude-cred"]
    assert verdict.session_headroom_floor_percent == 20
    assert calls.count("codex") == 2


def test_two_codex_candidates_sharing_a_reading_record_it_once() -> None:
    reading = _codex_reading()

    node = preflight.filter_node_candidates(
        chain=_chain(node="implement", agents=(CODEX_AGENT_ID, CODEX_AGENT_ID, CLAUDE_AGENT_ID)),
        inputs=preflight.PreflightInputs(headroom=_policy(reading=reading, calls=[])),
        assessed={},
    )

    assert node.codex_assessments == (reading,)
    assert len(node.candidates) == 3


def test_the_hermetic_admission_policy_reads_an_untouched_codex_window(
    tmp_path: Path,
) -> None:
    from livespec_orchestrator_beads_fabro.commands import _dispatcher_admission

    policy = _dispatcher_admission.session_headroom_policy(
        repo=tmp_path, now_iso=_NOW, journal_path=None
    )

    assert policy.codex_read is not None
    reading = policy.codex_read()
    assert reading.observable is True
    assert reading.governing_remaining_percent == 100.0
    assert codex.codex_headroom_skip_kind(reading=reading, floor_percent=20) is None
