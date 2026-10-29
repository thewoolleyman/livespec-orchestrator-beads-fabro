"""The commit runner's pass for a turn a node timeout cut: wait, stop, name, reap.

Work-item `bd-ib-ptnxyg`; `SPECIFICATION/contracts.md` "A commit run outlives a
node-timeout cut" and "Repository hooks that outlive a limit", Scenario 192. The
`needs_human` node runs this pass before its preservation commit. These cases load
the materialized program's exact source into a fresh namespace and replace its
clock, its signal sender and its process table with fakes, for the reason the
sibling program tests give: `check-tests-no-subprocess-spawn` forbids a real spawn.

What they pin is the clause's own vocabulary. A run that passes inside the bounded
wait is named `passed`; a run still running when the bound ends is stopped BEFORE
anything else happens and is named `no-verdict`; a git commit or push whose hook
run is still executing is named as a hook run and every process of it is
terminated; and a git commit with no hook run under it is neither named nor
touched, because that is not a hook-over-limit event.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_commit_runner_program import (
    COMMIT_RUNNER_PROGRAM_FILENAME,
    commit_runner_program_source,
)

_RUN_ID = "commit-00000000000000000000000000000002"
_TICKS = os.sysconf("SC_CLK_TCK")


class _Clock:
    """A monotonic clock that only moves when the program sleeps."""

    def __init__(self, *, on_sleep: Any = None) -> None:
        self.now = 0.0
        self.sleeps = 0
        self._on_sleep = on_sleep

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps += 1
        self.now += seconds
        if self._on_sleep is not None:
            self._on_sleep(self.sleeps)


def _program(tmp_path: Path, *, clock: _Clock | None = None) -> dict[str, Any]:
    namespace: dict[str, Any] = {"__name__": "livespec_commit_runner_under_test"}
    code = compile(
        commit_runner_program_source(),
        str(tmp_path / COMMIT_RUNNER_PROGRAM_FILENAME),
        "exec",
    )
    exec(code, namespace)  # noqa: S102 — the materialized program's exact source, in-process
    answers = {("rev-parse", "--git-path", "livespec-commit-runs"): str(tmp_path / "runs")}

    def git_output(*argv: str) -> str:
        return answers[argv]

    namespace["git_output"] = git_output
    namespace["time"] = clock or _Clock()
    return namespace


def _assert_has_cut_settle(program: dict[str, Any]) -> None:
    assert "cut_settle" in program, "the runner has no pass for a turn a node timeout cut"


def _record(tmp_path: Path, record: dict[str, object], *, pid: int | None) -> Path:
    path = tmp_path / "runs" / f"{_RUN_ID}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(json.dumps(record), encoding="utf-8")
    if pid is not None:
        _ = path.with_suffix(".pid").write_text(f"{pid}\n", encoding="utf-8")
    return path


def _process(
    proc: Path,
    *,
    pid: int,
    ppid: int,
    argv: list[str],
    start_seconds: float,
    group: int | None = None,
) -> None:
    (proc / str(pid)).mkdir(parents=True)
    own = str(pid if group is None else group)
    fields = ["S", str(ppid), own, own] + ["0"] * 15 + [str(int(start_seconds * _TICKS))]
    _ = (proc / str(pid) / "stat").write_text(f"{pid} (git) {' '.join(fields)}", encoding="utf-8")
    _ = (proc / str(pid) / "cmdline").write_bytes(b"\0".join(a.encode() for a in argv) + b"\0")


def _always_alive(group: int, proc_root: str = "/proc") -> bool:
    del group, proc_root
    return True


def _signals(proc: Path) -> tuple[list[tuple[int, int]], Any]:
    """A signal sender that records every signal and makes the process vanish."""
    sent: list[tuple[int, int]] = []

    def terminate(pid: int, signal_number: int) -> None:
        sent.append((pid, signal_number))
        shutil.rmtree(proc / str(pid), ignore_errors=True)

    return sent, terminate


def test_a_run_that_passes_inside_the_bounded_wait_is_named_passed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Scenario 192: the passed run is named, and nothing is stopped."""
    path = _record(tmp_path, {"state": "running"}, pid=4242)

    def finish(sleeps: int) -> None:
        del sleeps
        _ = path.write_text(json.dumps({"state": "passed", "exit_code": 0}), encoding="utf-8")

    program = _program(tmp_path, clock=_Clock(on_sleep=finish))
    _assert_has_cut_settle(program)
    program["group_alive"] = _always_alive
    proc = tmp_path / "proc"
    proc.mkdir()
    sent, program["terminate"] = _signals(proc)

    assert program["cut_settle"](60, str(proc)) == 0

    assert f"LIVESPEC_NODE_CUT_COMMIT_RUN: run={_RUN_ID} state=passed" in capsys.readouterr().err
    assert sent == []


def test_a_run_still_running_at_the_bound_is_stopped_and_named_no_verdict(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Scenario 192: stopped before preservation, recorded and named no-verdict."""
    path = _record(tmp_path, {"state": "running"}, pid=4242)
    program = _program(tmp_path)
    _assert_has_cut_settle(program)
    proc = tmp_path / "proc"
    _process(proc, pid=4242, ppid=1, argv=["python3", "runner.py", "worker"], start_seconds=1)
    _process(proc, pid=4250, ppid=4242, argv=["sleep", "9"], start_seconds=1, group=4242)
    sent, program["terminate"] = _signals(proc)

    def alive(group: int, proc_root: str = "/proc") -> bool:
        del group, proc_root
        return any((proc / name).is_dir() for name in ("4242", "4250"))

    program["group_alive"] = alive

    assert program["cut_settle"](5, str(proc)) == 0

    assert (
        f"LIVESPEC_NODE_CUT_COMMIT_RUN: run={_RUN_ID} state=no-verdict" in capsys.readouterr().err
    )
    assert {pid for pid, _ in sent} == {4242, 4250}
    assert signal.SIGTERM in {number for _, number in sent}
    assert json.loads(path.read_text(encoding="utf-8"))["state"] == "no-verdict"


def test_a_run_that_already_ended_is_named_without_waiting(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Scenario 192: an earlier terminal run is named with its own state and costs no wait."""
    _ = _record(tmp_path, {"state": "failed", "exit_code": 1}, pid=None)
    clock = _Clock()
    program = _program(tmp_path, clock=clock)
    _assert_has_cut_settle(program)
    proc = tmp_path / "proc"
    proc.mkdir()

    assert program["cut_settle"](60, str(proc)) == 0

    assert f"LIVESPEC_NODE_CUT_COMMIT_RUN: run={_RUN_ID} state=failed" in capsys.readouterr().err
    assert clock.sleeps == 0


def test_an_in_turn_commit_with_a_hook_run_still_executing_is_named_and_reaped(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Scenario 192: the hook run is named with its elapsed time and every process is ended."""
    program = _program(tmp_path)
    _assert_has_cut_settle(program)
    proc = tmp_path / "proc"
    proc.mkdir()
    _ = (proc / "uptime").write_text("1000.00 4000.00\n", encoding="utf-8")
    _process(proc, pid=100, ppid=1, argv=["git", "commit", "-m", "x"], start_seconds=700)
    _process(proc, pid=101, ppid=100, argv=["sh", ".git/hooks/pre-commit"], start_seconds=705)
    _process(proc, pid=102, ppid=101, argv=["just", "check"], start_seconds=706)
    sent, program["terminate"] = _signals(proc)

    assert program["cut_settle"](0, str(proc)) == 0

    assert "LIVESPEC_NODE_CUT_HOOK_RUN: operation=commit hook_elapsed_ms=295000" in (
        capsys.readouterr().err
    )
    assert {pid for pid, _ in sent} >= {100, 101, 102}


def test_a_push_with_a_hook_run_still_executing_is_named_a_push(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Scenario 192: the operation is the git subcommand, and the hook is matched by name."""
    program = _program(tmp_path)
    _assert_has_cut_settle(program)
    proc = tmp_path / "proc"
    proc.mkdir()
    _ = (proc / "uptime").write_text("500.00 900.00\n", encoding="utf-8")
    _process(proc, pid=200, ppid=1, argv=["git", "-c", "a=b", "push", "origin"], start_seconds=400)
    _process(proc, pid=201, ppid=200, argv=["lefthook", "run", "pre-push"], start_seconds=410)
    _, program["terminate"] = _signals(proc)

    assert program["cut_settle"](0, str(proc)) == 0

    assert "operation=push hook_elapsed_ms=90000" in capsys.readouterr().err


def test_a_commit_with_no_hook_run_under_it_is_neither_named_nor_touched(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Scenario 192: a commit ended before its hook started is not a hook-over-limit event."""
    program = _program(tmp_path)
    _assert_has_cut_settle(program)
    proc = tmp_path / "proc"
    proc.mkdir()
    _ = (proc / "uptime").write_text("1000.00 4000.00\n", encoding="utf-8")
    _process(proc, pid=300, ppid=1, argv=["git", "commit", "-m", "x"], start_seconds=900)
    _process(proc, pid=301, ppid=1, argv=["git", "status"], start_seconds=900)
    _process(proc, pid=302, ppid=1, argv=["sleep", "pre-commit"], start_seconds=900)
    sent, program["terminate"] = _signals(proc)

    assert program["cut_settle"](0, str(proc)) == 0

    assert "LIVESPEC_NODE_CUT_HOOK_RUN" not in capsys.readouterr().err
    assert sent == []


def test_the_cut_settle_operation_is_reachable_from_the_command_line(tmp_path: Path) -> None:
    """`cut-settle --timeout-seconds N` is the spelling the needs_human node invokes."""
    program = _program(tmp_path)
    _assert_has_cut_settle(program)
    calls: list[float] = []

    def cut_settle(timeout_seconds: float, proc_root: str = "/proc") -> int:
        del proc_root
        calls.append(timeout_seconds)
        return 0

    program["cut_settle"] = cut_settle

    assert program["main"](["cut-settle", "--timeout-seconds", "12"], "/runner.py") == 0
    assert calls == [12.0]
