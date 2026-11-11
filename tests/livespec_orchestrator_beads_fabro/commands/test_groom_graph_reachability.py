"""The committed groom-work-item graph is one the Petri-era engine accepts (bd-ib-ttrjvj).

Petri refuses, at run creation, a graph with a node its start cannot reach or an
exit node its start cannot reach (`attractor.unreachable_node` and
`attractor.exit_unreachable`, "Error in Petri, warning in Fabro"). The groom
variant carried both: it declares the reserved workflow's node names so the
adapter layer, the codex_models expansion and the per-node timeout table resolve
against it (the registered-variant clause), and every path ended at a failing
terminal. A legacy 0.254 validator accepts that shape, which is why it merged.

These assertions read the committed graph's own structure, so they hold with no
fabro binary present. The terminal routing they pin keeps the groom run ending
NON-GREEN: the draft or filing plan rides the needs_human sentinel, and a green
ending would route the run into the pull-request path a groom run has none for.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import (
    DotGraph,
    parse_dot_graph,
)

_GRAPH = (
    Path(__file__).resolve().parents[3]
    / ".fabro"
    / "workflows"
    / "groom-work-item"
    / "workflow.fabro"
)


def _graph() -> DotGraph:
    parsed = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert isinstance(parsed, DotGraph), parsed
    return parsed


def _shape_node(*, graph: DotGraph, shape: str) -> str:
    named = [name for name, attrs in graph.nodes.items() if attrs.get("shape") == shape]
    assert len(named) == 1, named
    return named[0]


def _reachable(*, graph: DotGraph) -> set[str]:
    start = _shape_node(graph=graph, shape="Mdiamond")
    seen = {start}
    frontier = [start]
    while frontier:
        node = frontier.pop()
        for edge in graph.edges:
            if edge.source == node and edge.destination not in seen:
                seen.add(edge.destination)
                frontier.append(edge.destination)
    return seen


def test_every_declared_node_is_reachable_from_start() -> None:
    graph = _graph()
    assert sorted(set(graph.nodes) - _reachable(graph=graph)) == []


def test_the_exit_node_is_reachable_from_start() -> None:
    graph = _graph()
    assert _shape_node(graph=graph, shape="Msquare") in _reachable(graph=graph)


def test_needs_human_reaches_exit_only_behind_a_failure_that_ends_the_run() -> None:
    graph = _graph()
    exit_node = _shape_node(graph=graph, shape="Msquare")
    into_exit = [edge for edge in graph.edges if edge.source == "needs_human"]
    assert [edge.destination for edge in into_exit] == [exit_node]
    assert graph.nodes["needs_human"].get("on_failure") == "exit"


def test_the_apply_publication_still_ends_at_needs_human() -> None:
    graph = _graph()
    assert "needs_human" in {edge.destination for edge in graph.edges if edge.source == "pr"}
