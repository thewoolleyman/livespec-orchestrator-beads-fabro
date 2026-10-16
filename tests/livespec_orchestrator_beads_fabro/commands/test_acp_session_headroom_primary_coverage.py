"""A node's PRIMARY carries its resolved agent id, so this clause is not inert.

Binds the coverage half of the "Admission filters candidates by projected Claude
session headroom" paragraph of `SPECIFICATION/contracts.md` section "Dispatcher
admission, WIP cap, and post-merge acceptance" at the place it is easiest to
satisfy on paper and miss in production: "a covered candidate is a structured
candidate whose resolved agent id is `claude-acp`".

WHY THIS FILE EXISTS AT ALL, recorded because the gap it closes produced a
clean, plausible, entirely wrong green. A node's FALLBACK candidates are parsed
as candidates, so each one carries the agent entry it resolved through. The
node's PRIMARY is not: `attach_acp_chains` rebuilds it from the already-resolved
adapter plus the chain's identity, so a coverage predicate reading the agent id
saw `None` on every primary. Measured against this repository's own committed
routing on 2026-10-14, every one of its eight ACP nodes resolves to a
`claude-acp` primary and the headroom filter took ZERO readings -- a feature
that passed every unit test while assessing nothing the factory actually runs.

THE LIVE CONTROL IS THE LOAD-BEARING ONE, and it is pointed at this
repository's committed configuration rather than at a fixture. A fixture proves
the attach path carries the field; only the live resolution proves the field
survives the whole layer stack this repository's dispatches go through. Its
first assertion establishes that the routing under test is still Claude, so a
re-route to another provider fails here loudly instead of making the rest of
the case vacuous.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import _acp_candidate_preflight as preflight
from livespec_orchestrator_beads_fabro.commands import _acp_session_headroom as headroom
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_session_headroom_gate as headroom_gate,
)
from livespec_orchestrator_beads_fabro.commands._acp_agent_catalog import CLAUDE_AGENT_ID
from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidateIdentity
from livespec_orchestrator_beads_fabro.commands._acp_catalogs import resolve_acp_catalogs
from livespec_orchestrator_beads_fabro.commands._acp_chain_resolution import attach_acp_chains
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import AcpAdapter
from livespec_orchestrator_beads_fabro.commands._acp_node_chains import parse_node_chains
from livespec_orchestrator_beads_fabro.commands._acp_node_layers import (
    AcpNodeResolution,
    ResolvedAcpNode,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_preflight import (
    resolve_acp_preflight,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_NOW = "2026-10-14T12:00:00Z"
_FLOOR = 20

# A structured node entry in the ratified grammar, naming the built-in Claude
# agent. Its rendered adapter is irrelevant here: what is under test is whether
# the agent it resolved THROUGH survives onto the rebuilt primary.
_STRUCTURED_NODE = {
    "implement": {"agent": CLAUDE_AGENT_ID, "model": "anthropic/claude-opus-5"},
}


def _resolution(*, rendered: str) -> AcpNodeResolution:
    adapter = AcpAdapter(command=rendered, env={}, args=())
    return AcpNodeResolution(
        nodes={
            "implement": ResolvedAcpNode(
                adapter=adapter, command_layer="repository", args_layer="repository", env_layers={}
            )
        },
        inputs={"implement": "implement_acp"},
        run_inputs=(),
    )


def _attached(*, builtins: dict[str, AcpCandidateIdentity]) -> Any:
    catalogs = resolve_acp_catalogs(block={})
    assert not isinstance(catalogs, str)
    chains = parse_node_chains(
        table=_STRUCTURED_NODE, key_prefix="dispatcher.acp_nodes", catalogs=catalogs
    )
    assert not isinstance(chains, str)
    attached = attach_acp_chains(
        resolution=_resolution(rendered="some-resolved-adapter"),
        chains=chains,
        dispatch={},
        builtins=builtins,
    )
    assert not isinstance(attached, str)
    return attached


def test_a_structured_node_entry_carries_its_agent_id_onto_the_rebuilt_primary() -> None:
    """The attach path: the primary is rebuilt, and the provenance survives it."""
    attached = _attached(builtins={})

    primary = attached.chains["implement"].primary
    assert primary.agent_id == CLAUDE_AGENT_ID
    assert headroom.headroom_covers_candidate(candidate=primary, builtin_pairs=frozenset()) is True


def test_this_repositorys_own_claude_routing_is_assessed_by_the_filter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The live control that caught the gap, kept as a standing one.

    Every success-critical node of this repository resolves to a `claude-acp`
    primary today, so a below-floor reading must empty every one of them and
    the whole chain set must be refused.

    THE POLICY IS BUILT BY THE PRODUCTION BUILDER, with only the provider read
    injected, and the count of provider reads is asserted across all eight
    nodes. That composition is the claim: the filter asks per covered
    candidate, and the clause's "One assessment per distinct projected
    credential per admission evaluation" is the BUILDER's memo. A
    hand-constructed policy here would assert the stand-in's own memoization
    and say nothing about the pair that runs in production.
    """
    reads: list[str | None] = []
    reading = headroom.session_headroom_reading(
        credential_identity="cred-1", observed_at=_NOW, utilization=95
    )

    def counting_read(*, token: str | None, observed_at: str) -> headroom.SessionHeadroomReading:
        _ = observed_at
        reads.append(token)
        return reading

    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "projected-token")
    # `tmp_path` declares no floor, so the builder resolves the RATIFIED default
    # -- which is the governing floor for every repository that has not set the
    # dial, and therefore the one this control should be measuring against.
    assert headroom.DEFAULT_SESSION_HEADROOM_FLOOR_PERCENT == _FLOOR
    verdict = resolve_acp_preflight(
        repo=_REPO_ROOT,
        journal_path=None,
        now_iso=_NOW,
        headroom=headroom_gate.session_headroom_policy(
            repo=tmp_path, now_iso=_NOW, journal_path=None, read=counting_read
        ),
    )

    # The routing under test, established rather than assumed: a re-route to a
    # provider outside this clause must fail HERE, not by making the
    # assertions below vacuously true.
    assert verdict.fallback_enabled is True
    assert all(
        node.candidates == () or node.skipped != () for node in verdict.nodes
    ), "this repository must still route its ACP nodes to Claude"

    assert reads == ["projected-token"]
    assert [reading.credential_identity for reading in verdict.headroom_assessments] == ["cred-1"]
    assert set(verdict.exhausted) == set(verdict.success_critical)
    assert verdict.viable is False
    assert all(
        skip.reason == preflight.HEADROOM_SKIP for node in verdict.nodes for skip in node.skipped
    )


def test_an_above_floor_reading_leaves_this_repositorys_routing_admissible() -> None:
    """The positive control: the filter is a filter, not a blanket refusal."""
    reading = headroom.session_headroom_reading(
        credential_identity="cred-1", observed_at=_NOW, utilization=5
    )

    verdict = resolve_acp_preflight(
        repo=_REPO_ROOT,
        journal_path=None,
        now_iso=_NOW,
        headroom=headroom.SessionHeadroomPolicy(floor_percent=_FLOOR, read=lambda: reading),
    )

    assert verdict.viable is True
    assert verdict.exhausted == ()
    assert [reading.remaining_percent for reading in verdict.headroom_assessments] == [95.0]
