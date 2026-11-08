"""Scenario 317 — capture settled run-branch work on immutable WIP refs.

The capture program is Dispatcher materialized beside ``push_origin`` rather
than authored in a run workspace.  This test executes it against a bare origin
so a ref's name, object, immutability, and the workspace's untouched state are
all observable rather than inferred from the workflow text.
"""

from __future__ import annotations

import importlib
import subprocess
from pathlib import Path

_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_wip_capture.py"
)


def test_capture_program_preserves_only_a_work_carrying_run_branch_tip(tmp_path: Path) -> None:
    """The first capture is immutable, hookless, and leaves its workspace untouched."""
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_wip_capture"
    )
    program = tmp_path / "capture-wip"
    program.write_text(module.wip_capture_program_source(), encoding="utf-8")
    program.chmod(0o755)

    origin, work = _repository(tmp_path=tmp_path)
    run = "01M6WIPCAPTURE"
    item = "bd-ib-ofvsr3"
    _git(work, "switch", "-c", f"fabro/run/{run}")
    (work / "work.txt").write_text("settled work\n", encoding="utf-8")
    _git(work, "add", "work.txt")
    _git(work, "commit", "-m", "settled work")
    tip = _git_stdout(work, "rev-parse", "HEAD")
    before = _workspace_state(work)

    first = _run(program=program, work=work, item=item, run=run)
    ref = f"refs/livespec/wip/{item}/{run}/1"

    assert first.returncode == 0, first.stderr
    assert _git_stdout(origin, "rev-parse", ref) == tip
    assert _workspace_state(work) == before
    assert f"LIVESPEC_WIP_CAPTURED: {ref} {tip}" in first.stderr

    repeated = _run(program=program, work=work, item=item, run=run)

    assert repeated.returncode == 0, repeated.stderr
    assert _refs(origin, prefix=f"refs/livespec/wip/{item}/{run}/") == [ref]
    assert f"LIVESPEC_WIP_SKIPPED: {ref} {tip} already captured" in repeated.stderr


def _repository(*, tmp_path: Path) -> tuple[Path, Path]:
    origin = tmp_path / "origin.git"
    work = tmp_path / "work"
    subprocess.run(["git", "init", "--bare", "--initial-branch=master", str(origin)], check=True)
    work.mkdir()
    _git(work, "init", "--initial-branch=master")
    _git(work, "config", "user.name", "Fixture")
    _git(work, "config", "user.email", "fixture@example.invalid")
    (work / "base.txt").write_text("base\n", encoding="utf-8")
    _git(work, "add", "base.txt")
    _git(work, "commit", "-m", "base")
    _git(work, "remote", "add", "origin", str(origin))
    _git(work, "push", "origin", "HEAD:master")
    _git(work, "fetch", "origin", "master")
    return origin, work


def _run(*, program: Path, work: Path, item: str, run: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(program), item, run, "master"],
        cwd=work,
        text=True,
        capture_output=True,
        check=False,
    )


def _workspace_state(work: Path) -> tuple[str, str, str]:
    return (
        _git_stdout(work, "rev-parse", "HEAD"),
        _git_stdout(work, "diff", "--cached", "--binary"),
        _git_stdout(work, "status", "--porcelain=v1"),
    )


def _refs(origin: Path, *, prefix: str) -> list[str]:
    return _git_stdout(origin, "for-each-ref", "--format=%(refname)", prefix).splitlines()


def _git(work: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=work, check=True, capture_output=True, text=True)


def _git_stdout(work: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=work, check=True, capture_output=True, text=True
    ).stdout.strip()
