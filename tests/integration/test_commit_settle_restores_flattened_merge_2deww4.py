"""Scenario 179 (work-item bd-ib-2deww4) — a settle restores a merge the engine checkpoint consumed.

A fix or review_fix turn can end with its runner commit of an in-progress merge
still running. The engine's per-node checkpoint then commits the merged index as
a TWO-parent commit, which removes `MERGE_HEAD`, and the commit-settle node's
restore-head step used to `git reset --soft` back to the runner commit's starting
head: the merged tree stayed staged with no merge in progress, so the runner
commit's own git refused (`could not open '.git/MERGE_HEAD'`) or, once checkpointed
again, flattened the merged-in branch into one parent. These cases execute the
COMMITTED `fix_commit_settle` node script and the runner's exact source in a real
git fixture, with a hook that holds the runner commit open while the checkpoint is
made:

- the settle moves HEAD back to the starting head and leaves the merge in progress,
  `MERGE_HEAD` naming the merged-in commit;
- when the held commit then passes, it is a merge commit of the starting head and
  the merged-in commit;
- when the held commit fails, no merge stays in progress and the index and tracked
  files equal the starting head's tree.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_commit_runner_program import (
    COMMIT_RUNNER_PROGRAM_FILENAME,
    commit_runner_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph

_GRAPH = (
    Path(__file__).resolve().parents[2]
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "workflow.fabro"
)
_SETTLE_NODES = ("fix_commit_settle", "review_fix_commit_settle")
_WAITING_HOOK = (
    "#!/bin/sh\n"
    "printf 'lefthook v1.13.6  hook: pre-commit\\n'\n"
    "touch '{started}'\n"
    "while ! test -f '{release}'; do sleep 0.05; done\n"
    "exit {status}\n"
)


def _clean_environment() -> dict[str, str]:
    """The child environment with every GIT_ and coverage variable removed."""
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


def _write(repo: Path, name: str, text: str) -> None:
    _ = (repo / name).write_text(text, encoding="utf-8")


def _commit(repo: Path, message: str) -> None:
    _ = _git(repo, "add", "-A")
    _ = _git(repo, "commit", "--quiet", "-m", message)


def _repo(tmp_path: Path) -> Path:
    """A `work` branch (two commits) beside a `base` branch the merge brings in."""
    repo = tmp_path / "clone"
    repo.mkdir()
    _ = _git(repo, "init", "--quiet", "-b", "base")
    _ = _git(repo, "config", "user.name", "Fixture")
    _ = _git(repo, "config", "user.email", "fixture@example.invalid")
    _write(repo, "a.txt", "base\n")
    _commit(repo, "base")
    _ = _git(repo, "checkout", "--quiet", "-b", "work")
    _write(repo, "b.txt", "work one\n")
    _commit(repo, "work one")
    _write(repo, "b.txt", "work two\n")
    _commit(repo, "work two")
    _ = _git(repo, "checkout", "--quiet", "-b", "other", "base")
    _write(repo, "d.txt", "other\n")
    _commit(repo, "other")
    _ = _git(repo, "checkout", "--quiet", "work")
    return repo


def _node_script(*, node: str) -> str:
    parsed = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(parsed, str), parsed
    return parsed.nodes[node]["script"]


def _wait_for(path: Path) -> None:
    deadline = time.monotonic() + 30
    while not path.exists():
        assert time.monotonic() < deadline, f"{path} never appeared"
        time.sleep(0.05)


def _in_progress(repo: Path) -> list[str]:
    return [
        name
        for name in ("rebase-merge", "rebase-apply", "MERGE_HEAD")
        if (repo / ".git" / name).exists()
    ]


def _engine_checkpoint_of_the_merge(repo: Path) -> str:
    """The engine's per-node checkpoint: the merged index as a two-parent commit.

    It is made while the runner commit is in flight, moves HEAD past the run's
    starting head and, like any commit made during a merge, removes the merge's
    state files. Returns the merged-in commit.
    """
    merged_in = (repo / ".git" / "MERGE_HEAD").read_text(encoding="utf-8").strip()
    checkpoint = _git(
        repo, "commit-tree", _git(repo, "write-tree"), "-p", "HEAD", "-p", merged_in, "-m", "cp"
    )
    _ = _git(repo, "update-ref", "HEAD", checkpoint)
    for name in ("MERGE_HEAD", "MERGE_MSG", "MERGE_MODE"):
        (repo / ".git" / name).unlink(missing_ok=True)
    return merged_in


def _settle_with_a_held_merge_commit(
    tmp_path: Path,
    *,
    node: str,
    status: int,
    while_held: Callable[[Path, str, str], None],
) -> tuple[Path, str, str, subprocess.CompletedProcess[str]]:
    """Hold a merge commit's hook, checkpoint, settle, inspect while held, then release."""
    repo = _repo(tmp_path)
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    runner = plugins / COMMIT_RUNNER_PROGRAM_FILENAME
    _ = runner.write_text(commit_runner_program_source(), encoding="utf-8")
    started_from = _git(repo, "rev-parse", "HEAD")
    _ = _git(repo, "merge", "--no-commit", "--no-ff", "other")
    started, release = tmp_path / "hook-started", tmp_path / "hook-release"
    hook = repo / ".git" / "hooks" / "pre-commit"
    _ = hook.write_text(
        _WAITING_HOOK.format(started=started, release=release, status=status), encoding="utf-8"
    )
    hook.chmod(0o755)
    environment = {**_clean_environment(), "GIT_EDITOR": "true"}
    _ = subprocess.run(
        [sys.executable, str(runner), "start", "--", "git", "commit", "--no-edit"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    _wait_for(started)
    merged_in = _engine_checkpoint_of_the_merge(repo)
    settling = subprocess.Popen(
        ["sh", "-c", _node_script(node=node)],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={**environment, "LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT": str(plugins)},
    )
    try:
        deadline = time.monotonic() + 30
        while _git(repo, "rev-parse", "HEAD") != started_from:
            assert time.monotonic() < deadline, "settle never restored the starting head"
            time.sleep(0.05)
        while_held(repo, started_from, merged_in)
    finally:
        _ = release.write_text("go\n", encoding="utf-8")
        stdout, stderr = settling.communicate(timeout=60)
    return (
        repo,
        started_from,
        merged_in,
        subprocess.CompletedProcess(
            args=settling.args, returncode=settling.returncode, stdout=stdout, stderr=stderr
        ),
    )


def _merge_is_open_on_the_merged_in_commit(repo: Path, started_from: str, merged_in: str) -> None:
    assert _in_progress(repo) == ["MERGE_HEAD"]
    assert (repo / ".git" / "MERGE_HEAD").read_text(encoding="utf-8").strip() == merged_in
    assert _git(repo, "rev-parse", "HEAD") == started_from


@pytest.mark.parametrize("node", _SETTLE_NODES)
def test_the_settle_leaves_the_merge_in_progress_on_the_merged_in_commit(
    tmp_path: Path, node: str
) -> None:
    _ = _settle_with_a_held_merge_commit(
        tmp_path, node=node, status=0, while_held=_merge_is_open_on_the_merged_in_commit
    )


@pytest.mark.parametrize("node", _SETTLE_NODES)
def test_a_passed_runner_commit_is_a_merge_of_the_starting_head_and_the_merged_in_commit(
    tmp_path: Path, node: str
) -> None:
    repo, started_from, merged_in, _result = _settle_with_a_held_merge_commit(
        tmp_path, node=node, status=0, while_held=lambda *_: None
    )

    assert _git(repo, "rev-list", "--parents", "-n", "1", "HEAD").split()[1:] == [
        started_from,
        merged_in,
    ]
    assert _in_progress(repo) == []
    assert _git(repo, "show", "HEAD:d.txt") == "other"
    assert _git(repo, "show", "HEAD:b.txt") == "work two"


@pytest.mark.parametrize("node", _SETTLE_NODES)
def test_a_failed_runner_commit_leaves_no_merge_and_the_starting_head_s_tree(
    tmp_path: Path, node: str
) -> None:
    repo, started_from, _merged_in, _result = _settle_with_a_held_merge_commit(
        tmp_path, node=node, status=1, while_held=lambda *_: None
    )

    assert _in_progress(repo) == []
    assert _git(repo, "rev-parse", "HEAD") == started_from
    assert _git(repo, "write-tree") == _git(repo, "rev-parse", "HEAD^{tree}")
    assert _git(repo, "status", "--porcelain", "--untracked-files=no") == ""
