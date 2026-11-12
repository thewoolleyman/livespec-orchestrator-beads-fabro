"""Scenario 317 — the work-free guard compares against the default branch on origin.

The capture program never fetches into the run workspace, so a local
``refs/remotes/origin/<default>`` tracking ref goes stale as soon as the default
branch advances during a run.  This test advances origin after the workspace's
last fetch and lands the run's own tree there, so only a guard that asks origin
itself can tell that the tip carries none of the run's work.
"""

from __future__ import annotations

import importlib
import subprocess
from pathlib import Path


def test_capture_skips_a_tip_whose_tree_equals_the_default_head_on_origin(tmp_path: Path) -> None:
    """A tip matching origin's current default head, not the stale local ref, is work-free."""
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_wip_capture"
    )
    program = tmp_path / "capture-wip"
    program.write_text(module.wip_capture_program_source(), encoding="utf-8")
    program.chmod(0o755)

    origin, work = _repository(tmp_path=tmp_path)
    run = "01M6WIPDEFAULTHEAD"
    item = "bd-ib-ofvsr3"
    _git(work, "switch", "-c", f"fabro/run/{run}")
    _commit_work(work)
    tip_tree = _git_stdout(work, "rev-parse", "HEAD^{tree}")

    other = tmp_path / "other"
    subprocess.run(["git", "clone", "-q", str(origin), str(other)], check=True)
    _configure(other)
    _commit_work(other)
    _git(other, "push", "origin", "HEAD:master")
    assert _git_stdout(other, "rev-parse", "HEAD^{tree}") == tip_tree
    assert _git_stdout(work, "rev-parse", "refs/remotes/origin/master^{tree}") != tip_tree

    capture = subprocess.run(
        [str(program), item, run, "master"],
        cwd=work,
        text=True,
        capture_output=True,
        check=False,
    )

    assert capture.returncode == 0, capture.stderr
    assert "LIVESPEC_WIP_SKIPPED" in capture.stderr
    refs = _git_stdout(origin, "for-each-ref", "--format=%(refname)", f"refs/livespec/wip/{item}/")
    assert refs == ""


def _repository(*, tmp_path: Path) -> tuple[Path, Path]:
    origin = tmp_path / "origin.git"
    work = tmp_path / "work"
    subprocess.run(["git", "init", "--bare", "--initial-branch=master", str(origin)], check=True)
    work.mkdir()
    _git(work, "init", "--initial-branch=master")
    _configure(work)
    (work / "base.txt").write_text("base\n", encoding="utf-8")
    _git(work, "add", "base.txt")
    _git(work, "commit", "-m", "base")
    _git(work, "remote", "add", "origin", str(origin))
    _git(work, "push", "origin", "HEAD:master")
    _git(work, "fetch", "origin", "master")
    return origin, work


def _commit_work(repository: Path) -> None:
    (repository / "work.txt").write_text("settled work\n", encoding="utf-8")
    _git(repository, "add", "work.txt")
    _git(repository, "commit", "-m", "settled work")


def _configure(repository: Path) -> None:
    _git(repository, "config", "user.name", "Fixture")
    _git(repository, "config", "user.email", "fixture@example.invalid")


def _git(work: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=work, check=True, capture_output=True, text=True)


def _git_stdout(work: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=work, check=True, capture_output=True, text=True
    ).stdout.strip()
