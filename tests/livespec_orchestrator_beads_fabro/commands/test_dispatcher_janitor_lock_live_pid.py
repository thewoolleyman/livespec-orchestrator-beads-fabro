"""Live-PID janitor lock coverage tests."""

import json
import os
from pathlib import Path

import livespec_orchestrator_beads_fabro.commands._dispatcher_janitor_lock as janitor_lock
import pytest


def test_claim_janitor_lock_refuses_live_foreign_pid_lock_without_rewriting_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Two conditions must BOTH hold to reach `_pid_is_alive`'s live-process branch,
    # and a hardcoded `pid: 1` met neither for a non-root user:
    #   - the PID must not be our own, because the caller short-circuits on
    #     `lock.pid == os.getpid()` before consulting `_pid_is_alive` at all; and
    #   - `os.kill(pid, 0)` must SUCCEED, whereas signalling init as uid != 0 raises
    #     PermissionError, so the branch returned through AttemptFailure instead.
    # That left the live-process branch covered only when the suite ran as root,
    # making `just check` privilege-dependent -- green in CI, red for every non-root
    # developer. Faking the probe pins the branch deterministically for both, and
    # spawning a real process is not an option (`check-tests-no-subprocess-spawn`).
    foreign_pid = os.getpid() + 1
    probed: list[tuple[int, int]] = []

    def fake_kill(pid: int, signal: int) -> None:
        probed.append((pid, signal))

    monkeypatch.setattr(os, "kill", fake_kill)

    path = tmp_path / "janitor.lock"
    original = (
        json.dumps(
            {
                "pid": foreign_pid,
                "started_at_epoch": 1.0,
                "work_item_id": "bd-live",
            },
            sort_keys=True,
        )
        + "\n"
    )
    path.write_text(original, encoding="utf-8")

    detail = janitor_lock.claim_janitor_lock(path=path, owner="bd-new")

    # The liveness probe is a signal-0 existence check against the lock's own PID,
    # never a real signal delivery.
    assert probed == [(foreign_pid, 0)]
    assert detail is not None
    assert "work-item bd-live" in detail
    assert f"pid {foreign_pid}" in detail
    assert path.read_text(encoding="utf-8") == original
