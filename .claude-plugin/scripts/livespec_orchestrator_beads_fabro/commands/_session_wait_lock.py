"""Deadline-aware serialization for the durable session-wait inventory."""

from __future__ import annotations

import fcntl
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TypeVar

__all__: list[str] = [
    "LockBudget",
    "LockSleeper",
    "run_with_wait_store_lock",
    "wait_store_lock",
]

_Value = TypeVar("_Value")


class LockSleeper(Protocol):
    def __call__(self, *, seconds: float) -> None: ...


@dataclass(frozen=True, kw_only=True)
class LockBudget:
    deadline: float
    monotonic: Callable[[], float]
    sleeper: LockSleeper


@contextmanager
def wait_store_lock(
    *,
    wait_store_root: Path,
    budget: LockBudget | None = None,
) -> Iterator[bool]:
    """Acquire the inventory lock without extending a supplied deadline."""
    wait_store_root.mkdir(parents=True, exist_ok=True)
    with (wait_store_root / ".inventory.lock").open("a", encoding="utf-8") as lock_file:
        acquired = False
        try:
            if budget is None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                acquired = True
            else:
                while not acquired:
                    try:
                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        acquired = True
                    except BlockingIOError:
                        remaining = budget.deadline - budget.monotonic()
                        if remaining <= 0:
                            yield False
                            return
                        budget.sleeper(seconds=min(0.01, remaining))
            yield True
        finally:
            if acquired:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def run_with_wait_store_lock(
    *,
    wait_store_root: Path,
    budget: LockBudget | None,
    action: Callable[[], _Value],
) -> _Value | None:
    """Run one mutation under the inventory lock, or report deadline expiry."""
    with wait_store_lock(wait_store_root=wait_store_root, budget=budget) as acquired:
        return action() if acquired else None
