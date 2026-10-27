"""A skipped Codex primary falls through, and the record names the provider.

Binds the second assertion of work-item `bd-ib-4jdgcw`'s Definition of Done,
and through it `SPECIFICATION/contracts.md` section "Provider spend
containment", paragraph "Admission filters Codex candidates by projected
usage-window headroom": "Every skip this clause defines has exactly the
semantics of a Claude floor skip: it is ephemeral and candidate-local to this
evaluation; per-node selection MUST continue in configured order to the next
eligible candidate ... The per-node selection record and any headroom-governed
refusal record MUST name each skip by its kind, distinguishing a Codex limit
skip, a floor skip, and a projection skip, and MUST name the provider as
`codex`."

`SPECIFICATION/scenarios.md` Scenario 243's first scenario -- "A Codex window
below the floor selects the fallback" -- is the governing scenario.

THE SELECTION IS READ OFF THE SURVIVOR, NOT OFF THE SKIP. A node that recorded
the skip while emptying its own chain satisfies every assertion about the skip
itself, so what makes this leg able to fail is the CLAUDE FALLBACK being the
candidate the selection renders -- at index 1, with the Codex primary in the
leading run it passed over.

THE PROVIDER IS ASSERTED BESIDE A CLAUDE SKIP IN THE SAME RECORD. One record
surface serves both clauses, so a build that hard-coded `codex` would satisfy a
Codex-only fixture while mislabelling every Claude skip in the repository, and
one that hard-coded `claude` would do the reverse. Only a record carrying one
of each can fail for the right reason, which is why the fixture gives two nodes
and reads both.

EACH OF THOSE TWO NODES FALLS BACK TO A MANUAL-FORM CANDIDATE, deliberately,
and getting this wrong is the first thing a reader should check. A policy holds
ONE memoized reading of ONE credential, so every candidate a policy covers
shares its verdict: a `claude-acp` fallback behind a Codex primary is skipped
by the same short Claude reading that skipped the Claude node's own primary,
which empties BOTH chains and the selection refuses rather than renders. An
uncovered candidate -- a manual-form adapter carrying an identity but no
resolved agent id -- is covered by neither clause, so each node has exactly one
skip and exactly one survivor, which is what makes the per-provider assertions
readings of one record rather than of a refusal. The literal "a Codex primary
reaches its CLAUDE fallback" is asserted separately below, on a node whose
evaluation supplies no Claude policy at all.

THE SKIP KIND IS ASSERTED AS `projection` RATHER THAN MERELY NON-NULL, because
a reading can sit below the floor AND project an exhaustion inside the horizon:
this fixture's window passes the floor with 40 points to spare, so `projection`
is the only kind that can be reported and a build defaulting to `floor` fails
here instead of agreeing by luck.
"""

from __future__ import annotations

import dataclasses

from livespec_orchestrator_beads_fabro.commands import _acp_candidate_preflight as preflight
from livespec_orchestrator_beads_fabro.commands import (
    _acp_codex_headroom_projection as codex_projection,
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
from livespec_orchestrator_beads_fabro.commands._acp_hold_ledger import AcpHoldLedger
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import AcpAdapter
from livespec_orchestrator_beads_fabro.commands._acp_node_selection import (
    acp_node_selection_record,
    select_acp_candidates,
)
from livespec_orchestrator_beads_fabro.commands._acp_preflight_verdict import (
    build_acp_preflight_verdict,
)
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom import (
    SessionHeadroomPolicy,
    session_headroom_reading,
)

_OBSERVED_AT = "2026-10-27T12:00:00Z"
_BASELINE_AT = "2026-10-27T11:00:00Z"
_FIVE_HOURS = 18000

# No typed availability record stands, so the only filter that can act here is
# this clause's own -- which is what makes every skip below evidence about it.
_EMPTY_LEDGER = AcpHoldLedger(holds=(), unobservable=(), observation_ids=frozenset())

# Two ACP nodes in series between the one start and the one green terminal, so
# both dominate the green terminal and are therefore admission-required.
_GRAPH = (
    "digraph ImplementWorkItem {\n"
    '    start [shape=Mdiamond, label="Start"]\n'
    '    exit  [shape=Msquare, label="Exit"]\n'
    '    implement [backend="acp", acp.command="npx -y claude-acp"]\n'
    '    codex_node [backend="acp", acp.command="npx -y codex-acp"]\n'
    "    start -> implement\n"
    "    implement -> codex_node\n"
    "    codex_node -> exit\n"
    "}\n"
)


def _candidate(*, agent_id: str | None, key: str) -> AcpCandidate:
    return AcpCandidate(
        adapter=AcpAdapter(command="/usr/bin/true"),
        identity=AcpCandidateIdentity(display_name=key, candidate_key=key, availability_key=key),
        agent_id=agent_id,
    )


def _chain(*, node: str, primary: AcpCandidate, fallback: AcpCandidate) -> ResolvedAcpChain:
    return ResolvedAcpChain(
        node=node,
        primary=primary,
        fallbacks=(fallback,),
        enabled=True,
        primary_generation=f"primary-{node}",
        full_chain=f"chain-{node}",
        redacted={},
    )


def _codex_policy() -> object:
    """A policy whose ONE reading projects exhaustion inside the horizon.

    60 percent used leaves 40 points, well above the floor of 20, draining 30
    points an hour against a baseline taken an hour earlier -- so the window
    empties 80 minutes out, inside the 180-minute horizon. The floor therefore
    cannot be the kind that fires.
    """
    codex = __import__(
        "livespec_orchestrator_beads_fabro.commands._acp_codex_headroom",
        fromlist=["codex_usage_reading"],
    )
    drain = __import__(
        "livespec_orchestrator_beads_fabro.commands._acp_session_headroom_drain",
        fromlist=["SessionHeadroomBaseline"],
    )
    reading = codex.codex_usage_reading(
        credential_identity="codex-pool",
        observed_at=_OBSERVED_AT,
        rate_limit={
            "allowed": True,
            "limit_reached": False,
            "primary_window": {"used_percent": 60, "limit_window_seconds": _FIVE_HOURS},
        },
    )
    projected = codex_projection.reading_with_codex_projections(
        reading=reading,
        projections=codex_projection.codex_window_projections(
            reading=reading,
            baselines={
                _FIVE_HOURS: drain.SessionHeadroomBaseline(
                    utilization_percent=30.0, observed_at=_BASELINE_AT, elapsed_hours=1.0
                )
            },
            floor_percent=20,
            horizon_minutes=180,
        ),
    )
    assert codex_projection.codex_projection_skips_candidate(reading=projected)
    return codex.CodexHeadroomPolicy(floor_percent=20, horizon_minutes=180, read=lambda: projected)


def _claude_policy() -> SessionHeadroomPolicy:
    """A Claude policy whose reading is short of the floor, for the control."""
    reading = session_headroom_reading(
        credential_identity="claude-pool", observed_at=_OBSERVED_AT, utilization=95.0
    )
    return SessionHeadroomPolicy(floor_percent=20, horizon_minutes=180, read=lambda: reading)


def test_preflight_inputs_carry_a_codex_headroom_policy() -> None:
    """The filter has a seam this clause's reading can arrive through."""
    names = {field.name for field in dataclasses.fields(preflight.PreflightInputs)}
    assert "codex_headroom" in names


def test_a_skipped_codex_primary_selects_the_claude_fallback() -> None:
    """Per-node selection continues in configured order to the next eligible."""
    codex_primary = _candidate(agent_id=CODEX_AGENT_ID, key="codex-pool")
    claude_fallback = _candidate(agent_id=CLAUDE_AGENT_ID, key="claude-fallback")
    chain = _chain(node="codex_node", primary=codex_primary, fallback=claude_fallback)
    node = preflight.filter_node_candidates(
        chain=chain,
        inputs=preflight.PreflightInputs(codex_headroom=_codex_policy()),
        assessed={},
    )
    assert [one.identity.candidate_key for one in node.candidates if one.identity] == [
        "claude-fallback"
    ]
    assert [one.candidate_key for one in node.skipped] == ["codex-pool"]
    skip = node.skipped[0]
    assert skip.reason == preflight.HEADROOM_SKIP
    assert skip.headroom_skip_kind == codex_projection.PROJECTION_SKIP_KIND
    assert skip.headroom_provider == "codex"
    assert skip.headroom_floor_percent == 20
    assert skip.headroom_horizon_minutes == 180
    assert skip.codex_headroom is not None
    assert skip.codex_headroom.credential_identity == "codex-pool"
    assert skip.headroom is None


def test_an_uncovered_candidate_is_never_assessed_by_this_clause() -> None:
    """A `claude-acp` primary survives a Codex policy untouched."""
    chain = _chain(
        node="implement",
        primary=_candidate(agent_id=CLAUDE_AGENT_ID, key="claude-primary"),
        fallback=_candidate(agent_id=CLAUDE_AGENT_ID, key="claude-fallback"),
    )
    node = preflight.filter_node_candidates(
        chain=chain,
        inputs=preflight.PreflightInputs(codex_headroom=_codex_policy()),
        assessed={},
    )
    assert node.skipped == ()
    assert node.codex_assessments == ()


def _two_provider_selections() -> dict[str, object]:
    """One `acp-node-selection` record carrying one skip of EACH provider.

    Both nodes in ONE record, which is what makes the provider assertions able
    to fail: a build that hard-coded either spelling satisfies a fixture
    carrying only the other one.
    """
    chains = {
        "implement": _chain(
            node="implement",
            primary=_candidate(agent_id=CLAUDE_AGENT_ID, key="claude-pool"),
            fallback=_candidate(agent_id=None, key="manual-implement"),
        ),
        "codex_node": _chain(
            node="codex_node",
            primary=_candidate(agent_id=CODEX_AGENT_ID, key="codex-pool"),
            fallback=_candidate(agent_id=None, key="manual-codex"),
        ),
    }
    verdict = build_acp_preflight_verdict(
        chains=chains,
        graph_text=_GRAPH,
        ledger=_EMPTY_LEDGER,
        inputs=preflight.PreflightInputs(codex_headroom=_codex_policy(), headroom=_claude_policy()),
    )
    selected = select_acp_candidates(chains=chains, verdict=verdict)
    assert not isinstance(selected, str)
    selections = acp_node_selection_record(selected=selected, dispatch_id="d1")["selections"]
    assert isinstance(selections, dict)
    return selections


def _one_headroom_skip(*, selections: dict[str, object], node: str) -> dict[str, object]:
    """The ONE headroom skip the record reports for one node."""
    selection = selections[node]
    assert isinstance(selection, dict)
    skips = selection["headroom_skips"]
    assert isinstance(skips, list)
    assert len(skips) == 1
    assert isinstance(skips[0], dict)
    return skips[0]


def test_the_selection_record_names_the_codex_skip_by_provider_and_kind() -> None:
    """The Codex entry names `codex`, its kind, and the window it was read on."""
    selections = _two_provider_selections()
    selection = selections["codex_node"]
    assert isinstance(selection, dict)
    assert selection["selected_candidate_key"] == "manual-codex"
    assert selection["selected_index"] == 1
    skip = _one_headroom_skip(selections=selections, node="codex_node")
    assert skip["provider"] == "codex"
    assert skip["candidate_key"] == "codex-pool"
    assert skip["headroom_skip_kind"] == codex_projection.PROJECTION_SKIP_KIND
    assert skip["headroom"] is None
    usage = skip["codex_usage"]
    assert isinstance(usage, dict)
    assert usage["credential_identity"] == "codex-pool"
    assert usage["allowed"] is True
    assert usage["limit_reached"] is False
    windows = usage["windows"]
    assert isinstance(windows, list)
    assert windows[0]["limit_window_seconds"] == _FIVE_HOURS
    assert windows[0]["remaining_percent"] == 40.0


def test_the_same_record_still_names_a_claude_skip_as_claude() -> None:
    """The control: one record surface serves both clauses without conflating them."""
    skip = _one_headroom_skip(selections=_two_provider_selections(), node="implement")
    assert skip["provider"] == "claude"
    assert skip["candidate_key"] == "claude-pool"
    assert skip["codex_usage"] is None
    assert skip["headroom"] is not None


def test_the_verdict_carries_the_codex_assessments_it_took() -> None:
    """One reading per distinct credential, reported for the journal to record."""
    chains = {
        "codex_node": _chain(
            node="codex_node",
            primary=_candidate(agent_id=CODEX_AGENT_ID, key="codex-pool"),
            fallback=_candidate(agent_id=CLAUDE_AGENT_ID, key="claude-fallback"),
        ),
    }
    verdict = build_acp_preflight_verdict(
        chains=chains,
        graph_text=_GRAPH,
        ledger=_EMPTY_LEDGER,
        inputs=preflight.PreflightInputs(codex_headroom=_codex_policy()),
    )
    assert [one.credential_identity for one in verdict.codex_headroom_assessments] == ["codex-pool"]
    assert verdict.session_headroom_floor_percent == 20
    assert verdict.session_headroom_horizon_minutes == 180
