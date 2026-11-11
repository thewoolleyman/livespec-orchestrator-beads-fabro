"""Scenario 199 (work-item bd-ib-gisyvv) — a re-entered turn's Green amend amends the open Red.

An open-Red re-entry (`fix_open_red_route`, `review_fix_open_red_route`, or
`implement_hook_route` after a settled open Red) sends the stage back to finish
the Green amend of a Red commit that is already complete. Between that Red and
the re-entered turn, the engine writes one checkpoint commit per stage: some
are tree-empty, and some carry the implementation the previous turn left staged.
The re-entered turn's `git commit --amend --no-edit` therefore amended the TOP
CHECKPOINT, not the open Red, and the repository's pairing hook refused it.
Measured on 2026-11-11 on livespec-dev-tooling-hmztez, -5lhafp and -a4w7qr
(build 8348582ab).

These cases run the runner's exact source in a real git fixture:

- an amend started through the runner over engine checkpoints above an open Red
  amends that Red, and the amended commit carries the checkpoints' tree changes;
- the runner names the fold on standard error;
- it folds nothing when HEAD is the open Red itself, when the commit under the
  checkpoints is a completed Red-Green commit, when a checkpoint in the chain
  is a merge, or when the commit is not an amend.
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

_RED_MESSAGE = (
    "feat: classify the declared key\n\n"
    "TDD-Red-Test-File: tests/test_widget.py\n"
    "TDD-Red-Test-File-Checksum: sha256:0000\n"
)
_GREEN_MESSAGE = _RED_MESSAGE + "TDD-Green-Verified-At: 2026-11-11T00:00:00Z\n"
# One checkpoint subject per stage the engine runs between the open Red and the
# re-entered turn, for each of the three re-entry routes.
_ROUTE_CHECKPOINTS = {
    "fix_open_red_route": ("fix", "fix_commit_settle", "fix_open_red_route"),
    "review_fix_open_red_route": (
        "review_fix",
        "review_fix_commit_settle",
        "review_fix_open_red_route",
    ),
    "implement_hook_route": ("implement", "implement_commit_settle", "implement_hook_route"),
}


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
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(text, encoding="utf-8")


def _commit(repo: Path, message: str, *, allow_empty: bool = False) -> str:
    _ = _git(repo, "add", "-A")
    extra = ("--allow-empty",) if allow_empty else ()
    _ = _git(repo, "commit", "--quiet", *extra, "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _checkpoint(repo: Path, node: str) -> str:
    return _commit(repo, f"fabro(01M7TESTRUN0000000000000000): {node} (success)", allow_empty=True)


def _repo(tmp_path: Path, *, red_message: str = _RED_MESSAGE) -> tuple[Path, str, str]:
    """A base commit and a Red commit adding the test; returns (repo, base, red)."""
    repo = tmp_path / "clone"
    repo.mkdir()
    _ = _git(repo, "init", "--quiet", "-b", "work")
    _ = _git(repo, "config", "user.name", "Fixture")
    _ = _git(repo, "config", "user.email", "fixture@example.invalid")
    _write(repo, "a.txt", "base\n")
    base = _commit(repo, "base")
    _write(repo, "tests/test_widget.py", "def test_widget():\n    assert False\n")
    red = _commit(repo, red_message)
    return repo, base, red


def _checkpoints_above(repo: Path, nodes: tuple[str, ...]) -> None:
    """The engine's per-stage checkpoints: the first tree-empty, the second carrying the impl."""
    _ = _checkpoint(repo, nodes[0])
    _write(repo, "widget.py", "def widget():\n    return 1\n")
    _ = _checkpoint(repo, nodes[1])
    _ = _checkpoint(repo, nodes[2])


def _stage_a_change(repo: Path) -> None:
    """Stage a change, so an amend of the top commit is not refused as empty."""
    _write(repo, "staged.txt", "staged\n")
    _ = _git(repo, "add", "-A")


def _amend_through_the_runner(
    tmp_path: Path, repo: Path, *argv: str
) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    runner = tmp_path / COMMIT_RUNNER_PROGRAM_FILENAME
    _ = runner.write_text(commit_runner_program_source(), encoding="utf-8")
    environment = {**_clean_environment(), "GIT_EDITOR": "true"}
    started = subprocess.run(
        [sys.executable, str(runner), "start", "--", "git", "commit", *argv],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    run_id = started.stdout.strip().splitlines()[-1]
    waited = subprocess.run(
        [sys.executable, str(runner), "wait", run_id, "--timeout-seconds", "60"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    return started, json.loads(waited.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("route", sorted(_ROUTE_CHECKPOINTS))
def test_a_reentered_green_amend_amends_the_open_red_and_carries_the_checkpoints(
    tmp_path: Path, route: str
) -> None:
    repo, base, _red = _repo(tmp_path)
    _checkpoints_above(repo, _ROUTE_CHECKPOINTS[route])

    started, report = _amend_through_the_runner(tmp_path, repo, "--amend", "--no-edit")

    assert report["state"] == "passed", report
    assert _git(repo, "rev-parse", "HEAD^") == base
    assert _git(repo, "log", "--format=%s", f"{base}..HEAD").splitlines() == [
        "feat: classify the declared key"
    ]
    assert "TDD-Red-Test-File-Checksum: sha256:0000" in _git(repo, "log", "-1", "--format=%B")
    assert _git(repo, "show", "HEAD:widget.py") == "def widget():\n    return 1"
    assert "LIVESPEC_COMMIT_RUNNER_FOLDED_CHECKPOINTS" in started.stderr


def test_an_amend_with_the_open_red_at_head_folds_nothing(tmp_path: Path) -> None:
    repo, base, _red = _repo(tmp_path)
    _write(repo, "widget.py", "def widget():\n    return 1\n")
    _ = _git(repo, "add", "-A")

    started, report = _amend_through_the_runner(tmp_path, repo, "--amend", "--no-edit")

    assert report["state"] == "passed", report
    assert _git(repo, "rev-parse", "HEAD^") == base
    assert "LIVESPEC_COMMIT_RUNNER_FOLDED_CHECKPOINTS" not in started.stderr


def test_checkpoints_above_a_completed_red_green_commit_are_not_folded(tmp_path: Path) -> None:
    repo, _base, green = _repo(tmp_path, red_message=_GREEN_MESSAGE)
    _checkpoints_above(repo, _ROUTE_CHECKPOINTS["fix_open_red_route"])
    below_top = _git(repo, "rev-parse", "HEAD^")
    _stage_a_change(repo)

    started, report = _amend_through_the_runner(tmp_path, repo, "--amend", "--no-edit")

    assert report["state"] == "passed", report
    assert _git(repo, "rev-parse", "HEAD^") == below_top
    assert _git(repo, "merge-base", "--is-ancestor", green, "HEAD") == ""
    assert "LIVESPEC_COMMIT_RUNNER_FOLDED_CHECKPOINTS" not in started.stderr


def test_a_merge_checkpoint_in_the_chain_stops_the_fold(tmp_path: Path) -> None:
    repo, _base, red = _repo(tmp_path)
    side = _git(repo, "commit-tree", _git(repo, "rev-parse", "HEAD^{tree}"), "-m", "side")
    merge = _git(
        repo,
        "commit-tree",
        _git(repo, "rev-parse", "HEAD^{tree}"),
        "-p",
        red,
        "-p",
        side,
        "-m",
        "fabro(01M7TESTRUN0000000000000000): fix (success)",
    )
    _ = _git(repo, "update-ref", "HEAD", merge)
    _ = _checkpoint(repo, "fix_open_red_route")
    below_top = _git(repo, "rev-parse", "HEAD^")
    _stage_a_change(repo)

    started, report = _amend_through_the_runner(tmp_path, repo, "--amend", "--no-edit")

    assert report["state"] == "passed", report
    assert _git(repo, "rev-parse", "HEAD^") == below_top
    assert "LIVESPEC_COMMIT_RUNNER_FOLDED_CHECKPOINTS" not in started.stderr


def test_a_commit_that_is_not_an_amend_folds_nothing(tmp_path: Path) -> None:
    repo, _base, _red = _repo(tmp_path)
    _checkpoints_above(repo, _ROUTE_CHECKPOINTS["fix_open_red_route"])
    top = _git(repo, "rev-parse", "HEAD")
    _write(repo, "more.txt", "more\n")
    _ = _git(repo, "add", "-A")

    started, report = _amend_through_the_runner(tmp_path, repo, "-m", "chore: more")

    assert report["state"] == "passed", report
    assert _git(repo, "rev-parse", "HEAD^") == top
    assert "LIVESPEC_COMMIT_RUNNER_FOLDED_CHECKPOINTS" not in started.stderr
