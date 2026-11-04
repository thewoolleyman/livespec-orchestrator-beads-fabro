"""The state machine that waits on a detached commit process for its own verdict.

`SPECIFICATION/contracts.md` "A commit leg completes past one tool call"
(Scenario 179, work-item `bd-ib-atyefi`). A bounded wait is an observation,
not a verdict. The process that owns the commit supplies the terminal exit
status and its hook output whenever it later finishes; a caller whose wait
expires only learns that the process is still running, and a process that
ends without writing a verdict is reported as having none.

ONE STATE MACHINE, TWO LAUNCHERS. The sandbox half is the materialized
`livespec-commit-runner.py` (`_dispatcher_commit_runner_program`), which owns
the real process and is stdlib-only because the sandbox clone carries no copy
of this package. The Dispatcher half is `_dispatcher_commit_runner_replay`,
which drives THIS runner through a launcher built from the run's recorded
`start` and `wait` tool calls, so the verdict the needs-human cause and the
dispatch journal carry is the one this state machine retains. Tests drive it
through an injected fake launcher and clock, which is why nothing here spawns
or sleeps.

THE TERMINAL NORMALIZER IS SHARED. `result_from_observation` is the one rule
that turns an exit status and the hook's own output into a verdict, used for a
direct `git commit` tool call and for a runner report alike, so the two commit
routes cannot name a refusal's failed targets differently.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from livespec_orchestrator_beads_fabro.commands._dispatcher_commit_runner_program import (
    COMMIT_RUNNER_PROGRAM_FILENAME,
    commit_runner_prepare_steps_block,
    commit_runner_program_path_expansion,
    commit_runner_program_source,
)

__all__: list[str] = [
    "COMMIT_RUNNER_PROGRAM_FILENAME",
    "NO_VERDICT_STATE",
    "RUNNING_STATE",
    "CommitClock",
    "CommitLauncher",
    "CommitProcess",
    "CommitRunResult",
    "DetachedCommitRunner",
    "commit_runner_prepare_steps_block",
    "commit_runner_program_path_expansion",
    "commit_runner_program_source",
    "failed_targets",
    "result_from_observation",
]

RUNNING_STATE = "running"
NO_VERDICT_STATE = "no-verdict"

# The gate aggregate's own list of failed recipes: `Failed targets (1):` followed
# by `  - check-types` lines. The list ends at the first line that is not one.
_FAILED_TARGETS_HEADER = re.compile(r"^Failed targets \(\d+\):\s*$", re.MULTILINE)
_FAILED_TARGET_LINE = re.compile(r"^\s+-\s+(\S+)\s*$")

_POLL_INTERVAL_SECONDS = 1.0


class CommitProcess(Protocol):
    """The one process reading the runner needs from a launched commit."""

    @property
    def output(self) -> str:
        """The commit's own output so far, hook output included."""
        ...

    def poll(self, *, now: float) -> int | None:
        """Return the commit's exit status once its own process has finished."""
        ...

    def ended_without_verdict(self) -> bool:
        """True once the commit's process is gone without having written a verdict."""
        ...


class CommitLauncher(Protocol):
    """Starts the commit process without changing its command arguments."""

    def launch(self, *, command: tuple[str, ...]) -> CommitProcess:
        """Start one detached commit process."""
        ...


class CommitClock(Protocol):
    """The bounded-wait clock, injectable so this state machine needs no sleep."""

    @property
    def now(self) -> float:
        """The current observation instant, in seconds."""
        ...

    def sleep(self, *, seconds: float) -> None:
        """Advance to the next permitted observation instant."""
        ...


@dataclass(frozen=True, kw_only=True)
class CommitRunResult:
    """The current or terminal report for one commit process.

    `state` is `passed`, `failed`, `running` or `no-verdict`; only the first two
    carry an exit status, and only a refusal can name failed targets.
    """

    state: str
    exit_code: int | None
    failed_targets: tuple[str, ...]

    @property
    def terminal(self) -> bool:
        """True for every state but `running`."""
        return self.state != RUNNING_STATE


_STILL_RUNNING = CommitRunResult(state=RUNNING_STATE, exit_code=None, failed_targets=())
_NO_VERDICT = CommitRunResult(state=NO_VERDICT_STATE, exit_code=None, failed_targets=())


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
        """Observe one run until it reaches a terminal state or this caller's bound expires."""
        run = self._runs[run_id]
        deadline = self._clock.now + timeout_seconds
        while True:
            terminal = self._record_terminal_verdict(run=run)
            if terminal is not None:
                return terminal
            if self._clock.now >= deadline:
                return _STILL_RUNNING
            self._clock.sleep(seconds=min(_POLL_INTERVAL_SECONDS, deadline - self._clock.now))

    def _record_terminal_verdict(self, *, run: _CommitRun) -> CommitRunResult | None:
        """Store the process's terminal state once, retaining it for all later waits."""
        if run.result is not None:
            return run.result
        exit_code = run.process.poll(now=self._clock.now)
        if exit_code is not None:
            run.result = result_from_observation(exit_code=exit_code, output=run.process.output)
        elif run.process.ended_without_verdict():
            run.result = _NO_VERDICT
        return run.result


def result_from_observation(*, exit_code: int, output: str) -> CommitRunResult:
    """The verdict an exit status and the hook's own output state."""
    return CommitRunResult(
        state="passed" if exit_code == 0 else "failed",
        exit_code=exit_code,
        failed_targets=() if exit_code == 0 else failed_targets(output=output),
    )


def failed_targets(*, output: str) -> tuple[str, ...]:
    """The failed recipe names the gate aggregate's own final list printed."""
    header = _FAILED_TARGETS_HEADER.search(output)
    if header is None:
        return ()
    targets: list[str] = []
    for line in output[header.end() :].splitlines()[1:]:
        match = _FAILED_TARGET_LINE.match(line)
        if match is None:
            break
        targets.append(match.group(1))
    return tuple(targets)
