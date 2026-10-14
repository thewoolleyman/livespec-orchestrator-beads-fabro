"""Inventory-lock retries use a clock independent of thread scheduling."""

from __future__ import annotations

import fcntl
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._session_wait_lock import (
    LockBudget,
    wait_store_lock,
)


@pytest.mark.parametrize(
    ("deadline", "expected_sleeps"),
    [
        (0.005, [0.005]),
        (0.025, [0.01, 0.01, 0.005]),
    ],
)
def test_contended_lock_sleeps_until_injected_deadline(
    *, tmp_path: Path, deadline: float, expected_sleeps: list[float]
) -> None:
    now = 0.0
    sleeps: list[float] = []

    def sleep(*, seconds: float) -> None:
        nonlocal now
        assert 0 < seconds <= 0.01
        sleeps.append(seconds)
        now += seconds

    budget = LockBudget(deadline=deadline, monotonic=lambda: now, sleeper=sleep)
    # Hold a separate file descriptor throughout: every nonblocking attempt
    # must be refused, and only the injected sleeper can expire the deadline.
    with (tmp_path / ".inventory.lock").open("a", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            with wait_store_lock(wait_store_root=tmp_path, budget=budget) as acquired:
                assert acquired is False
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    assert sleeps == pytest.approx(expected_sleeps)
    assert now == pytest.approx(deadline)
