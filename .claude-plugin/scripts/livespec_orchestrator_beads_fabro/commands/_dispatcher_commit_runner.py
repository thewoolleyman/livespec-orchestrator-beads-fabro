"""The fake-driven state machine that waits on a detached commit process.

A bounded wait is an observation, not a verdict.  The process that owns the
commit supplies the terminal exit status and its hook output whenever it later
finishes; a caller whose wait expires only learns that the process is running.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

__all__: list[str] = [
    "CommitRunResult",
    "DetachedCommitRunner",
]

_FAILED_TARGET = re.compile(r"^[ \t]+-[ \t]+(\S+)[ \t]*$", re.MULTILINE)
_POLL_INTERVAL_SECONDS = 1.0


class CommitProcess(Protocol):
    """The one process reading the runner needs from a launched commit."""

    output: str

    def poll(self, *, now: float) -> int | None:
        """Return the commit's exit status once its own process has finished."""
        ...


class CommitLauncher(Protocol):
    """Starts the commit process without changing its command arguments."""

    def launch(self, *, command: tuple[str, ...]) -> CommitProcess:
        """Start one detached commit process."""
        ...


class CommitClock(Protocol):
    """The bounded-wait clock, injectable so this state machine needs no sleep."""

    now: float

    def sleep(self, *, seconds: float) -> None:
        """Advance to the next permitted observation instant."""
        ...


@dataclass(frozen=True, kw_only=True)
class CommitRunResult:
    """The current or terminal report for one commit process."""

    state: str
    exit_code: int | None
    failed_targets: tuple[str, ...]


@dataclass
class _CommitRun:
    process: CommitProcess
    result: CommitRunResult | None = None


class DetachedCommitRunner:
    """Start commits once and collect their own verdict through bounded waits."""

    def __init__(self, *, launcher: CommitLauncher, clock: CommitClock) -> None:
        self._launcher = launcher
        self._clock = clock
        self._runs: dict[str, _CommitRun] = {}
        self._next_run_id = 1

    def start(self, *, command: tuple[str, ...]) -> str:
        """Start one commit and return its identity without waiting for it."""
        run_id = f"commit-{self._next_run_id}"
        self._next_run_id += 1
        self._runs[run_id] = _CommitRun(process=self._launcher.launch(command=command))
        return run_id

    def wait(self, *, run_id: str, timeout_seconds: float) -> CommitRunResult:
        """Observe one run until it finishes or this caller's bound expires."""
        run = self._runs[run_id]
        deadline = self._clock.now + timeout_seconds
        while True:
            terminal = self._record_terminal_verdict(run=run)
            if terminal is not None:
                return terminal
            if self._clock.now >= deadline:
                return CommitRunResult(state="running", exit_code=None, failed_targets=())
            self._clock.sleep(seconds=min(_POLL_INTERVAL_SECONDS, deadline - self._clock.now))

    def _record_terminal_verdict(self, *, run: _CommitRun) -> CommitRunResult | None:
        """Store the process's verdict once, retaining it for all later waits."""
        if run.result is not None:
            return run.result
        exit_code = run.process.poll(now=self._clock.now)
        if exit_code is None:
            return None
        run.result = CommitRunResult(
            state="passed" if exit_code == 0 else "failed",
            exit_code=exit_code,
            failed_targets=_failed_targets(output=run.process.output),
        )
        return run.result


def _failed_targets(*, output: str) -> tuple[str, ...]:
    """The named failed targets from the hook's own final output."""
    _, _, targets = output.partition("Failed targets")
    return tuple(_FAILED_TARGET.findall(targets))
