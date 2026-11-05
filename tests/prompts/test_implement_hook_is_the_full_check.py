"""Command nodes own implement commits while fix loops keep their runner."""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph

_GRAPH = (
    Path(__file__).resolve().parents[2]
    / ".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro"
)


def test_implement_commits_are_owned_by_command_nodes() -> None:
    """Red and Green do not start the detached commit runner themselves."""
    graph = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph

    assert "implement" not in graph.nodes
    for node in ("red", "green"):
        assert graph.nodes[f"commit_{node}"]["script"] == (
            'LIVESPEC_MECHANICAL_TARGETS="{{ inputs.mechanical_targets }}" '
            'LIVESPEC_MECHANICAL_REENTRIES="{{ inputs.mechanical_reentries }}" '
            f"bash dev-tooling/commit-{node}.sh"
        )


def test_fix_and_review_fix_keep_their_commit_runner_settle_nodes() -> None:
    """The graph rewrite does not alter either existing repair loop."""
    graph = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph

    for node in ("fix_commit_settle", "review_fix_commit_settle"):
        assert "livespec-commit-runner.py" in graph.nodes[node]["script"]
