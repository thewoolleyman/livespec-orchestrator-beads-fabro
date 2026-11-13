"""Scenario 285 exhausted command nodes retain their recorded verdicts."""

from __future__ import annotations

import subprocess
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph

_ROOT = Path(__file__).resolve().parents[2]
_GRAPH = _ROOT / ".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro"


def _run(*, cwd: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, check=False, capture_output=True, text=True)


def _repo(*, tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    repo = tmp_path / "repo"
    _ = _run(cwd=tmp_path, args=["git", "init", "-q", str(repo)])
    return repo


def test_exhausted_red_and_green_bounds_name_the_last_commit_verdict(tmp_path: Path) -> None:
    """A retry cap reports the command that refused, not an unrelated turn."""
    graph = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph

    for node, counter, section, status, target in (
        ("red_admission", "livespec-red-admission-count", "commit_red", "8", "check-red"),
        ("green_admission", "livespec-green-admission-count", "commit_green", "10", "check-green"),
    ):
        repo = _repo(tmp_path=tmp_path / node)
        git_dir = repo / ".git"
        (git_dir / counter).write_text("3\n", encoding="utf-8")
        (git_dir / "livespec-implement-handoff.md").write_text(
            f"## {section}\nExit status: {status}; failed targets: {target}\n",
            encoding="utf-8",
        )

        result = _run(cwd=repo, args=["sh", "-c", str(graph.nodes[node]["script"])])

        cause = (git_dir / "livespec-stage-cause").read_text(encoding="utf-8")
        assert result.returncode != 0, result.stderr
        assert f"Exit status: {status}" in cause
        assert target in cause
