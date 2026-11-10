"""Scenario 202 (work-item bd-ib-7cixf3) — a commit with no authored subject line is not a commit.

A repository's commit-msg hook may append a `Factory-Run-Id:` trailer to the message
file. Git runs that hook BEFORE its empty-message check, so a commit attempted with an
EMPTY message is no longer empty when git looks, and it is created with the trailer as
its whole message. These cases execute the runner's exact source in a real git fixture
whose commit-msg hook appends such a trailer:

- an empty authored message settles the commit run FAILED, leaves HEAD at the head the
  run started from, and the run's brief names the commit as having no authored subject
  line;
- a non-empty authored message yields a commit whose first line is the authored subject
  with the appended trailer after it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

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
_TRAILER_HOOK = (
    "#!/bin/sh\n"
    'git interpret-trailers --in-place --trailer "Factory-Run-Id: 0123456789abcdef" "$1"\n'
)


def _environment() -> dict[str, str]:
    """The child environment with every GIT_ and coverage variable removed."""
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("GIT_", "COV_CORE", "COVERAGE"))
    }
    return {**environment, "GIT_EDITOR": "true", "GIT_CONFIG_GLOBAL": "/dev/null"}


def _git(repo: Path, *argv: str) -> str:
    result = subprocess.run(
        ["git", *argv],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        env=_environment(),
    )
    return result.stdout.strip()


def _repo(tmp_path: Path) -> Path:
    """A repository on `work` with one commit, a staged file and a trailer-appending hook."""
    repo = tmp_path / "clone"
    repo.mkdir()
    _ = _git(repo, "init", "--quiet", "-b", "work")
    _ = _git(repo, "config", "user.name", "Fixture")
    _ = _git(repo, "config", "user.email", "fixture@example.invalid")
    _ = (repo / "a.txt").write_text("a\n", encoding="utf-8")
    _ = _git(repo, "add", "-A")
    _ = _git(repo, "commit", "--quiet", "-m", "base")
    hook = repo / ".git" / "hooks" / "commit-msg"
    _ = hook.write_text(_TRAILER_HOOK, encoding="utf-8")
    hook.chmod(0o755)
    _ = (repo / "b.txt").write_text("b\n", encoding="utf-8")
    _ = _git(repo, "add", "-A")
    return repo


def _plugins(tmp_path: Path) -> Path:
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    _ = (plugins / COMMIT_RUNNER_PROGRAM_FILENAME).write_text(
        commit_runner_program_source(), encoding="utf-8"
    )
    return plugins


def _runner(repo: Path, plugins: Path, *argv: str) -> str:
    result = subprocess.run(
        [sys.executable, str(plugins / COMMIT_RUNNER_PROGRAM_FILENAME), *argv],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        env=_environment(),
    )
    return result.stdout.strip()


def _commit_run(repo: Path, plugins: Path, *message: str) -> dict[str, object]:
    run_id = _runner(repo, plugins, "start", "--", "git", "commit", *message)
    report = _runner(repo, plugins, "wait", run_id, "--timeout-seconds", "60")
    return json.loads(report.splitlines()[-1])


def _settle_brief(repo: Path, plugins: Path) -> str:
    parsed = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(parsed, str), parsed
    environment = {**_environment(), "LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT": str(plugins)}
    _ = subprocess.run(
        ["sh", "-c", parsed.nodes["implement_commit_settle"]["script"]],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    brief = repo / ".git" / "livespec-implement-live-commit"
    return brief.read_text(encoding="utf-8") if brief.exists() else ""


def test_an_empty_authored_message_settles_failed_and_leaves_head_where_it_began(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    plugins = _plugins(tmp_path)
    started_from = _git(repo, "rev-parse", "HEAD")

    report = _commit_run(repo, plugins, "-m", "")

    assert report["state"] == "failed"
    assert _git(repo, "rev-parse", "HEAD") == started_from
    assert "no authored subject line" in str(report["output_tail"])
    brief = _settle_brief(repo, plugins)
    assert brief.startswith("failed\n")
    assert "no authored subject line" in brief


def test_a_non_empty_authored_message_keeps_its_subject_ahead_of_the_trailer(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    plugins = _plugins(tmp_path)

    report = _commit_run(repo, plugins, "-m", "feat: authored subject")

    assert report["state"] == "passed"
    message = _git(repo, "log", "-1", "--format=%B").splitlines()
    assert message[0] == "feat: authored subject"
    assert message[-1] == "Factory-Run-Id: 0123456789abcdef"
