"""Janitor-lock tests that must hold for a NON-ROOT runner.

These exist because the janitor's own gate was red for every non-root runner
while CI's root container masked it. Two independent holes are covered here:

1. The live-process branch of the liveness probe was unreachable off-root. The
   only live-pid test probed pid 1, and `os.kill(1, 0)` raises `PermissionError`
   for an unprivileged uid -- so the probe fell through the exception path and
   the direct `return True` branch never executed. Probing OUR OWN pid is the
   privilege-independent way to reach it, but a short-circuit on
   `lock.pid == os.getpid()` prevented the probe from ever being consulted.

2. The `fcntl.flock` reclaim mutex had no coverage at all: the whole suite
   passed with it deleted, so nothing would have caught its removal.
"""

import fcntl
import json
import os
from pathlib import Path

import livespec_orchestrator_beads_fabro.commands._dispatcher_janitor_lock as janitor_lock
import pytest


def _write_lock(*, path: Path, pid: int, owner: str) -> None:
    path.write_text(
        json.dumps(
            {"pid": pid, "started_at_epoch": 1.0, "work_item_id": owner},
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def test_own_pid_lock_is_probed_for_liveness_rather_than_short_circuited(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A lock held by our own pid MUST be decided by the liveness probe.

    Short-circuiting on `lock.pid == os.getpid()` cannot change the outcome --
    the probe is always True whenever that comparison is -- but it does prevent
    the probe from running, which is what left the live-process branch
    uncovered for every non-root runner.
    """
    path = tmp_path / "janitor.lock"
    _write_lock(path=path, pid=os.getpid(), owner="bd-own-pid")
    probed: list[int] = []

    def recording_probe(*, pid: int) -> bool:
        probed.append(pid)
        return True

    monkeypatch.setattr(janitor_lock, "_pid_is_alive", recording_probe)

    detail = janitor_lock.claim_janitor_lock(path=path, owner="bd-claimant")

    assert probed == [os.getpid()]
    assert detail is not None
    assert "work-item bd-own-pid" in detail


def test_live_own_pid_lock_is_refused_through_the_real_unprivileged_probe(
    tmp_path: Path,
) -> None:
    """A live own-pid lock MUST be refused via the REAL probe, unpatched.

    This is the privilege-independent execution of the live-process branch.
    Nothing is monkeypatched, so the real probe signals our own live pid --
    which an unprivileged uid is always permitted to signal. Probing pid 1
    cannot serve the purpose off-root: that raises `PermissionError`, which the
    implementation correctly treats as "alive" via a different path, leaving
    the direct branch unexecuted.
    """
    path = tmp_path / "janitor.lock"
    original = path
    _write_lock(path=path, pid=os.getpid(), owner="bd-live-own")
    before = path.read_text(encoding="utf-8")

    detail = janitor_lock.claim_janitor_lock(path=original, owner="bd-claimant")

    assert detail is not None
    assert "work-item bd-live-own" in detail
    assert f"pid {os.getpid()}" in detail
    assert path.read_text(encoding="utf-8") == before


def test_stale_reclaim_takes_an_exclusive_flock_on_the_reclaim_mutex(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reclaiming a stale lock MUST serialize behind an exclusive reclaim mutex.

    The mutex had zero coverage: the suite passed with it deleted. This
    discriminates its presence on both halves -- the mutex file is opened, and
    an exclusive lock is taken on that file's descriptor -- so removing either
    line reddens this test rather than passing silently.
    """
    path = tmp_path / "janitor.lock"
    _write_lock(path=path, pid=999_999_999, owner="bd-stale")
    mutex_path = path.with_name(f"{path.name}.reclaim")
    real_flock = fcntl.flock
    operations: list[tuple[str, int]] = []

    def recording_flock(fd: int, operation: int) -> None:
        operations.append((str(Path(f"/proc/self/fd/{fd}").readlink()), operation))
        real_flock(fd, operation)

    monkeypatch.setattr(janitor_lock.fcntl, "flock", recording_flock)

    detail = janitor_lock.claim_janitor_lock(path=path, owner="bd-reclaimer")

    assert detail is None
    assert (str(mutex_path), fcntl.LOCK_EX) in operations
    assert mutex_path.exists()
