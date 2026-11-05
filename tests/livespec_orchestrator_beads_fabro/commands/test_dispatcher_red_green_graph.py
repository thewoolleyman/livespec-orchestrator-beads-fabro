"""Pin the implement stage's separate Red, commit, Green and commit graph."""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_already_satisfied import (
    already_satisfied_base_from_text,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph

_GRAPH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro"
)


def test_the_implement_stage_is_a_red_green_command_graph() -> None:
    """Each turn is fresh, and only the two command nodes commit it."""
    graph = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph

    assert {
        "implement",
        "implement_commit_settle",
        "test_wrong_reset",
    }.isdisjoint(graph.nodes)
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
    assert ("green", "implement_completion", None) in edges
    assert ("implement_completion", "implement_hook_route", "outcome=failed") in edges
    assert ("implement_hook_route", "green", "outcome=succeeded") in edges
    assert ("implement_completion", "commit_green", None) in edges
    assert ("green", "commit_green", None) not in edges
    assert ("commit_green", "implementation_diff", None) in edges
    assert ("commit_green", "green", "outcome=failed") in edges
    assert ("red", "already_satisfied", "preferred_label=already-satisfied") in edges
    assert ("red", "green", "preferred_label=seeded-open-red") in edges
    assert ("red", "green", "preferred_label=seeded-already-satisfied") in edges
    assert not [edge for edge in graph.edges if edge.source == "already_satisfied"]


def test_the_already_satisfied_node_prints_the_line_the_dispatcher_reads() -> None:
    """The node's printed line, with its base substituted, is the ending the engine parses."""
    graph = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    script = graph.nodes["already_satisfied"]["script"]
    base = "e" * 40
    substitution = '$(git rev-parse "origin/{{ inputs.default_branch }}")'

    assert substitution in script
    printed = script.split('echo "', 1)[1].split('" >&2', 1)[0].replace(substitution, base)

    assert already_satisfied_base_from_text(text=printed) == base
    assert already_satisfied_base_from_text(text=script) is None
