"""The reachability leg of the factory-graph gate: no shipped node is orphaned.

The engine refuses a graph with a node its start node cannot reach
(`attractor.unreachable_node`), and refuses it at `fabro run`, so a shipped graph
carrying one makes every dispatch die before any node runs. Release v0.329.0
shipped exactly that: the red/green split rewired the edges that entered
`implement_hook_route` and `implement_commit_settle` and left both nodes in
place, and the release CI stayed green because no check asked the question.

This leg asks it of the SHIPPED graphs without the engine, so it also runs inside
a Fabro sandbox, where the `fabro` binary is structurally absent and the
engine-backed leg can only warn. It reads every `workflow*.fabro` under
`.claude-plugin/.fabro/workflows/*/` rather than the registered payload set, so a
variant graph beside the bundle, or a second graph file in one directory, is
read too. The start node is the one the graph itself declares with
`shape=Mdiamond`, or failing that the node the engine's own fallback names,
`start`; a graph with neither is a finding, never a pass, because reachability
from nothing would report every node orphaned or none checked. The nodes
checked are every declared node plus every edge endpoint, so a node only an
edge names is graded too.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import (
    DotGraph,
    parse_dot_graph,
)

__all__: list[str] = ["unreachable_node_findings"]

_GRAPH_GLOB = ".claude-plugin/.fabro/workflows/*/workflow*.fabro"
_START_SHAPE = "Mdiamond"
_START_FALLBACK_NAMES = ("start", "Start")


def unreachable_node_findings(*, repo_root: Path) -> list[str]:
    """Name every node of every shipped graph that its start node cannot reach."""
    findings: list[str] = []
    for graph_path in sorted(repo_root.glob(_GRAPH_GLOB)):
        where = graph_path.relative_to(repo_root / ".claude-plugin" / ".fabro" / "workflows")
        parsed = parse_dot_graph(text=graph_path.read_text(encoding="utf-8"))
        if isinstance(parsed, str):
            findings.append(f"{where}: reachability could not be checked: {parsed}")
            continue
        starts = _start_nodes(graph=parsed)
        if not starts:
            findings.append(f"{where}: no start node (`shape={_START_SHAPE}`) is declared")
            continue
        reached = _reachable(graph=parsed, starts=starts)
        findings.extend(
            f"{where}: `{node}` is not reachable from the start node `{starts[0]}`"
            for node in _all_nodes(graph=parsed)
            if node not in reached
        )
    return findings


def _all_nodes(*, graph: DotGraph) -> list[str]:
    """Every declared node, then every node only an edge names, in first-seen order."""
    names = list(graph.nodes)
    for edge in graph.edges:
        names.extend(name for name in (edge.source, edge.destination) if name not in names)
    return names


def _start_nodes(*, graph: DotGraph) -> list[str]:
    """The declared start shape's nodes, else the engine's fallback name when present."""
    declared = [name for name, attrs in graph.nodes.items() if attrs.get("shape") == _START_SHAPE]
    if declared:
        return declared
    named = set(_all_nodes(graph=graph))
    return [name for name in _START_FALLBACK_NAMES if name in named][:1]


def _reachable(*, graph: DotGraph, starts: list[str]) -> set[str]:
    """Every node a walk along the graph's edges reaches from the start nodes."""
    reached = set(starts)
    pending = list(starts)
    while pending:
        current = pending.pop()
        for edge in graph.edges:
            if edge.source == current and edge.destination not in reached:
                reached.add(edge.destination)
                pending.append(edge.destination)
    return reached
