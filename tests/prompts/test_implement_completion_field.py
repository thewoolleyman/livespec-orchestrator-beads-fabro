"""The Green turn retains the implement stage's completion declaration."""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph

_GRAPH = (
    Path(__file__).resolve().parents[2]
    / ".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro"
)


def test_green_owns_the_implement_completion_field() -> None:
    """Splitting the turn moves the field from `implement` to Green."""
    graph = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph

    assert "implement" not in graph.nodes
    assert graph.nodes["green"]["output_schema"] == (
        '{"type":"object","properties":{"definition_of_done_complete":{"type":"boolean"}}}'
    )


def test_only_a_complete_green_turn_reaches_the_commit() -> None:
    """A false or absent completion field re-enters Green instead of committing."""
    graph = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph

    gate = graph.nodes["implement_completion"]
    assert gate["stdin_source"] == "context.output.green"
    assert "LIVESPEC_IMPLEMENT_PARTIAL_PROGRESS" in gate["script"]

    edges = {
        (edge.source, edge.destination, edge.attributes.get("condition")) for edge in graph.edges
    }
    assert ("green", "implement_completion", None) in edges
    assert ("implement_completion", "implement_hook_route", "outcome=failed") in edges
    assert ("implement_hook_route", "green", "outcome=succeeded") in edges
    assert ("implement_completion", "commit_green", None) in edges
    assert not [e for e in graph.edges if e.source == "green" and e.destination == "commit_green"]
