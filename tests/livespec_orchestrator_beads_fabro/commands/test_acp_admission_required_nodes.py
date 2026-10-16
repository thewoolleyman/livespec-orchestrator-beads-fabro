"""The ADMISSION-REQUIRED node set is wider than the dominator set.

Binds `SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": "The admission-required set is wider: every ACP node potentially
reachable in the submitted graph is admission-required, success-critical or
not. Before submission, every ACP node potentially reachable in the submitted
graph MUST have an eligible candidate. A node proven unreachable in that graph
imposes no candidate requirement." Scenario 169's neighbours in
`SPECIFICATION/scenarios.md` -- "Admission requires an eligible candidate for
every potentially reachable ACP node" and "A conditional node with every
candidate held causes a ready wait without adapter execution" -- are the
scenarios that govern it.

THE TWO SETS ARE ASSERTED TOGETHER, AND THAT PAIRING IS THE CONTROL. Widening
what admission grades is one edit away from widening what
`derive_success_critical` returns, and both wrong answers are individually
plausible: a dominator derivation that started returning the reachable set
would satisfy every admission assertion here while silently changing what the
per-node selection record and the `success_critical` journal field mean. So the
dominator set is re-asserted against the committed graph in the same module
that asserts the wider set, with the two expected values spelled out
separately.

THE UNREACHABLE ARM IS THE OTHER HALF OF THE CLAIM. "Potentially reachable" is
not "declared": a graph carrying an ACP node nothing points at must impose no
candidate requirement, and an implementation that simply graded every declared
ACP node would pass each reachable-node assertion above while refusing
dispatch over a node no run can ever visit.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_WORKFLOW_GRAPH = (
    _REPO_ROOT
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "workflow.fabro"
)

# One start, one green terminal, one ACP node dominating it (`implement`) and
# one conditional ACP node that dominates nothing (`fix`) -- the shape the
# dominator derivation and the reachability derivation disagree about.
_MINIMAL_GRAPH = """
    graph [stall_timeout="7200s"]
    start [shape=Mdiamond, label="Start"]
    exit  [shape=Msquare, label="Exit"]
    implement [backend="acp", acp.command="a", timeout="60s"]
    fix [backend="acp", acp.command="b", timeout="60s"]
    gate [shape=parallelogram, timeout="60s"]
    start -> implement
    implement -> gate
    gate -> exit [label="green", condition="outcome=succeeded"]
    gate -> fix [label="red"]
    fix -> gate
"""

# The same graph plus an ACP node no edge reaches. `orphan` is declared, runs
# an adapter, and no run can visit it.
_ORPHAN_GRAPH = _MINIMAL_GRAPH + '    orphan [backend="acp", acp.command="c"]\n'

_NOW = "2026-10-15T12:00:00Z"


def _module(*, name: str) -> Any:
    return importlib.import_module(f"{_PACKAGE}.{name}")


def _candidate(*, availability_key: str | None = "codex", candidate_key: str = "only") -> Any:
    schema = _module(name="_acp_candidate_schema")
    adapters = _module(name="_acp_node_adapters")
    identity = (
        None
        if availability_key is None
        else schema.AcpCandidateIdentity(
            display_name=f"{availability_key}/{candidate_key}",
            candidate_key=candidate_key,
            availability_key=availability_key,
        )
    )
    return schema.AcpCandidate(
        adapter=adapters.AcpAdapter(command="adapter", env={}, args=()),
        identity=identity,
        signatures=(),
    )


def _chain(*, node: str, candidates: tuple[Any, ...]) -> Any:
    resolution = _module(name="_acp_chain_resolution")
    return resolution.ResolvedAcpChain(
        node=node,
        primary=candidates[0],
        fallbacks=tuple(candidates[1:]),
        enabled=True,
        primary_generation="primary-digest",
        full_chain="chain-digest",
        redacted={},
    )


def _hold(*, hold_key: str = "codex") -> Any:
    records = _module(name="_acp_hold_records")
    return records.AcpAvailabilityHold(
        schema_version=1,
        observation_id="obs-1",
        scope="availability-domain",
        hold_key=hold_key,
        candidate_key=None,
        cause="quota",
        occurred_at=_NOW,
        expires_at="2026-10-15T13:00:00Z",
    )


def _ledger(*, holds: tuple[Any, ...] = ()) -> Any:
    ledger = _module(name="_acp_hold_ledger")
    return ledger.AcpHoldLedger(holds=holds, unobservable=(), observation_ids=frozenset())


def _verdict(*, graph_text: str, chains: dict[str, Any], holds: tuple[Any, ...]) -> Any:
    preflight = _module(name="_acp_candidate_preflight")
    return _module(name="_acp_preflight_verdict").build_acp_preflight_verdict(
        chains=chains,
        graph_text=graph_text,
        ledger=_ledger(holds=holds),
        inputs=preflight.PreflightInputs(holds=holds),
    )


def _graph(*, text: str) -> Any:
    return _module(name="_acp_workflow_graph").parse_workflow_graph(text=text)


def test_an_exhausted_conditional_node_makes_the_verdict_refuse() -> None:
    """The v127 widening, at the one surface that decides a dispatch.

    `fix` dominates no green path, so a run that never goes Red reaches `exit`
    without it -- which is exactly why it is NOT success-critical. It is still
    admission-required, because the Dispatcher "MUST NOT render or start a
    candidate covered by a live hold, including for conditional repair or
    adjudication nodes": a held `fix` cannot be rendered, so a run that DOES go
    Red has nowhere to go.
    """
    held = (_hold(),)
    verdict = _verdict(
        graph_text=_MINIMAL_GRAPH,
        chains={
            "implement": _chain(
                node="implement",
                candidates=(_candidate(availability_key="anthropic", candidate_key="ok"),),
            ),
            "fix": _chain(node="fix", candidates=(_candidate(candidate_key="held"),)),
        },
        holds=held,
    )

    assert verdict.viable is False
    assert verdict.exhausted == ("fix",)
    assert set(getattr(verdict, "admission_required", ())) == {"implement", "fix"}
    # The dominator set is unchanged and still rides the verdict, so the
    # per-node selection record keeps reporting the narrower fact it names.
    assert verdict.success_critical == ("implement",)


def test_the_refusal_detail_names_the_admission_required_nodes() -> None:
    """The deterministic explanation reports the set it actually graded."""
    held = (_hold(),)
    verdict = _verdict(
        graph_text=_MINIMAL_GRAPH,
        chains={"fix": _chain(node="fix", candidates=(_candidate(candidate_key="held"),))},
        holds=held,
    )

    assert verdict.detail == "no candidate remains for admission-required ACP node fix"


def test_the_committed_graph_requires_every_reachable_acp_node() -> None:
    """All eight of this repository's ACP nodes, conditional ones included.

    `fix`, `review_fix` and `disposition` are the three the dominator
    derivation leaves out, and they are precisely the conditional repair and
    adjudication nodes the clause names.
    """
    module = _module(name="_acp_success_critical")
    assert hasattr(
        module, "derive_admission_required"
    ), "derive_admission_required is not implemented yet"
    graph = _graph(text=_WORKFLOW_GRAPH.read_text(encoding="utf-8"))

    assert set(module.derive_admission_required(graph=graph, start="start")) == {
        "disposition",
        "dod_gate",
        "fix",
        "implement",
        "proof_capture",
        "proof_verify",
        "review",
        "review_fix",
    }


def test_derive_success_critical_still_returns_the_dominator_set() -> None:
    """The paired control: the wider set did not displace the narrower one."""
    module = _module(name="_acp_success_critical")
    graph = _graph(text=_WORKFLOW_GRAPH.read_text(encoding="utf-8"))
    critical = module.derive_success_critical(graph=graph)

    assert set(critical.nodes) == {
        "dod_gate",
        "implement",
        "proof_capture",
        "proof_verify",
        "review",
    }
    assert critical.start == "start"
    assert critical.green_terminal == "exit"


def test_an_unreachable_acp_node_imposes_no_candidate_requirement() -> None:
    """ "A node proven unreachable in that graph imposes no candidate requirement."""
    module = _module(name="_acp_success_critical")
    assert hasattr(
        module, "derive_admission_required"
    ), "derive_admission_required is not implemented yet"
    graph = _graph(text=_ORPHAN_GRAPH)

    assert "orphan" in graph.acp_names
    assert module.derive_admission_required(graph=graph, start="start") == ("implement", "fix")


def test_an_exhausted_unreachable_node_does_not_refuse_the_verdict() -> None:
    """The same claim one level up: the verdict grades reachability, not declaration."""
    held = (_hold(),)
    verdict = _verdict(
        graph_text=_ORPHAN_GRAPH,
        chains={
            "implement": _chain(
                node="implement",
                candidates=(_candidate(availability_key="anthropic", candidate_key="ok"),),
            ),
            "orphan": _chain(node="orphan", candidates=(_candidate(candidate_key="held"),)),
        },
        holds=held,
    )

    assert verdict.node_preflight(node="orphan").exhausted is True
    assert verdict.exhausted == ()
    assert verdict.viable is True
