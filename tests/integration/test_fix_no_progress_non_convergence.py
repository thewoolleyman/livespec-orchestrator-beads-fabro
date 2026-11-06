"""Scenario coverage for a fix turn that cannot advance the failed janitor head.

The shipped graph must not spend its wall budget alternating an unchanged fix
turn with the same janitor failure.  These tests execute the command-node
scripts decoded from the committed graph: a copied shell recipe would let a
test pass while the factory ran different bytes.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import NON_CONVERGED_MARKER

_GRAPH = (
    Path(__file__).resolve().parents[2]
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "workflow.fabro"
)


def _script(*, node: str) -> str:
    """Decode a command node from the shipped graph."""
    graph = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    assert node in graph.nodes
    return graph.nodes[node]["script"].replace("{{ inputs.default_branch }}", "master")


def _run(*, node: str, repo: Path) -> subprocess.CompletedProcess[str]:
    """Run one shipped command node in the throwaway working branch."""
    return subprocess.run(
        ["sh", "-c", _script(node=node)],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )


def _git(*args: str, repo: Path) -> None:
    """Run a setup-only git command and require it to succeed."""
    _ = subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _repo(*, tmp_path: Path) -> Path:
    """Create a branch with an `origin/master` that janitor can refresh against."""
    origin = tmp_path / "origin.git"
    _ = subprocess.run(["git", "init", "--bare", "--quiet", str(origin)], check=True)
    repo = tmp_path / "repo"
    _git("init", "--quiet", str(repo), repo=tmp_path)
    _git("config", "user.name", "Test User", repo=repo)
    _git("config", "user.email", "test@example.test", repo=repo)
    _ = (repo / "work.txt").write_text("initial\n", encoding="utf-8")
    _git("add", "work.txt", repo=repo)
    _git("commit", "--quiet", "-m", "initial", repo=repo)
    _git("remote", "add", "origin", str(origin), repo=repo)
    _git("push", "--quiet", "origin", "HEAD:master", repo=repo)
    _git("fetch", "--quiet", "origin", "master", repo=repo)
    return repo


def _start_failed_refresh(*, repo: Path) -> subprocess.CompletedProcess[str]:
    """Cause the measured pre-aggregate rebase-start failure without running a suite."""
    git_dir = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    (repo / git_dir / "rebase-merge").mkdir(parents=True, exist_ok=True)
    result = _run(node="janitor", repo=repo)
    assert result.returncode != 0
    assert "rebase-merge" in result.stderr
    return result


def test_repeated_refresh_failure_at_an_unchanged_fix_head_exits_non_converged(
    tmp_path: Path,
) -> None:
    """A no-op fix sends the next identical janitor failure to the existing exit."""
    repo = _repo(tmp_path=tmp_path)
    first = _start_failed_refresh(repo=repo)
    assert first.returncode != 0
    first_route = _run(node="janitor_refresh_route", repo=repo)
    assert first_route.returncode == 0
    assert json.loads(first_route.stdout) == {"preferred_next_label": "refresh_repair"}
    assert _run(node="refresh_repair", repo=repo).returncode == 0

    unchanged_head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    assert _run(node="fix_progress_route", repo=repo).returncode == 0
    second = _start_failed_refresh(repo=repo)
    assert second.returncode != 0
    repeated_route = _run(node="janitor_refresh_route", repo=repo)

    assert repeated_route.returncode == 0
    assert json.loads(repeated_route.stdout) == {"preferred_next_label": "fix"}
    repeated = _run(node="janitor_failure_route", repo=repo)

    assert repeated.returncode != 0
    terminal = _run(node="non_converged", repo=repo)
    assert terminal.returncode != 0
    assert NON_CONVERGED_MARKER in terminal.stderr
    assert "janitor failed again" in terminal.stderr
    assert unchanged_head in terminal.stderr


def test_a_fix_head_change_keeps_the_next_janitor_failure_in_the_repair_loop(
    tmp_path: Path,
) -> None:
    """A progress-making fix still returns to janitor instead of the terminal."""
    repo = _repo(tmp_path=tmp_path)
    _start_failed_refresh(repo=repo)
    assert _run(node="janitor_failure_route", repo=repo).returncode == 0
    _ = (repo / "work.txt").write_text("fixed\n", encoding="utf-8")
    _git("add", "work.txt", repo=repo)
    _git("commit", "--quiet", "-m", "fix", repo=repo)

    assert _run(node="fix_progress_route", repo=repo).returncode == 0
    next_failure = _run(node="janitor_failure_route", repo=repo)
    assert next_failure.returncode == 0

    graph = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    edges = {
        (edge.source, edge.destination, edge.attributes.get("condition", ""))
        for edge in graph.edges
    }
    assert ("janitor", "janitor_refresh_route", "outcome!=succeeded") in edges
    assert ("janitor_refresh_route", "janitor_failure_route", "preferred_label=fix") in edges
    assert ("janitor_refresh_route", "fix", "") in edges
    assert ("fix", "fix_progress_route", "outcome=succeeded") in edges
    assert ("fix_progress_route", "fix_commit_settle", "") in edges
    assert ("fix_commit_settle", "janitor_admission", "") in edges
    assert ("janitor_failure_route", "non_converged", "outcome=failed") in edges
