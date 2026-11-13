"""The Green node declares the split-stage routing outcomes."""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph

_GRAPH = (
    Path(__file__).resolve().parents[2]
    / ".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro"
)


def test_green_declares_completion_and_test_wrong_outcomes() -> None:
    """The command-node graph receives both Green outcomes as structured labels."""
    graph = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph

    assert "implement" not in graph.nodes
    schema = graph.nodes["green"]["output_schema"]
    assert '"definition_of_done_complete"' in schema
    assert '"preferred_next_label"' in schema
    edges = {
        (edge.source, edge.destination, edge.attributes.get("condition")) for edge in graph.edges
    }
    assert ("green", "test_wrong_reset", "preferred_label=test-wrong") in edges
    assert ("green", "commit_green", None) in edges
