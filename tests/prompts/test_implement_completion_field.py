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
