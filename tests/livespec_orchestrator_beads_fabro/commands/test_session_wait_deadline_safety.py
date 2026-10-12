"""Real deadline and probe-cancellation safety for bounded session waits."""

from __future__ import annotations

import fcntl
import os
import signal
import threading
import time
from contextlib import suppress
from pathlib import Path
from typing import cast

import pytest
from livespec_orchestrator_beads_fabro.commands._session_wait_types import ProbeLauncher
from livespec_orchestrator_beads_fabro.commands.session_wait import (
    GateStatusLauncher,
    GateTarget,
    WaitRequest,
    run_wait,
)


def _wait_for_file(*, path: Path, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    while not path.exists() and time.monotonic() < deadline:
        time.sleep(0.005)
    assert path.is_file()


def test_waiting_for_a_file_that_never_appears_refuses_at_the_deadline(*, tmp_path: Path) -> None:
    """The wait POLLS to a bounded deadline and then refuses, rather than hanging.

    This is the other arm of `_wait_for_file`, and only this test can reach it.
    The probe below publishes its pid through a POSIX shell that starts in
    milliseconds, so the file is already there on the first condition check and
    the polling body is never entered — the arm that matters when a probe dies
    before publishing anything is the one that must still terminate. Elapsed
    time is asserted rather than left to a coverage report, so a loop that
    stopped waiting (or never waited) fails here instead of passing silently.
    """
    started = time.monotonic()

    with pytest.raises(AssertionError):
        _wait_for_file(path=tmp_path / "never-written", timeout_seconds=0.05)

    assert time.monotonic() - started >= 0.05


def test_registration_lock_is_inside_the_original_deadline(*, tmp_path: Path) -> None:
    wait_store_root = tmp_path / "session-waits"
    wait_store_root.mkdir()
    returned = threading.Event()
    result_outcomes: list[str] = []

    def invoke_wait() -> None:
        result = run_wait(
            request=WaitRequest(
                wait_id="lock-bound",
                session_id="deadline-safety",
                repository=tmp_path,
                deadline_seconds=0.05,
                targets=(),
            ),
            launcher=cast("ProbeLauncher", object()),
            wait_store_root=wait_store_root,
        )
        result_outcomes.append(result.command_outcome)
        returned.set()

    lock_path = wait_store_root / ".inventory.lock"
    with lock_path.open("a", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        worker = threading.Thread(target=invoke_wait)
        worker.start()
        returned_by_bound = returned.wait(timeout=0.2)
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    worker.join(timeout=1.0)

    assert returned_by_bound is True
    assert result_outcomes == ["deadline"]
    assert worker.is_alive() is False


def test_cancelling_probe_terminates_probe_child_only(*, tmp_path: Path) -> None:
    gate_store_root = tmp_path / "gate-runs"
    gate_dir = gate_store_root / "synthetic-gate"
    gate_dir.mkdir(parents=True)
    _ = (gate_dir / "started_at").write_text("generation-one\n", encoding="utf-8")
    target = GateTarget.freeze(gate_store_root=gate_store_root, run_id=gate_dir.name)
    pid_file = tmp_path / "probe.pid"
    # A POSIX-SHELL probe rather than a Python one, because `launch` clamps its
    # budget to `min(1.0, ...)` and a cold CPython cannot reach its first
    # statement inside one second while the suite runs under coverage tracing
    # on a loaded host — the probe was reaped before it ever published its pid,
    # so this test failed on `_wait_for_file` for a reason that was never about
    # the code under test. The semantics it asserts are preserved exactly: the
    # trap is armed BEFORE the pid is published, so SIGTERM is already ignored
    # by the time the test can read the pid; `exec` then replaces the shell in
    # place, so the published pid stays the live process's own pid and process
    # group, and an ignored disposition survives `exec` per POSIX. Cancellation
    # must therefore still escalate past SIGTERM to kill it.
    helper = tmp_path / "sleeping-probe.sh"
    _ = helper.write_text(
        """trap '' TERM
echo $$ > "$1"
exec sleep 30
""",
        encoding="utf-8",
    )
    probe = GateStatusLauncher(
        repository=tmp_path,
        command_prefix=("/bin/sh", str(helper), str(pid_file)),
    ).launch(target=target, timeout_seconds=1.0)
    assert probe.poll(now=time.monotonic()) is None
    _wait_for_file(path=pid_file, timeout_seconds=1.0)
    probe_pid = int(pid_file.read_text(encoding="utf-8"))

    probe.cancel(timeout_seconds=0.05)
    time.sleep(0.1)
    probe_alive = Path(f"/proc/{probe_pid}").exists()
    with suppress(ProcessLookupError):
        os.kill(probe_pid, signal.SIGKILL)
    assert probe_alive is False
    assert probe.active is False
    assert (gate_dir / "started_at").read_text(encoding="utf-8") == "generation-one\n"
