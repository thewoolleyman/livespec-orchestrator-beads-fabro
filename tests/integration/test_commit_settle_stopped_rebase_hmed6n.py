"""Scenario 176 (work-item bd-ib-hmed6n) — a settle whose rebase stops again hands the turn back.

A fix turn that resolves one conflicting pick of a refresh rebase commits the
resolution through the runner and ends with the rebase still in progress. The
commit-settle node's `git rebase --continue` then applies the remaining picks and
can stop on a LATER conflicting pick. The node used to journal only that the
continue "did not complete" and return success, so the graph routed the passed
settle on to the janitor, which failed on the leftover `rebase-merge` directory
and sent the run round the same loop until its visit limit. These cases execute the
COMMITTED node script and the runner's exact source in a real git fixture:

- a passed commit run whose continue stops on a later conflicting pick fails the
  `fix` settle with a live-commit brief naming that pick and every conflicted path,
  and leaves the rebase in progress at the pick with the settled commit reachable;
- a continue, a rebase abort or a merge abort that does not complete journals git's
  own error output.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
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
_BANNER_HOOK = "#!/bin/sh\nprintf 'lefthook v1.13.6  hook: pre-commit\\n'\nexit {status}\n"
_SHIM = (
    "#!/bin/sh\n"
    'if test "$1" = {subcommand} && test "$2" = --abort; then\n'
    "  echo 'fatal: shim refuses the abort' >&2\n"
    "  exit 128\n"
    "fi\n"
    'exec {git} "$@"\n'
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


def _do(repo: Path, *argv: str) -> None:
    _ = _git(repo, *argv)


def _write(repo: Path, name: str, text: str) -> None:
    _ = (repo / name).write_text(text, encoding="utf-8")


def _commit(repo: Path, message: str) -> None:
    _do(repo, "add", "-A")
    _do(repo, "commit", "--quiet", "-m", message)


def _repo(tmp_path: Path) -> Path:
    """A `work` branch whose first and third commits each conflict with `side`."""
    repo = tmp_path / "clone"
    repo.mkdir()
    _do(repo, "init", "--quiet", "-b", "base")
    _do(repo, "config", "user.name", "Fixture")
    _do(repo, "config", "user.email", "fixture@example.invalid")
    _write(repo, "a.txt", "base\n")
    _write(repo, "c.txt", "base\n")
    _write(repo, "d.txt", "base\n")
    _commit(repo, "base")
    _do(repo, "checkout", "--quiet", "-b", "side")
    _write(repo, "a.txt", "side\n")
    _write(repo, "c.txt", "side\n")
    _write(repo, "d.txt", "side\n")
    _commit(repo, "side")
    _do(repo, "checkout", "--quiet", "base")
    _do(repo, "checkout", "--quiet", "-b", "work")
    _write(repo, "a.txt", "work\n")
    _commit(repo, "work one")
    _write(repo, "b.txt", "work two\n")
    _commit(repo, "work two")
    _write(repo, "c.txt", "work\n")
    _write(repo, "d.txt", "work\n")
    _commit(repo, "work three")
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


def _run_commit(repo: Path, plugins: Path) -> dict[str, object]:
    run_id = _runner(repo, plugins, "start", "--", "git", "commit", "--no-edit")
    report = _runner(repo, plugins, "wait", run_id, "--timeout-seconds", "60")
    return json.loads(report.splitlines()[-1])


def _stop_on_first_pick(repo: Path) -> None:
    """Start the refresh rebase, stop on pick one, and stage a resolution of it."""
    result = subprocess.run(
        ["git", "rebase", "side"],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        env=_clean_environment(),
    )
    assert result.returncode != 0, result.stdout
    _write(repo, "a.txt", "resolved\n")
    _do(repo, "add", "a.txt")


def _settle(
    repo: Path, plugins: Path, *, path_prefix: Path | None = None
) -> subprocess.CompletedProcess[str]:
    parsed = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(parsed, str), parsed
    environment = {**_clean_environment(), "LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT": str(plugins)}
    if path_prefix is not None:
        environment["PATH"] = f"{path_prefix}{os.pathsep}{environment['PATH']}"
    return subprocess.run(
        ["sh", "-c", parsed.nodes["fix_commit_settle"]["script"]],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


def _in_progress(repo: Path) -> list[str]:
    names = ("rebase-merge", "rebase-apply", "MERGE_HEAD")
    return [name for name in names if (repo / ".git" / name).exists()]


def test_a_continue_that_stops_on_a_later_pick_fails_the_settle_with_a_brief(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    plugins = _plugins(tmp_path)
    _stop_on_first_pick(repo)
    _hook(repo, status=0)
    report = _run_commit(repo, plugins)
    assert report["state"] == "passed"
    settled = str(report["head"])

    result = _settle(repo, plugins)

    assert result.returncode != 0, result.stderr
    brief = (repo / ".git" / "livespec-fix-live-commit").read_text(encoding="utf-8")
    assert brief.startswith("failed\n")
    assert "work three" in brief
    assert _git(repo, "rev-parse", "--short", "REBASE_HEAD") in brief
    assert "c.txt" in brief
    assert "d.txt" in brief
    assert "a.txt" not in brief.replace("c.txt", "").replace("d.txt", "")
    assert "rebase-merge" in _in_progress(repo)
    _do(repo, "merge-base", "--is-ancestor", settled, "HEAD")
    assert _git(repo, "show", "HEAD:b.txt") == "work two"
    assert "CONFLICT" in result.stderr


def test_a_continue_that_stops_leaves_the_pick_for_the_next_turn_to_finish(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    plugins = _plugins(tmp_path)
    _stop_on_first_pick(repo)
    _hook(repo, status=0)
    _ = _run_commit(repo, plugins)
    _ = _settle(repo, plugins)

    _write(repo, "c.txt", "resolved\n")
    _write(repo, "d.txt", "resolved\n")
    _do(repo, "add", "c.txt", "d.txt")
    report = _run_commit(repo, plugins)
    assert report["state"] == "passed"
    result = _settle(repo, plugins)

    assert result.returncode == 0, result.stderr
    assert _in_progress(repo) == []
    assert _git(repo, "rev-parse", "--abbrev-ref", "HEAD") == "work"
    assert _git(repo, "show", "HEAD:c.txt") == "resolved"


@pytest.mark.parametrize("operation", ["rebase", "merge"])
def test_an_abort_that_does_not_complete_journals_gits_own_error_output(
    tmp_path: Path, operation: str
) -> None:
    repo = _repo(tmp_path)
    plugins = _plugins(tmp_path)
    if operation == "rebase":
        _stop_on_first_pick(repo)
    else:
        _do(repo, "checkout", "--quiet", "-b", "other", "base")
        _write(repo, "a.txt", "other\n")
        _commit(repo, "other")
        _do(repo, "checkout", "--quiet", "work")
        merge = subprocess.run(
            ["git", "merge", "--no-commit", "other"],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
            env=_clean_environment(),
        )
        assert merge.returncode != 0, merge.stdout
        _write(repo, "a.txt", "resolved\n")
        _do(repo, "add", "a.txt")
    _hook(repo, status=1)
    report = _run_commit(repo, plugins)
    assert report["state"] == "failed"
    shim_directory = tmp_path / "shim"
    shim_directory.mkdir()
    shim = shim_directory / "git"
    git = shutil.which("git")
    assert git is not None
    _ = shim.write_text(_SHIM.format(subcommand=operation, git=git), encoding="utf-8")
    shim.chmod(0o755)

    result = _settle(repo, plugins, path_prefix=shim_directory)

    assert "LIVESPEC_COMMIT_SETTLE_OPERATION_UNRESOLVED" in result.stderr
    assert f"git {operation} --abort" in result.stderr
    assert "fatal: shim refuses the abort" in result.stderr
