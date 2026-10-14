"""Deterministic retry coverage for the session-wait inventory lock."""

from __future__ import annotations

import fcntl
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._session_wait_lock import (
    LockBudget,
    wait_store_lock,
)


@pytest.mark.parametrize("deadline", [0.005, 0.025])
def test_contended_lock_sleeps_until_injected_deadline(*, tmp_path: Path, deadline: float) -> None:
    """Reach retry sleep without depending on thread start latency or wall time."""
    now = 0.0
    sleeps: list[float] = []

    def monotonic() -> float:
        return now

    def sleeper(*, seconds: float) -> None:
        nonlocal now
        assert 0 < seconds <= 0.01
        assert seconds <= deadline - now
        sleeps.append(seconds)
        now += seconds

    budget = LockBudget(deadline=deadline, monotonic=monotonic, sleeper=sleeper)
    with (tmp_path / ".inventory.lock").open("a", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        # Only the injected sleeper advances time, so the first refused flock
        # always has budget remaining, however loaded the host is.
        with wait_store_lock(wait_store_root=tmp_path, budget=budget) as acquired:
            assert acquired is False

    assert sleeps, "lock contention must sleep before the deadline expires"
    assert now == pytest.approx(deadline)
