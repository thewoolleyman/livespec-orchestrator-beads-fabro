"""Scenario 285 — the implement stage is a Red/Green command graph.

The graph is intentionally inspected through its shipped DOT payload: the
factory materializes this file, so a unit assertion over a Python helper would
not establish the route a dispatched run can take.  The reset helper is run in
a scratch repository because its promise is about the branch and worktree it
leaves behind.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph

_ROOT = Path(__file__).resolve().parents[2]
_GRAPH = _ROOT / ".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro"
_RESET = _ROOT / "dev-tooling/reset-test-wrong-to-dispatch-base.sh"


def _run(*, cwd: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, check=True, text=True, capture_output=True)


def test_scenario285_routes_each_implement_commit_through_red_and_green_command_nodes() -> None:
    """The split replaces `implement`, and only command nodes own commits."""
    graph = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph

    assert "implement" not in graph.nodes
    assert {"red", "commit_red", "green", "commit_green", "test_wrong_reset"} <= set(graph.nodes)
    edges = {
        (edge.source, edge.destination, edge.attributes.get("condition")) for edge in graph.edges
    }
    assert ("dod_gate_mutation_guard", "red", None) in edges
    assert ("red", "commit_red", None) in edges
    assert ("commit_red", "red", "outcome=failed") in edges
    assert ("commit_red", "green", None) in edges
    assert ("green", "test_wrong_reset", "preferred_label=test-wrong") in edges
    assert ("test_wrong_reset", "red", None) in edges
    assert ("commit_green", "green", "outcome=failed") in edges
    assert ("commit_green", "implementation_diff", None) in edges
    assert graph.nodes["commit_red"]["script"] == "bash dev-tooling/commit-red.sh"
    assert graph.nodes["commit_green"]["script"] == "bash dev-tooling/commit-green.sh"
    assert "commit-runner.py" not in graph.nodes["red"].get("prompt", "")
    assert "commit-runner.py" not in graph.nodes["green"].get("prompt", "")


def test_scenario285_test_wrong_reset_restores_the_dispatch_base(tmp_path: Path) -> None:
    """A test-wrong lap leaves its handoff but removes all branch changes."""
    repo = tmp_path / "repo"
    _run(cwd=tmp_path, args=["git", "init", "-q", str(repo)])
    _run(cwd=repo, args=["git", "config", "user.name", "Scenario 285"])
    _run(cwd=repo, args=["git", "config", "user.email", "scenario285@example.test"])
    (repo / "tracked.txt").write_text("base\n", encoding="utf-8")
    _run(cwd=repo, args=["git", "add", "tracked.txt"])
    _run(cwd=repo, args=["git", "commit", "-qm", "base"])
    _run(cwd=repo, args=["git", "remote", "add", "origin", str(repo)])
    _run(cwd=repo, args=["git", "fetch", "origin", "master:refs/remotes/origin/master"])
    (repo / "tracked.txt").write_text("wrong test\n", encoding="utf-8")
    (repo / "untracked.txt").write_text("remove me\n", encoding="utf-8")

    reset = subprocess.run(
        [str(_RESET), "master"], cwd=repo, check=False, text=True, capture_output=True
    )

    assert reset.returncode == 0, reset.stderr
    assert (repo / "tracked.txt").read_text(encoding="utf-8") == "base\n"
    assert not (repo / "untracked.txt").exists()
