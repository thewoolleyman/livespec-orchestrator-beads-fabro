"""Scenario 131 — the Definition-of-Done gate node, ahead of any implementation spend.

Binds the `SPECIFICATION/contracts.md` requirement (ratified v114) that the
reserved `implement-work-item` workflow carries a `dod_gate` ACP node as the
first node after `start` and before `implement`, selecting its adapter through
its own `dod_gate_adapter` input, and named in that file's per-node timeout
table, its ACP-node list, and its built-in-defaults table.

WHY THE EDGE SHAPE IS ASSERTED AND NOT JUST THE NODE. Inserting a node ahead of
`implement` CONSUMES `start`'s own fallthrough, and a node whose every outgoing
edge carries a condition is rejected by the engine's `all_conditional_edges`
rule — the defect that took the whole factory down twice (`dev-tooling/checks/
fabro_graph_validity.py` records both outages). So the exceptional route is
named by condition and the ordinary route is the unconditional fallthrough that
conditional edges outrank, exactly as `implement -> implementation_diff ->
dead_implementer` already does.

THE REGISTERED VARIANT IS READ TOO, because the same file's peer clause holds a
registered variant to the reserved workflow's ACP node names so the adapter
layer and the timeout table resolve against it without naming an absent node,
while permitting a groom-kind variant to leave `dod_gate` unreached by its
edges. Parity is a relation between two payloads, so the variant is compared
against the BUNDLE rather than against a list restated here (the same discipline
`test_groom_workflow_variant_registration` uses).
"""

from __future__ import annotations

import re
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import (
    ACP_NODES,
    NODE_INPUT_CANDIDATES,
)
from livespec_orchestrator_beads_fabro.commands._acp_success_critical import (
    derive_success_critical,
)
from livespec_orchestrator_beads_fabro.commands._acp_workflow_graph import parse_workflow_graph
from livespec_orchestrator_beads_fabro.commands._node_timeouts import (
    DEFAULT_FABRO_TIMEOUT_SECONDS,
    default_node_timeouts,
    derive_fabro_timeout_seconds,
    node_timeouts_from_block,
)

_BUNDLE = Path(".claude-plugin/.fabro/workflows/implement-work-item")
_VARIANT = Path(".fabro/workflows/groom-work-item")
_GATE = "dod_gate"
_ADAPTER_INPUT = "dod_gate_adapter"
_ACP_BACKEND = 'backend="acp"'
# A DOT node declaration: a name at the start of a line followed by its
# attribute block. An edge line cannot match — the `^`-anchored name must be
# followed by the bracket with only whitespace between it, and an edge has its
# arrow and target there instead.
_NODE_DECLARATION = re.compile(r"(?m)^[ \t]*(?P<node>\w+)[ \t]*\[(?P<attrs>[^\]]*)\]")


def _dot(*, payload: Path) -> str:
    graph = payload / "workflow.fabro"
    assert graph.is_file(), graph
    return graph.read_text(encoding="utf-8")


def _toml(*, payload: Path) -> str:
    return (payload / "workflow.toml").read_text(encoding="utf-8")


def _node_body(*, text: str, node: str) -> str | None:
    """One node block's body, or `None` when the graph declares no such node."""
    match = re.search(rf"^\s*{node}\s*\[(?P<body>.*?)^\s*\]", text, re.DOTALL | re.MULTILINE)
    return None if match is None else match.group("body")


def _edges(*, text: str) -> list[str]:
    """Every edge line, comments stripped, so a commented example cannot match."""
    return [
        line.strip()
        for line in text.splitlines()
        if "->" in line and not line.strip().startswith("//")
    ]


def _acp_node_names(*, payload: Path) -> set[str]:
    """Every node in one payload's graph the adapter layer has to address."""
    return {
        match.group("node")
        for match in _NODE_DECLARATION.finditer(_dot(payload=payload))
        if _ACP_BACKEND in match.group("attrs")
    }


def test_the_gate_is_an_acp_node_on_its_own_adapter_input() -> None:
    """`dod_gate` is an ACP node whose adapter rides `inputs.dod_gate_adapter`."""
    body = _node_body(text=_dot(payload=_BUNDLE), node=_GATE)

    assert body is not None, "the reserved workflow declares no dod_gate node"
    assert _ACP_BACKEND in body
    assert 'acp.command="{{ inputs.' + _ADAPTER_INPUT + ' }}"' in body
    assert 'prompt="@prompts/dod-gate.md"' in body
    assert (_BUNDLE / "prompts" / "dod-gate.md").is_file()


def test_the_gate_sits_between_start_and_implement() -> None:
    """`start` enters the gate, and nothing enters `implement` from `start` any more."""
    edges = _edges(text=_dot(payload=_BUNDLE))

    assert [edge for edge in edges if edge.startswith("start ->")] == [f"start -> {_GATE}"]
    assert not any(edge.startswith("start -> implement") for edge in edges)


def test_the_gate_falls_through_to_implement_and_routes_a_failure_to_needs_human() -> None:
    """The ordinary route is UNCONDITIONAL, so `all_conditional_edges` cannot fire.

    A node whose every outgoing edge carries a condition is rejected by the
    pinned engine, and inserting this node consumed `start`'s fallthrough — so
    the fallthrough has to reappear HERE or no dispatch runs a node at all.
    """
    edges = [edge for edge in _edges(text=_dot(payload=_BUNDLE)) if edge.startswith(f"{_GATE} ->")]

    assert edges, "the gate declares no outgoing edges"
    fallthrough = [edge for edge in edges if "condition=" not in edge]
    assert fallthrough == [f"{_GATE} -> implement"]
    blocked = [edge for edge in edges if edge.startswith(f"{_GATE} -> needs_human")]
    assert len(blocked) == 1
    assert 'condition="outcome=failed"' in blocked[0]


def test_the_bundle_declares_the_gate_adapter_default() -> None:
    """The built-in default is the entry the workflow declares for its review input.

    The contracts file's built-in-defaults table puts `dod_gate` on the entry the
    workflow declares for its review input, so the two lines are compared to each other
    rather than to a model name restated here — a default pinned by copying a
    literal would drift the moment the review pin moved.
    """
    toml = _toml(payload=_BUNDLE)
    gate = re.search(rf'^\s*{_ADAPTER_INPUT}\s*=\s*"(?P<value>.+)"', toml, re.MULTILINE)
    review = re.search(r'^\s*review_adapter\s*=\s*"(?P<value>.+)"', toml, re.MULTILINE)

    assert review is not None
    assert gate is not None, "the reserved workflow declares no dod_gate_adapter input"
    assert gate.group("value") == review.group("value")


def test_the_gate_is_a_registered_acp_node_with_its_own_input_candidate() -> None:
    """The adapter layer addresses the gate, and only through its own input.

    The shared `acp_adapter` is deliberately NOT a candidate: this node is an
    adjudication step, not an implementer one, so a target that moved the
    implementer tier must not silently move the gate with it.
    """
    assert _GATE in ACP_NODES
    assert NODE_INPUT_CANDIDATES[_GATE] == (_ADAPTER_INPUT,)


def test_the_gate_carries_a_worst_case_visit_budget() -> None:
    """Lengthening the gate's configured timeout lengthens the derived ceiling.

    The subprocess ceiling is derived from the graph's worst-case path, so a
    node absent from that derivation is budgeted at ZERO — the run would be
    killed by the Dispatcher's own subprocess timeout before the node it never
    accounted for could finish. Asserting through the derivation rather than
    against the visit table itself is what makes this a behaviour test.
    """
    longer = node_timeouts_from_block(block={"node_timeouts": {_GATE: 14400}})

    assert not isinstance(longer, str), longer
    # `max_retries=1` gives the gate two worst-case attempts, as `implement` has.
    assert derive_fabro_timeout_seconds(timeouts=longer) == DEFAULT_FABRO_TIMEOUT_SECONDS + 2 * (
        14400 - 1800
    )
    assert default_node_timeouts().seconds_for(node=_GATE) == 1800


def test_the_gate_dominates_every_green_path_so_it_is_success_critical() -> None:
    """The fallback-priority clause names the gate admission-required.

    Derived from the committed graph rather than asserted as a literal set: the
    gate is success-critical BECAUSE it sits on the only route out of `start`,
    and reading it off the dominator derivation is what proves the widened graph
    is still a shape that derivation understands rather than one it refuses.
    """
    critical = derive_success_critical(graph=parse_workflow_graph(text=_dot(payload=_BUNDLE)))

    assert not isinstance(critical, str), critical
    assert _GATE in critical.nodes


def test_the_registered_variant_declares_the_bundles_acp_node_set() -> None:
    """Peer parity for the names the adapter, model and timeout layers address.

    A groom-kind variant MAY leave the gate unreached by its edges, but it MUST
    still DECLARE it, so a repository configuring `dispatcher.acp_nodes.dod_gate`
    or `dispatcher.node_timeouts.dod_gate` is not refused for naming a node the
    variant's own payload lacks.
    """
    bundle = _acp_node_names(payload=_BUNDLE)

    assert _GATE in bundle
    assert _acp_node_names(payload=_VARIANT) == bundle
    assert re.search(rf'^\s*{_ADAPTER_INPUT}\s*=\s*"', _toml(payload=_VARIANT), re.MULTILINE)


def test_the_variant_leaves_the_gate_unreached_by_its_edges() -> None:
    """The permitted difference, asserted so it stays the ONLY one.

    Declaring the node is what makes the layers resolve; REACHING it would spend
    an adjudication turn on a graph whose purpose is to produce Definitions of
    Done rather than to grade one.
    """
    edges = _edges(text=_dot(payload=_VARIANT))

    assert not any(_GATE in edge for edge in edges)
