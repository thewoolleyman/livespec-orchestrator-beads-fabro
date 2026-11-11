"""The H2 headings read from `origin/master`'s governed spec tree (work-item bd-ib-ahtcng).

`test_dispatcher_definition_of_done_origin_revision.py` shows the wall admitting
and refusing against a lagging primary. These cases are the reader's own: what
counts as a heading of the tree, and every way the remote revision can fail to be
read. The read runs against real git repositories for the same reason that file
gives, and the three failure arms a real repository cannot produce on demand (a
git that will not launch, a listing that fails after a fetch that worked, a file
that vanishes between the listing and the read) are driven through a stand-in
for the one `subprocess.run` seam.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_definition_of_done_origin_spec as origin_spec,
)

_GIT = (
    "git",
    "-c",
    "user.name=t",
    "-c",
    "user.email=t@example.invalid",
    "-c",
    "commit.gpgsign=false",
)


def _clean_environment() -> dict[str, str]:
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment["GIT_CONFIG_GLOBAL"] = os.devnull
    return environment


def _run(*args: str, cwd: Path) -> None:
    _ = subprocess.run(
        [*_GIT, *args], cwd=cwd, check=True, capture_output=True, env=_clean_environment()
    )


def _clone_of_origin_carrying(*, tmp_path: Path, files: dict[str, str]) -> Path:
    """A clone whose origin's master carries exactly `files` (repo-relative path to text)."""
    origin = tmp_path / "origin.git"
    seed = tmp_path / "seed"
    clone = tmp_path / "clone"
    _run("init", "--bare", "-b", "master", str(origin), cwd=tmp_path)
    _run("init", "-b", "master", str(seed), cwd=tmp_path)
    _run("remote", "add", "origin", str(origin), cwd=seed)
    for relative, text in files.items():
        target = seed / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        _ = target.write_text(text, encoding="utf-8")
    _ = (seed / "README.md").write_text("# Readme\n\n## Not spec\n", encoding="utf-8")
    _run("add", "-A", cwd=seed)
    _run("commit", "-m", "revise", cwd=seed)
    _run("push", "origin", "HEAD:refs/heads/master", cwd=seed)
    _run("clone", str(origin), str(clone), cwd=tmp_path)
    return clone


def test_the_headings_are_the_h2_lines_of_the_top_level_spec_files_in_prefixed_form(
    tmp_path: Path,
) -> None:
    clone = _clone_of_origin_carrying(
        tmp_path=tmp_path,
        files={
            "SPECIFICATION/contracts.md": "# Contracts\n\n## First clause\n\n### Not an H2\n",
            "SPECIFICATION/scenarios.md": "# Scenarios\n\n##   Second clause   \n",
            "SPECIFICATION/history/v001/contracts.md": "## Historical clause\n",
            "SPECIFICATION/notes.txt": "## Not markdown\n",
        },
    )

    headings = origin_spec.origin_spec_h2_headings(repo=clone)

    assert headings == frozenset({"## First clause", "## Second clause"})


def test_a_tree_with_no_spec_directory_reads_as_an_empty_set(tmp_path: Path) -> None:
    clone = _clone_of_origin_carrying(tmp_path=tmp_path, files={})

    assert origin_spec.origin_spec_h2_headings(repo=clone) == frozenset()


def test_a_non_object_canonical_branch_config_falls_back_to_origin_head(tmp_path: Path) -> None:
    clone = _clone_of_origin_carrying(
        tmp_path=tmp_path, files={"SPECIFICATION/contracts.md": "## Clause\n"}
    )
    _ = (clone / ".livespec.jsonc").write_text("[]\n", encoding="utf-8")

    assert origin_spec.origin_spec_h2_headings(repo=clone) == frozenset({"## Clause"})


def test_the_read_ignores_an_ambient_git_dir_pointing_elsewhere(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clone = _clone_of_origin_carrying(
        tmp_path=tmp_path, files={"SPECIFICATION/contracts.md": "## Clause\n"}
    )
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "elsewhere"))
    monkeypatch.setenv("GIT_WORK_TREE", str(tmp_path / "elsewhere"))

    assert origin_spec.origin_spec_h2_headings(repo=clone) == frozenset({"## Clause"})


def test_an_origin_that_cannot_be_fetched_is_unreadable_and_named(tmp_path: Path) -> None:
    clone = _clone_of_origin_carrying(
        tmp_path=tmp_path, files={"SPECIFICATION/contracts.md": "## Clause\n"}
    )
    _run("remote", "set-url", "origin", str(tmp_path / "gone.git"), cwd=clone)

    result = origin_spec.origin_spec_h2_headings(repo=clone)

    assert isinstance(result, origin_spec.OriginSpecUnreadable)
    assert "`git fetch` exited" in result.detail


def test_a_directory_that_is_not_a_repository_is_unreadable(tmp_path: Path) -> None:
    standalone = tmp_path / "standalone"
    standalone.mkdir()
    _run("init", "-b", "master", str(standalone), cwd=tmp_path)

    result = origin_spec.origin_spec_h2_headings(repo=standalone)

    assert isinstance(result, origin_spec.OriginSpecUnreadable)


def test_a_git_that_will_not_launch_is_unreadable(monkeypatch: pytest.MonkeyPatch) -> None:
    def _no_launch(*_args: object, **_kwargs: object) -> object:
        raise FileNotFoundError("git")

    monkeypatch.setattr(origin_spec.subprocess, "run", _no_launch)

    result = origin_spec.origin_spec_h2_headings(repo=Path())

    assert isinstance(result, origin_spec.OriginSpecUnreadable)
    assert "`git fetch` could not run" in result.detail


def _scripted_git(*, failing: str, listing: str) -> object:
    """A `subprocess.run` stand-in whose every git step succeeds except `failing`."""

    def _run_step(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        step = argv[3]
        if step == failing:
            return subprocess.CompletedProcess(argv, 128, stdout="", stderr=f"{step} broke\n")
        stdout = listing if step == "ls-tree" else ""
        return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")

    return _run_step


def test_a_listing_that_fails_after_the_fetch_is_unreadable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(origin_spec.subprocess, "run", _scripted_git(failing="ls-tree", listing=""))

    result = origin_spec.origin_spec_h2_headings(repo=Path())

    assert result == origin_spec.OriginSpecUnreadable(
        detail="`git ls-tree` exited 128: ls-tree broke"
    )


def test_a_file_that_cannot_be_read_after_it_was_listed_is_unreadable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        origin_spec.subprocess,
        "run",
        _scripted_git(failing="show", listing="SPECIFICATION/contracts.md\n"),
    )

    result = origin_spec.origin_spec_h2_headings(repo=Path())

    assert result == origin_spec.OriginSpecUnreadable(detail="`git show` exited 128: show broke")
