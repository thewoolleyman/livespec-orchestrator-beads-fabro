"""Which release tags a repository carries, read from a real git repository.

Covers `_plan_release_tags`. The read is driven against a REAL `git init`
repository rather than a stubbed runner, because the whole value of the module
is that it agrees with what git reports: a stubbed `git tag --list` would prove
only that the parse handles whatever bytes the test supplied.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _plan_release_tags
from livespec_orchestrator_beads_fabro.commands._plan_release_tags import (
    release_tags_argv,
    repository_release_tags,
)


def _git(*, cwd: Path, args: list[str]) -> None:
    _ = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        check=True,
    )


def test_a_tagged_repository_reports_every_tag_and_an_untagged_one_reports_none(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(cwd=repo, args=["init", "--quiet"])
    _git(cwd=repo, args=["config", "user.email", "fixture@example.invalid"])
    _git(cwd=repo, args=["config", "user.name", "Fixture"])
    _ = (repo / "README.md").write_text("fixture\n", encoding="utf-8")
    _git(cwd=repo, args=["add", "README.md"])
    _git(cwd=repo, args=["commit", "--quiet", "--no-verify", "-m", "chore: fixture"])

    # The untagged control FIRST, on the same repository: without it, "the tags
    # were read" is equally consistent with a reader that returns a fixed set.
    assert repository_release_tags(project_root=repo) == frozenset()

    _git(cwd=repo, args=["tag", "v0.1.0"])
    _git(cwd=repo, args=["tag", "v0.2.0"])

    assert repository_release_tags(project_root=repo) == frozenset({"v0.1.0", "v0.2.0"})


def test_a_directory_that_is_no_repository_reports_no_tags(tmp_path: Path) -> None:
    # git exits non-zero here, which is the measured "this is not a repository"
    # answer rather than a parse of empty output.
    assert repository_release_tags(project_root=tmp_path / "absent") == frozenset()


def test_an_unrunnable_git_reports_no_tags_rather_than_raising(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(*_args: object, **_kwargs: object) -> object:
        raise OSError("git is not on PATH")

    monkeypatch.setattr(_plan_release_tags.subprocess, "run", refuse)

    # The UNMEASURED direction the module docstring records: it waives the
    # release-identity half of the rule and never the proof leg itself.
    assert repository_release_tags(project_root=tmp_path) == frozenset()


def test_the_published_argv_is_the_read_that_runs(tmp_path: Path) -> None:
    seen: list[list[str]] = []

    def record(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        seen.append(argv)
        return subprocess.CompletedProcess(args=argv, returncode=1, stdout="", stderr="")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(_plan_release_tags.subprocess, "run", record)
        _ = repository_release_tags(project_root=tmp_path)

    # The published argv is what a caller's journal cites, so it has to be the
    # one that ran rather than a reconstruction that might differ from it.
    assert seen == [release_tags_argv(project_root=tmp_path)]
