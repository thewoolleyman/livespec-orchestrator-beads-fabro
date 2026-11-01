"""Pin the implement stage's separate Red, commit, Green and commit graph."""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph

_GRAPH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro"
)


def test_the_implement_stage_is_a_red_green_command_graph() -> None:
    """Each turn is fresh, and only the two command nodes commit it."""
    graph = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph

    assert {"implement", "implement_commit_settle", "implement_completion"}.isdisjoint(graph.nodes)
    assert graph.nodes["red"]["backend"] == "acp"
    assert graph.nodes["red"]["acp.command"] == "{{ inputs.implement_adapter }}"
    assert graph.nodes["red"]["prompt"] == "@prompts/red.md"
    assert graph.nodes["green"]["backend"] == "acp"
    assert graph.nodes["green"]["acp.command"] == "{{ inputs.implement_adapter }}"
    assert graph.nodes["green"]["prompt"] == "@prompts/green.md"
    assert graph.nodes["commit_red"]["script"] == "bash dev-tooling/commit-red.sh"
    assert graph.nodes["commit_green"]["script"] == "bash dev-tooling/commit-green.sh"

    edges = {
        (edge.source, edge.destination, edge.attributes.get("condition")) for edge in graph.edges
    }
    assert ("dod_gate_mutation_guard", "red", None) in edges
    assert ("red", "commit_red", None) in edges
    assert ("commit_red", "green", None) in edges
    assert ("commit_red", "red", "outcome=failed") in edges
    assert ("green", "commit_green", None) in edges
    assert ("commit_green", "implementation_diff", None) in edges
    assert ("commit_green", "green", "outcome=failed") in edges
    assert ("green", "test_wrong_reset", "preferred_label=test-wrong") in edges
    assert ("test_wrong_reset", "red", None) in edges
    assert ("red", "already_satisfied", "preferred_label=already-satisfied") in edges
