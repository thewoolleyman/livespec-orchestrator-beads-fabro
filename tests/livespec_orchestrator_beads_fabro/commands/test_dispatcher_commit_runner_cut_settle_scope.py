"""The cut-settle pass ends only git operations in its own repository.

Work-item `bd-ib-ptnxyg`, Scenario 192. The pass terminates processes, and a factory
host (or a test host) runs git commits that belong to no cut turn: the commit hook of
the very suite exercising this program is one. A git commit with a hook run under it
whose working directory lies OUTSIDE the directory the pass was started in must be
neither named nor touched, while the same shape inside it is the event.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_commit_runner_program import (
    COMMIT_RUNNER_PROGRAM_FILENAME,
    commit_runner_program_source,
)

_TICKS = os.sysconf("SC_CLK_TCK")


def _program(tmp_path: Path) -> dict[str, Any]:
    namespace: dict[str, Any] = {"__name__": "livespec_commit_runner_under_test"}
    code = compile(
        commit_runner_program_source(), str(tmp_path / COMMIT_RUNNER_PROGRAM_FILENAME), "exec"
    )
    exec(code, namespace)  # noqa: S102 — the materialized program's exact source, in-process
    runs = tmp_path / "runs"
    runs.mkdir()

    def git_output(*argv: str) -> str:
        del argv
        return str(runs)

    namespace["git_output"] = git_output
    return namespace


def _commit_with_hook(proc: Path, *, pid: int, cwd: Path) -> None:
    for offset, argv in enumerate((["git", "commit"], ["sh", ".git/hooks/pre-commit"])):
        entry = proc / str(pid + offset)
        entry.mkdir(parents=True)
        ppid = 1 if offset == 0 else pid
        fields = ["S", str(ppid), str(pid), str(pid)] + ["0"] * 15 + [str(500 * _TICKS)]
        _ = (entry / "stat").write_text(
            f"{pid + offset} (git) {' '.join(fields)}", encoding="utf-8"
        )
        _ = (entry / "cmdline").write_bytes(b"\0".join(a.encode() for a in argv) + b"\0")
        (entry / "cwd").symlink_to(cwd)


def _signals(proc: Path) -> tuple[list[int], Any]:
    sent: list[int] = []

    def terminate(pid: int, signal_number: int) -> None:
        del signal_number
        sent.append(pid)
        shutil.rmtree(proc / str(pid), ignore_errors=True)

    return sent, terminate


def test_a_commit_in_another_directory_tree_is_neither_named_nor_touched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Scenario 192: only the pass's own repository is its business."""
    mine, elsewhere = tmp_path / "mine", tmp_path / "elsewhere"
    mine.mkdir()
    elsewhere.mkdir()
    monkeypatch.chdir(mine)
    program = _program(tmp_path)
    proc = tmp_path / "proc"
    proc.mkdir()
    _ = (proc / "uptime").write_text("1000.00 4000.00\n", encoding="utf-8")
    _commit_with_hook(proc, pid=500, cwd=elsewhere)
    sent, program["terminate"] = _signals(proc)

    assert program["cut_settle"](0, str(proc)) == 0

    assert "LIVESPEC_NODE_CUT_HOOK_RUN" not in capsys.readouterr().err
    assert sent == []


def test_the_same_commit_in_a_subdirectory_of_the_repository_is_the_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Scenario 192: the control — a hook run under the pass's directory is named and ended."""
    mine = tmp_path / "mine"
    (mine / "sub").mkdir(parents=True)
    monkeypatch.chdir(mine)
    program = _program(tmp_path)
    proc = tmp_path / "proc"
    proc.mkdir()
    _ = (proc / "uptime").write_text("1000.00 4000.00\n", encoding="utf-8")
    _commit_with_hook(proc, pid=600, cwd=mine / "sub")
    sent, program["terminate"] = _signals(proc)

    assert program["cut_settle"](0, str(proc)) == 0

    assert "LIVESPEC_NODE_CUT_HOOK_RUN: operation=commit hook_elapsed_ms=500000" in (
        capsys.readouterr().err
    )
    assert set(sent) >= {600, 601}
