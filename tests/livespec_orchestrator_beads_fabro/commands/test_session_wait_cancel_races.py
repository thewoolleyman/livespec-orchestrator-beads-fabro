"""Cancellation must not raise when a probe task wins the race against it.

`run_wait` cancels every probe on EVERY return path, including the successful
first-event one. So a cancel that raises does not merely fail to cancel — it
discards a bounded result that had already been computed, and reports the whole
wait as a crash. These cases pin the three ways the task can win that race.

The happy path (a live probe child, killed, gate untouched) is covered by
`test_session_wait_deadline_safety`; this module covers only the races.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._session_wait_gate import (
    GateStatusLauncher,
    _CommandTask,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_types import GateTarget

# A probe command that completes immediately, so its worker thread exits while
# the probe still holds the task.
_FAST_PROBE = (
    "sh",
    "-c",
    "echo '  state             : FAILED'; echo '  exit_code         : 23'",
)


def _target(*, gate_store_root: Path, run_id: str) -> GateTarget:
    run_dir = gate_store_root / run_id
    run_dir.mkdir(parents=True)
    _ = (run_dir / "started_at").write_text("generation-one\n", encoding="utf-8")
    frozen = GateTarget.freeze(gate_store_root=gate_store_root, run_id=run_id)
    assert frozen is not None
    return frozen


def _raised_by(action: object) -> str | None:
    """Run a no-argument callable, returning the exception name it raised."""
    assert callable(action)
    try:
        action()
    except BaseException as exc:  # noqa: BLE001 - "it raises" is the finding
        return f"{type(exc).__name__}: {exc}"
    return None


def test_cancelling_a_probe_whose_task_already_finished_does_not_raise(
    *,
    tmp_path: Path,
) -> None:
    """A sibling finishing between the last poll and cancel is not a fault.

    Its `/proc/<pid>/task/<tid>/` directory is gone by then, and an exited task
    has already reaped the child it spawned, so there is nothing left to kill.
    """
    target = _target(gate_store_root=tmp_path / "gate-runs", run_id="finished-early")
    probe = GateStatusLauncher(
        repository=tmp_path,
        command_prefix=_FAST_PROBE,
    ).launch(target=target, timeout_seconds=1.0)

    assert probe.poll(now=time.monotonic()) is None
    # Let the worker run to completion WITHOUT polling again, so the probe
    # still holds a task whose thread has exited.
    time.sleep(1.0)

    assert _raised_by(lambda: probe.cancel(timeout_seconds=1.0)) is None
    assert probe.active is False


def test_cancelling_a_task_that_never_became_ready_does_not_raise(
    *,
    tmp_path: Path,
) -> None:
    """A zero cancellation budget at deadline expiry has no thread id to scan.

    `run_wait` cancels with `max(0.0, deadline - monotonic())`, which is 0.0 at
    expiry, so `ready.wait` can return before the worker has published its
    native thread id. Building a `/proc` path out of that absence is what
    raised.
    """
    target = _target(gate_store_root=tmp_path / "gate-runs", run_id="never-ready")
    task = _CommandTask(
        target=target,
        command_prefix=("sh", "-c", "sleep 30"),
        observed_at=1.0,
        timeout_seconds=1.0,
    )

    assert task.native_thread_id is None
    assert _raised_by(lambda: task.cancel(timeout_seconds=0.0)) is None


def test_a_task_cancelled_before_it_runs_spawns_no_probe_child(
    *,
    tmp_path: Path,
) -> None:
    """Skipping the kill for an unready task is only sound if none was spawned.

    Cancellation that lands before the worker reaches its probe must stop the
    worker from starting one, or the skip above would leave a live child behind
    while reporting a clean cancellation.
    """
    target = _target(gate_store_root=tmp_path / "gate-runs", run_id="cancelled-early")
    witness = tmp_path / "probe-ran.witness"
    task = _CommandTask(
        target=target,
        command_prefix=("sh", "-c", f"touch {witness}", "--"),
        observed_at=1.0,
        timeout_seconds=1.0,
    )
    task.cancel_requested = True

    task.start()
    assert task.thread is not None
    task.thread.join(timeout=5.0)

    assert task.thread.is_alive() is False
    assert witness.exists() is False
    assert task.result is None
    assert sys.executable  # the probe is a shell, not this interpreter
