"""Scenario 285 — the implement stage is a Red/Green command graph."""

from __future__ import annotations

import subprocess
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph

_ROOT = Path(__file__).resolve().parents[2]
_GRAPH = _ROOT / ".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro"
_RESET = _ROOT / "dev-tooling/reset-test-wrong-to-dispatch-base.sh"


def _run(*, cwd: Path, args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, check=check, text=True, capture_output=True)


def _graph() -> object:
    graph = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    return graph


def _scratch_repo(*, tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    repo = tmp_path / "repo"
    _run(cwd=tmp_path, args=["git", "init", "-q", str(repo)])
    _run(cwd=repo, args=["git", "config", "user.name", "Scenario 285"])
    _run(cwd=repo, args=["git", "config", "user.email", "scenario285@example.test"])
    (repo / "tracked.txt").write_text("base\n", encoding="utf-8")
    _run(cwd=repo, args=["git", "add", "tracked.txt"])
    _run(cwd=repo, args=["git", "commit", "-qm", "base"])
    _run(cwd=repo, args=["git", "remote", "add", "origin", str(repo)])
    _run(cwd=repo, args=["git", "fetch", "origin", "master:refs/remotes/origin/master"])
    return repo


def test_scenario285_routes_each_implement_commit_through_red_and_green_command_nodes() -> None:
    """The split replaces ``implement`` and admissions name exhausted bounds."""
    graph = _graph()
    assert "implement" not in graph.nodes
    assert {
        "red_admission",
        "red",
        "commit_red",
        "green_admission",
        "green",
        "commit_green",
        "test_wrong_reset",
    } <= set(graph.nodes)
    edges = {
        (edge.source, edge.destination, edge.attributes.get("condition")) for edge in graph.edges
    }
    assert ("dod_gate_mutation_guard", "red_admission", None) in edges
    assert ("red_admission", "red", None) in edges
    assert ("red", "commit_red", None) in edges
    assert ("commit_red", "red_admission", "outcome=failed") in edges
    assert ("commit_red", "green_admission", None) in edges
    assert ("green_admission", "green", None) in edges
    assert ("green", "test_wrong_reset", "preferred_label=test-wrong") in edges
    assert ("test_wrong_reset", "red_admission", None) in edges
    assert ("commit_green", "green_admission", "outcome=failed") in edges
    assert ("commit_green", "implementation_diff", None) in edges
    assert graph.nodes["commit_red"]["script"] == "bash dev-tooling/commit-red.sh"
    assert graph.nodes["commit_green"]["script"] == "bash dev-tooling/commit-green.sh"
    assert "commit-runner.py" not in graph.nodes["red"].get("prompt", "")
    assert "commit-runner.py" not in graph.nodes["green"].get("prompt", "")


def test_scenario285_test_wrong_reset_restores_the_dispatch_base(tmp_path: Path) -> None:
    """A test-wrong lap leaves its handoff but removes all branch changes."""
    repo = _scratch_repo(tmp_path=tmp_path)
    (repo / "tracked.txt").write_text("wrong test\n", encoding="utf-8")
    (repo / "untracked.txt").write_text("remove me\n", encoding="utf-8")

    reset = _run(cwd=repo, args=[str(_RESET), "master"], check=False)

    assert reset.returncode == 0, reset.stderr
    assert (repo / "tracked.txt").read_text(encoding="utf-8") == "base\n"
    assert not (repo / "untracked.txt").exists()


def test_scenario285_exhausted_admissions_write_the_handoff_evidence(tmp_path: Path) -> None:
    """Every exhausted loop writes a terminal cause from its recorded handoff."""
    graph = _graph()
    for node, counter, _section in (
        ("red_admission", "livespec-red-admission-count", "red"),
        ("green_admission", "livespec-green-admission-count", "green"),
        ("test_wrong_reset", "livespec-implement-test-wrong-reentries", "test-wrong"),
    ):
        repo = _scratch_repo(tmp_path=tmp_path / node)
        git_dir = repo / ".git"
        (git_dir / counter).write_text(
            "3\n" if node != "test_wrong_reset" else "2\n", encoding="utf-8"
        )
        (git_dir / "livespec-implement-handoff.md").write_text(
            "## red\npreview exit status: 7; failed targets: check-lint\n"
            "## green\npreview exit status: 9; failed targets: check-types\n"
            "## test-wrong\nRed test is wrong.\n",
            encoding="utf-8",
        )
        script = graph.nodes[node]["script"].replace("{{ inputs.default_branch }}", "master")

        result = _run(cwd=repo, args=["sh", "-c", script], check=False)

        cause = (git_dir / "livespec-stage-cause").read_text(encoding="utf-8")
        assert result.returncode != 0, result.stderr
        assert "EXHAUSTED" in result.stderr
        assert "exit status" in cause
        assert "failed targets" in cause
