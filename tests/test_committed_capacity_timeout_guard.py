"""Positive controls for the committed dispatcher capacity/timeout guard."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block

_REPO_ROOT = Path(__file__).resolve().parents[1]
_TRIPPED = pytest.fail.Exception


def test_every_direct_read_of_a_committed_capacity_or_timeout_trips() -> None:
    block = dispatcher_block(cwd=_REPO_ROOT)
    capacity = block["wip_cap"]
    timeouts = block["node_timeouts"]
    reads: tuple[Callable[[], object], ...] = (
        lambda: bool(capacity),
        lambda: capacity == 16,
        lambda: capacity != 16,
        lambda: capacity < 17,
        lambda: capacity <= 16,
        lambda: capacity > 15,
        lambda: capacity >= 16,
        lambda: repr(capacity),
        lambda: capacity + 1,
        lambda: 1 + capacity,
        lambda: capacity - 1,
        lambda: 1 - capacity,
        lambda: capacity * 2,
        lambda: 2 * capacity,
        lambda: timeouts["dod_gate"],
        lambda: iter(timeouts),
        lambda: len(timeouts),
        lambda: "dod_gate" in timeouts,
        lambda: timeouts == {},
        lambda: timeouts != {},
        lambda: bool(timeouts),
        lambda: repr(timeouts),
        lambda: timeouts.get("dod_gate"),
        lambda: timeouts.items(),
        lambda: timeouts.keys(),
        lambda: timeouts.values(),
        lambda: timeouts.copy(),
    )

    for read in reads:
        with pytest.raises(_TRIPPED, match="COMMITTED dispatcher capacity or timeout"):
            _ = read()
