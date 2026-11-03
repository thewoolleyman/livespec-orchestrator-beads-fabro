"""Failure backoff for a Dispatcher's Fabro event reads."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

__all__: list[str] = ["BoundedEventsReader"]

_FIRST_FAILURE_BACKOFF_SECONDS = 60.0


class EventsCommand(Protocol):
    """The command facts that establish whether a read was observable."""

    @property
    def exit_code(self) -> int: ...

    @property
    def stdout(self) -> str: ...


class EventsCommandRead(Protocol):
    """Run an events command within its caller's remaining budget."""

    def __call__(self, *, timeout_seconds: float) -> EventsCommand: ...


@dataclass(frozen=True, kw_only=True)
class _ReadKey:
    caller: str
    run_id: str


@dataclass(kw_only=True)
class _FailureState:
    attempts: int
    retry_after: float


@dataclass(kw_only=True)
class BoundedEventsReader:
    """Back off failures by caller and run, and journal each attempted failure."""

    journal: Callable[[dict[str, object]], None]
    clock: Callable[[], float] = time.monotonic
    _failures: dict[_ReadKey, _FailureState] = field(default_factory=dict)

    def read(
        self,
        *,
        work_item_id: str,
        run_id: str,
        factory: str,
        caller: str,
        timeout_seconds: float,
        read: EventsCommandRead,
    ) -> EventsCommand | None:
        """Read once when its backoff permits, else return an unobservable result."""
        key = _ReadKey(caller=caller, run_id=run_id)
        started = self.clock()
        previous = self._failures.get(key)
        if previous is not None and started < previous.retry_after:
            return None
        command = read(timeout_seconds=timeout_seconds)
        elapsed = self.clock() - started
        if command.exit_code == 0 and command.stdout != "":
            _ = self._failures.pop(key, None)
            return command
        attempts = 1 if previous is None else previous.attempts + 1
        backoff = _FIRST_FAILURE_BACKOFF_SECONDS * 2 ** (attempts - 1)
        self._failures[key] = _FailureState(
            attempts=attempts,
            retry_after=self.clock() + backoff,
        )
        self.journal(
            {
                "stage": "fabro-events-read-failed",
                "work_item_id": work_item_id,
                "run_id": run_id,
                "factory": factory,
                "caller": caller,
                "elapsed_seconds": elapsed,
                "consecutive_attempt": attempts,
                "backoff_seconds": backoff,
            }
        )
        return command
