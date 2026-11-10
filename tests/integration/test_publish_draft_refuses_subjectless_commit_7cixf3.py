"""Scenario 202 (work-item bd-ib-7cixf3) — publish_draft never publishes a commit with no authored subject.

A factory commit whose first message line is a trailer line (or empty) is not
rejected by the repository's range gate, and under rebase-merge it lands on the
default branch as it stands. The `publish_draft` node is the last stage before the
branch becomes a pull request, so it refuses there. These cases execute the committed
node script in a local git fixture with a real bare origin:

- a branch carrying such a commit is not pushed, the output names that commit, and
  the failure routes to `fix` through the classifier with a brief naming the commit;
- a branch carrying no such commit is pushed exactly as before.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import (
    DotGraph,
    parse_dot_graph,
)

_WORKFLOW = Path(".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro")
_PUBLISH_BRANCH = "feat/bd-ib-7cixf3"
_TRAILER_ONLY = "Factory-Run-Id: c5d75329655c48dd8307828b4e79e03c\nTDD-Suite-Green-Verified-At: x\n"


def _git(cwd: Path, *argv: str) -> str:
    result = subprocess.run(
        ["git", *argv], cwd=str(cwd), check=True, text=True, capture_output=True
    )
    return result.stdout.strip()


def _graph() -> DotGraph:
    parsed = parse_dot_graph(text=_WORKFLOW.read_text(encoding="utf-8"))
    assert not isinstance(parsed, str), parsed
    return parsed


def _script(*, node: str) -> str:
    return _graph().nodes[node]["script"].replace("{{ inputs.default_branch }}", "master")


def _sandbox(*, tmp_path: Path, message: str) -> Path:
    origin = tmp_path / "origin.git"
    _ = _git(tmp_path, "init", "--bare", "-b", "master", str(origin))
    work = tmp_path / "work"
    work.mkdir()
    _ = _git(work, "init", "-b", "master")
    _ = _git(work, "config", "user.name", "subjectless-test")
    _ = _git(work, "config", "user.email", "subjectless-test@example.invalid")
    _ = (work / "base.txt").write_text("base\n", encoding="utf-8")
    _ = _git(work, "add", "base.txt")
    _ = _git(work, "commit", "-m", "base")
    _ = _git(work, "remote", "add", "origin", str(origin))
    _ = _git(work, "push", "-u", "origin", "master")
    _ = _git(work, "switch", "-c", "fabro/run/subjectless")
    _ = (work / "change.txt").write_text("change\n", encoding="utf-8")
    _ = _git(work, "add", "change.txt")
    _ = _git(work, "commit", "-m", "feat: an authored subject")
    _ = (work / "second.txt").write_text("second\n", encoding="utf-8")
    _ = _git(work, "add", "second.txt")
    _ = _git(work, "commit", "--allow-empty-message", "-m", message)
    return work


def _env(*, tmp_path: Path) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    _ = gh.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
    env = {
        key: value
        for key, value in os.environ.items()
        if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE")
    }
    env.update(
        {
            "PATH": f"{bin_dir}{os.pathsep}{env.get('PATH', '')}",
            "LIVESPEC_GIT_AUTHOR_NAME": "Subjectless Test",
            "LIVESPEC_GIT_AUTHOR_EMAIL": "subjectless-test@example.invalid",
            "LIVESPEC_PUBLISH_BRANCH": _PUBLISH_BRANCH,
        }
    )
    return env


def _publish(*, work: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sh", "-c", _script(node="publish_draft")],
        cwd=str(work),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _pushed(*, work: Path) -> str:
    return _git(work, "ls-remote", "origin", f"refs/heads/{_PUBLISH_BRANCH}")


def test_a_trailer_subject_commit_is_not_pushed_and_routes_to_fix_naming_it(
    tmp_path: Path,
) -> None:
    work = _sandbox(tmp_path=tmp_path, message=_TRAILER_ONLY)
    subjectless = _git(work, "rev-parse", "HEAD")
    env = _env(tmp_path=tmp_path)

    publish = _publish(work=work, env=env)

    assert publish.returncode != 0
    assert _pushed(work=work) == ""
    assert subjectless in publish.stderr
    assert "no authored subject line" in publish.stderr
    edges = {(edge.source, edge.destination) for edge in _graph().edges}
    assert ("publish_draft", "refresh_repair") in edges
    assert ("refresh_repair", "fix") in edges
    routed = subprocess.run(
        ["sh", "-c", _script(node="refresh_repair")],
        cwd=str(work),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert routed.returncode == 0, routed.stderr
    assert subjectless in routed.stderr
    assert _git(work, "rev-parse", "HEAD") == subjectless


def test_an_empty_subject_commit_is_not_pushed_either(tmp_path: Path) -> None:
    work = _sandbox(tmp_path=tmp_path, message="")
    emptied = _git(work, "rev-parse", "HEAD")

    publish = _publish(work=work, env=_env(tmp_path=tmp_path))

    assert publish.returncode != 0
    assert _pushed(work=work) == ""
    assert emptied in publish.stderr


def test_a_branch_with_authored_subjects_is_pushed_as_before(tmp_path: Path) -> None:
    work = _sandbox(tmp_path=tmp_path, message="fix: a second authored subject\n\nTDD-Note: y\n")
    head = _git(work, "rev-parse", "HEAD")

    publish = _publish(work=work, env=_env(tmp_path=tmp_path))

    assert publish.returncode == 0, publish.stderr
    assert "SUBJECTLESS" not in publish.stderr
    assert _pushed(work=work).split()[0] == head
