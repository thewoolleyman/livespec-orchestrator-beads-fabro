"""The two cancellation guards, each asserted in BOTH directions.

A guard that tolerates an absence is one edit away from tolerating a blindness,
and the two have opposite consequences: an absent task directory means the
child is already reaped, while an unreadable one means nobody looked. So each
guard is pinned on the arm it must swallow AND on the arm it must still raise —
a test that only covered the tolerant arm would pass just as happily against a
bare `except OSError: return ()`.

⚠ THE REFUSED-KILL ARM IS ASSERTED THROUGH A SEAM, AND MUST STAY THAT WAY.
The obvious live control — `_kill_probe_group(pid=1)`, expecting
`PermissionError` because pid 1 "is not ours" — is BOTH unsafe and wrong, and
it destroyed the run that first wrote it (hp run 01M4PPNRBBRX95J1FVC0BNHT9G,
native ACP exit 137 = SIGKILL). Unsafe because this suite runs as root inside a
container, where the kill is NOT refused: `killpg(1, ...)` signals process
GROUP 1, and a worker sharing that group kills itself. Wrong because root's
kill raises nothing at all, so the assertion could only ever fail — after the
signal had already landed. A stdlib seam asserts the real contract ("only
`ProcessLookupError` is swallowed") deterministically and signals nothing.
NEVER signal pid 1, or any process this test did not itself create.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._session_wait_gate import (
    _kill_probe_group,
    _probe_task_dir,
    _thread_child_pids,
)

from tests.livespec_orchestrator_beads_fabro.commands.test_session_wait_cancel_races import (
    _raised_by,
)


def test_an_exited_task_has_no_children_but_a_blind_read_still_raises(
    *,
    tmp_path: Path,
) -> None:
    absent = tmp_path / "task-that-exited"
    assert _thread_child_pids(task_dir=absent) == ()

    present_but_unreadable = tmp_path / "task-still-alive"
    present_but_unreadable.mkdir()
    with pytest.raises(OSError, match="children"):
        _ = _thread_child_pids(task_dir=present_but_unreadable)

    readable = tmp_path / "task-with-children"
    readable.mkdir()
    _ = (readable / "children").write_text("4321 8765 \n", encoding="utf-8")
    assert _thread_child_pids(task_dir=readable) == (4321, 8765)


def test_this_threads_task_directory_is_the_one_proc_reports() -> None:
    own = _probe_task_dir(native_thread_id=os.getpid())
    assert own == Path(f"/proc/{os.getpid()}/task/{os.getpid()}")
    assert own.is_dir()
    assert (own / "children").is_file()


def _refuse_every_kill(*captured: int) -> None:
    """Stand in for `os.killpg` as the kernel would answer a REFUSED kill.

    Positional because it substitutes a stdlib-owned name through
    `monkeypatch.setattr` below, which is that calling convention's exemption
    from the keyword-only rule.
    """
    assert len(captured) == 2
    raise PermissionError(1, "Operation not permitted")


def test_a_vanished_probe_group_is_tolerated_but_a_refused_kill_is_not(
    *,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A child of THIS test, started in its own session and then reaped, is
    # exactly what a probe child exiting before the signal looks like — a real
    # observation of the race, which is why this arm is not a seam.
    child = subprocess.Popen(["sh", "-c", "exit 0"], start_new_session=True)
    own_pid = child.pid
    assert child.wait() == 0
    _kill_probe_group(pid=own_pid)

    # The opposite arm: a kill the kernel REFUSES says the group is live and
    # unreachable, not that it has gone, so it must not be swallowed. See this
    # module's docstring for why this is a seam and never a live signal.
    monkeypatch.setattr(os, "killpg", _refuse_every_kill)
    with pytest.raises(PermissionError):
        _kill_probe_group(pid=own_pid)


def test_the_race_modules_raise_detector_actually_reports_a_raise() -> None:
    """A positive control on the instrument the three race cases measure with.

    `_raised_by` is how `test_session_wait_cancel_races` decides that cancelling
    did not raise, and every one of its assertions is `is None`. So an instrument
    that returned `None` unconditionally — for a raising callable as readily as a
    clean one — would make all three pass VACUOUSLY against the very defect they
    exist to catch. Its reporting arm is unreachable from that module once the
    guards hold, which is precisely why the control belongs here: proving the
    detector CAN return a hit is what makes its three misses evidence.
    """
    assert _raised_by(lambda: None) is None

    def _raise_permission_error() -> None:
        raise PermissionError(1, "Operation not permitted")

    reported = _raised_by(_raise_permission_error)
    assert reported is not None
    assert reported.startswith("PermissionError: ")
