"""Scenario 176 (work-item bd-ib-yzrguu) — a commit settle hands on a tree with no merge or rebase open.

A fix turn that integrates the default branch by merge or rebase can end while
that operation is still in progress, and whichever node touches the tree next
breaks (`there is already a rebase-merge directory`, a checkpoint that flattens
a merge into one parent). Every tree-mutating agent turn routes into a commit
settle node that runs the commit runner's `settle` operation, so one guard there
is the whole remedy. These cases execute the COMMITTED node script and the
runner's exact source in a real git fixture:

- a FAILED commit run aborts the merge or rebase it was recording, leaves HEAD
  where the turn started, and journals the stage and the operation;
- a PASSED commit run mid-rebase finishes the rebase, so the settled commit stays
  on HEAD, and a passed run with nothing in progress leaves history untouched;
- a failed fix commit run re-enters `fix` with a brief naming the run;
- the next node's refresh (`git rebase`) is not refused afterwards.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_commit_runner_program import (
    COMMIT_RUNNER_PROGRAM_FILENAME,
    commit_runner_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GRAPH = (
    _REPO_ROOT
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "workflow.fabro"
)
_SETTLES = (
    ("implement_commit_settle", "implement"),
    ("fix_commit_settle", "fix"),
    ("review_fix_commit_settle", "review_fix"),
)
_BANNER_HOOK = "#!/bin/sh\nprintf 'lefthook v1.13.6  hook: pre-commit\\n'\nexit {status}\n"


def _clean_environment() -> dict[str, str]:
    """The child environment with every GIT_ and coverage variable removed.

    This suite can itself run under a commit hook, whose `GIT_INDEX_FILE` would
    otherwise point the fixture's commits at the outer repository.
    """
    return {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("GIT_", "COV_CORE", "COVERAGE"))
    }


def _git(repo: Path, *argv: str) -> str:
    environment = {**_clean_environment(), "GIT_EDITOR": "true", "GIT_CONFIG_GLOBAL": "/dev/null"}
    result = subprocess.run(
        ["git", *argv], cwd=repo, check=True, capture_output=True, text=True, env=environment
    )
    return result.stdout.strip()


def _do(repo: Path, *argv: str) -> None:
    _ = _git(repo, *argv)


def _write(repo: Path, name: str, text: str) -> None:
    _ = (repo / name).write_text(text, encoding="utf-8")


def _commit(repo: Path, message: str) -> None:
    _do(repo, "add", "-A")
    _do(repo, "commit", "--quiet", "-m", message)


def _repo(tmp_path: Path) -> Path:
    """A repository whose `work` branch (two commits) conflicts with `side` on a.txt."""
    repo = tmp_path / "clone"
    repo.mkdir()
    _do(repo, "init", "--quiet", "-b", "base")
    _do(repo, "config", "user.name", "Fixture")
    _do(repo, "config", "user.email", "fixture@example.invalid")
    _write(repo, "a.txt", "base\n")
    _commit(repo, "base")
    _do(repo, "checkout", "--quiet", "-b", "side")
    _write(repo, "a.txt", "side\n")
    _commit(repo, "side")
    _do(repo, "checkout", "--quiet", "base")
    _do(repo, "checkout", "--quiet", "-b", "work")
    _write(repo, "a.txt", "work\n")
    _commit(repo, "work one")
    _write(repo, "b.txt", "work two\n")
    _commit(repo, "work two")
    return repo


def _plugins(tmp_path: Path) -> Path:
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    _ = (plugins / COMMIT_RUNNER_PROGRAM_FILENAME).write_text(
        commit_runner_program_source(), encoding="utf-8"
    )
    return plugins


def _runner(repo: Path, plugins: Path, *argv: str) -> str:
    environment = {**_clean_environment(), "GIT_EDITOR": "true"}
    result = subprocess.run(
        [sys.executable, str(plugins / COMMIT_RUNNER_PROGRAM_FILENAME), *argv],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    return result.stdout.strip()


def _hook(repo: Path, *, status: int) -> None:
    path = repo / ".git" / "hooks" / "pre-commit"
    _ = path.write_text(_BANNER_HOOK.format(status=status), encoding="utf-8")
    path.chmod(0o755)


def _run_commit(repo: Path, plugins: Path) -> tuple[str, dict[str, object]]:
    run_id = _runner(repo, plugins, "start", "--", "git", "commit", "--no-edit")
    report = _runner(repo, plugins, "wait", run_id, "--timeout-seconds", "60")
    return run_id, json.loads(report.splitlines()[-1])


def _integrate(repo: Path, operation: str) -> None:
    """Start `operation` of `side` into `work`, stop on the conflict, and stage a resolution."""
    argv = ("rebase", "side") if operation == "rebase" else ("merge", "--no-commit", "side")
    result = subprocess.run(
        ["git", *argv],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        env=_clean_environment(),
    )
    assert result.returncode != 0, result.stdout
    _write(repo, "a.txt", "resolved\n")
    _do(repo, "add", "a.txt")


def _in_progress(repo: Path) -> list[str]:
    names = ("rebase-merge", "rebase-apply", "MERGE_HEAD")
    return [name for name in names if (repo / ".git" / name).exists()]


def _node_script(*, node: str) -> str:
    parsed = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(parsed, str), parsed
    return parsed.nodes[node]["script"]


def _settle(repo: Path, plugins: Path, *, node: str) -> subprocess.CompletedProcess[str]:
    environment = {**_clean_environment(), "LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT": str(plugins)}
    return subprocess.run(
        ["sh", "-c", _node_script(node=node)],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


def _refreshable(repo: Path) -> bool:
    """The refresh every later node performs: a rebase onto the default branch."""
    result = subprocess.run(
        ["git", "rebase", "base"],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        env=_clean_environment(),
    )
    return result.returncode == 0


@pytest.mark.parametrize(("node", "stage"), _SETTLES)
@pytest.mark.parametrize("operation", ["rebase", "merge"])
def test_a_failed_commit_run_aborts_the_operation_and_journals_it(
    tmp_path: Path, node: str, stage: str, operation: str
) -> None:
    repo = _repo(tmp_path)
    plugins = _plugins(tmp_path)
    started_from = _git(repo, "rev-parse", "HEAD")
    _integrate(repo, operation)
    _hook(repo, status=1)
    _, report = _run_commit(repo, plugins)
    assert report["state"] == "failed"
    assert _in_progress(repo) != []

    result = _settle(repo, plugins, node=node)

    assert _in_progress(repo) == []
    assert _git(repo, "rev-parse", "HEAD") == started_from
    assert _git(repo, "rev-parse", "--abbrev-ref", "HEAD") == "work"
    assert f"stage {stage}" in result.stderr
    assert f"aborted the in-progress {operation}" in result.stderr
    assert _refreshable(repo)


@pytest.mark.parametrize(("node", "stage"), _SETTLES)
def test_a_passed_commit_run_mid_rebase_finishes_the_rebase(
    tmp_path: Path, node: str, stage: str
) -> None:
    repo = _repo(tmp_path)
    plugins = _plugins(tmp_path)
    _integrate(repo, "rebase")
    _hook(repo, status=0)
    _, report = _run_commit(repo, plugins)
    assert report["state"] == "passed"
    assert _in_progress(repo) != []
    settled = str(report["head"])

    result = _settle(repo, plugins, node=node)

    assert _in_progress(repo) == []
    assert _git(repo, "rev-parse", "--abbrev-ref", "HEAD") == "work"
    _do(repo, "merge-base", "--is-ancestor", settled, "HEAD")
    assert _git(repo, "show", "HEAD:b.txt") == "work two"
    assert _git(repo, "show", "HEAD:a.txt") == "resolved"
    assert f"stage {stage}" in result.stderr
    assert _refreshable(repo)


@pytest.mark.parametrize(("node", "stage"), _SETTLES)
def test_a_passed_commit_run_with_nothing_in_progress_changes_no_history(
    tmp_path: Path, node: str, stage: str
) -> None:
    del stage
    repo = _repo(tmp_path)
    plugins = _plugins(tmp_path)
    _write(repo, "c.txt", "plain\n")
    _do(repo, "add", "c.txt")
    _hook(repo, status=0)
    run_id = _runner(repo, plugins, "start", "--", "git", "commit", "-m", "plain")
    report = json.loads(_runner(repo, plugins, "wait", run_id, "--timeout-seconds", "60"))
    assert report["state"] == "passed"
    history = _git(repo, "log", "--format=%H %P", "--topo-order")
    head = _git(repo, "rev-parse", "HEAD")

    _ = _settle(repo, plugins, node=node)

    assert _git(repo, "log", "--format=%H %P", "--topo-order") == history
    assert _git(repo, "rev-parse", "HEAD") == head
    assert _git(repo, "rev-parse", "--abbrev-ref", "HEAD") == "work"


def test_a_failed_fix_commit_run_reenters_fix_with_a_brief_naming_it(tmp_path: Path) -> None:
    parsed = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(parsed, str), parsed
    targets = [
        (edge.destination, edge.attributes.get("condition", ""))
        for edge in parsed.edges
        if edge.source == "fix_commit_settle"
    ]
    assert ("fix", "outcome=failed") in targets
    assert ("janitor_admission", "") in targets
    repo = _repo(tmp_path)
    plugins = _plugins(tmp_path)
    _integrate(repo, "merge")
    _hook(repo, status=1)
    run_id, _ = _run_commit(repo, plugins)

    result = _settle(repo, plugins, node="fix_commit_settle")

    assert result.returncode != 0, result.stderr
    brief = (repo / ".git" / "livespec-fix-live-commit").read_text(encoding="utf-8")
    assert brief.startswith("failed\n")
    assert run_id in brief
    assert "aborted the in-progress merge" in brief
