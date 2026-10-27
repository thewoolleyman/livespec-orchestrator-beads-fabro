"""A healthy Codex window is ADMITTED, and its reading is journaled anyway.

Sibling of `test_acp_codex_headroom_selection_record.py`, which binds the
SKIPPING half of work-item `bd-ib-4jdgcw`'s second assertion. This module owns
the two things a skipping fixture cannot observe, and both are sentences of
`SPECIFICATION/contracts.md` section "Provider spend containment", paragraph
"Admission filters Codex candidates by projected usage-window headroom":

THE ADMITTED CASE IS STILL JOURNALED. "a floor of 0 disables every skip this
clause defines while retaining the bounded read and its journal record", and
the journal requirement itself is "For each affected work-item and assessed
Codex credential" rather than for each refused one. A filter that recorded the
reading only on its refusing arm would leave the journal silent on exactly the
dispatches that went through -- and silent is what a credential nobody assessed
looks like, so the drain rate of the next evaluation would have no baseline to
measure against. This is the positive control for every absence the sibling
module asserts: without it, a filter that assessed NOTHING would satisfy them
all.

ONE READING IS REUSED ACROSS NODES. "MUST reuse that one reading across every
node and candidate sharing the credential", which is a claim about a COUNT and
therefore unobservable from any one node: two nodes filtered from one policy
must contribute ONE assessment, not one each. It is read off the verdict's own
deduplicated tuple AND off the policy's call count, because the two fail
separately -- a policy read twice that happened to return an equal value would
satisfy the first and not the second.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands import _acp_candidate_preflight as preflight
from livespec_orchestrator_beads_fabro.commands._acp_agent_catalog import CODEX_AGENT_ID
from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import (
    AcpCandidate,
    AcpCandidateIdentity,
)
from livespec_orchestrator_beads_fabro.commands._acp_chain_resolution import ResolvedAcpChain
from livespec_orchestrator_beads_fabro.commands._acp_codex_headroom import (
    CodexHeadroomPolicy,
    CodexUsageReading,
    codex_usage_reading,
)
from livespec_orchestrator_beads_fabro.commands._acp_hold_ledger import AcpHoldLedger
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import AcpAdapter
from livespec_orchestrator_beads_fabro.commands._acp_preflight_verdict import (
    build_acp_preflight_verdict,
)

_OBSERVED_AT = "2026-10-27T12:00:00Z"
_FIVE_HOURS = 18000
_EMPTY_LEDGER = AcpHoldLedger(holds=(), unobservable=(), observation_ids=frozenset())

_GRAPH = (
    "digraph ImplementWorkItem {\n"
    '    start [shape=Mdiamond, label="Start"]\n'
    '    exit  [shape=Msquare, label="Exit"]\n'
    '    implement [backend="acp", acp.command="npx -y codex-acp"]\n'
    '    review [backend="acp", acp.command="npx -y codex-acp"]\n'
    "    start -> implement\n"
    "    implement -> review\n"
    "    review -> exit\n"
    "}\n"
)


def _candidate(*, key: str) -> AcpCandidate:
    return AcpCandidate(
        adapter=AcpAdapter(command="/usr/bin/true"),
        identity=AcpCandidateIdentity(display_name=key, candidate_key=key, availability_key=key),
        agent_id=CODEX_AGENT_ID,
    )


def _chain(*, node: str, key: str) -> ResolvedAcpChain:
    return ResolvedAcpChain(
        node=node,
        primary=_candidate(key=key),
        fallbacks=(),
        enabled=True,
        primary_generation=f"primary-{node}",
        full_chain=f"chain-{node}",
        redacted={},
    )


def _healthy_reading() -> CodexUsageReading:
    """90 points of headroom, the provider serving, and no projection attached.

    No projection is attached deliberately: a reading the gate never projected
    carries none, which is the state every surface that composes a verdict
    without a journal produces -- and `codex_projection_skips_candidate` must
    answer `False` for it rather than treating an absent projection as a
    refusal.
    """
    return codex_usage_reading(
        credential_identity="codex-pool",
        observed_at=_OBSERVED_AT,
        rate_limit={
            "allowed": True,
            "limit_reached": False,
            "primary_window": {"used_percent": 10, "limit_window_seconds": _FIVE_HOURS},
        },
    )


def test_a_healthy_codex_window_is_admitted_and_still_assessed() -> None:
    """The candidate survives, and its reading is reported for the journal."""
    reading = _healthy_reading()
    node = preflight.filter_node_candidates(
        chain=_chain(node="implement", key="codex-pool"),
        inputs=preflight.PreflightInputs(
            codex_headroom=CodexHeadroomPolicy(
                floor_percent=20, horizon_minutes=180, read=lambda: reading
            )
        ),
        assessed={},
    )
    assert [one.identity.candidate_key for one in node.candidates if one.identity] == ["codex-pool"]
    assert node.skipped == ()
    assert node.codex_assessments == (reading,)


def test_two_nodes_sharing_one_credential_are_assessed_once() -> None:
    """One bounded read per credential per evaluation, however many nodes use it."""
    reading = _healthy_reading()
    reads: list[int] = []

    def read() -> CodexUsageReading:
        reads.append(1)
        return reading

    verdict = build_acp_preflight_verdict(
        chains={
            "implement": _chain(node="implement", key="codex-pool"),
            "review": _chain(node="review", key="codex-pool"),
        },
        graph_text=_GRAPH,
        ledger=_EMPTY_LEDGER,
        inputs=preflight.PreflightInputs(
            codex_headroom=CodexHeadroomPolicy(floor_percent=20, horizon_minutes=180, read=read)
        ),
    )
    assert verdict.codex_headroom_assessments == (reading,)
    assert sum(reads) == 2
    assert verdict.exhausted == ()


def test_one_node_whose_two_candidates_share_a_credential_records_one_reading() -> None:
    """The in-node memo: a reading already recorded is not recorded twice.

    Read off the NODE rather than off the verdict, because the verdict
    deduplicates by credential identity on its own -- so a filter that appended
    the same reading once per candidate would still report one row there, and
    the only surface that can show the duplication is the node's own tuple.
    """
    reading = _healthy_reading()
    chain = ResolvedAcpChain(
        node="implement",
        primary=_candidate(key="codex-pool"),
        fallbacks=(_candidate(key="codex-pool-second-model"),),
        enabled=True,
        primary_generation="primary",
        full_chain="chain",
        redacted={},
    )
    node = preflight.filter_node_candidates(
        chain=chain,
        inputs=preflight.PreflightInputs(
            codex_headroom=CodexHeadroomPolicy(
                floor_percent=20, horizon_minutes=180, read=lambda: reading
            )
        ),
        assessed={},
    )
    assert len(node.candidates) == 2
    assert node.codex_assessments == (reading,)
