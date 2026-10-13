"""Existing gate-status adapter for independently observed wait targets."""

from __future__ import annotations

import os
import re
import signal
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_defaults import (
    FLEET_RECIPE_RUNNER,
    FLEET_TOOL_RUNNER,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._session_wait_types import (
    GateObservation,
    GateTarget,
)

__all__: list[str] = [
    "GateStatusLauncher",
    "GateStatusProbe",
    "observe_gate_target",
    "resolve_primary_repository",
]

_DEFAULT_COMMAND = (
    FLEET_TOOL_RUNNER,
    "exec",
    "--",
    FLEET_RECIPE_RUNNER,
    "gate-status",
)
_STATE_PATTERN = re.compile(r"^\s*state\s*:\s*(\S+)\s*$", re.MULTILINE)
_EXIT_PATTERN = re.compile(r"^\s*exit_code\s*:\s*(-?\d+)\s*$", re.MULTILINE)
# The exit code `ShellCommandRunner` maps a child it had to REAP onto, so the
# runner's own timeout is routable data rather than an exception.
_TIMEOUT_EXIT_CODE = 124


def resolve_primary_repository(*, repository: Path) -> Path:
    result = ShellCommandRunner().run(
        argv=["git", "-C", str(repository), "config", "--get", "livespec.primaryPath"],
        cwd=repository,
        timeout_seconds=5.0,
    )
    configured = result.stdout.strip()
    return Path(configured).resolve() if configured else repository.resolve()


def _generation_observation(*, target: GateTarget, observed_at: float) -> GateObservation | None:
    try:
        generation = (target.gate_store_root / target.run_id / "started_at").read_text(
            encoding="utf-8"
        )
    except OSError:
        return GateObservation(
            target=target,
            state="GONE",
            exit_code=None,
            observed_at=observed_at,
            fresh=True,
        )
    if generation.strip() != target.generation:
        return GateObservation(
            target=target,
            state="REPLACED",
            exit_code=None,
            observed_at=observed_at,
            fresh=True,
        )
    return None


def _unavailable(*, target: GateTarget, observed_at: float) -> GateObservation:
    """The diagnostic for a gate that WAS probed and could not be read."""
    return GateObservation(
        target=target,
        state="UNAVAILABLE",
        exit_code=None,
        observed_at=observed_at,
        fresh=True,
    )


def _parse_status(
    *,
    target: GateTarget,
    output: str,
    probe_exit_code: int,
    observed_at: float,
) -> GateObservation | None:
    """This probe's reading of the gate, or None when it never took one.

    `probe_exit_code` is the PROBE PROCESS's own exit code and is never the
    gate's: the gate's is parsed out of the status output below. Keeping them
    under separate names is what stops a reaped probe's 124 from being
    reported as a verdict the gate never printed.

    A probe REAPED BY ITS OWN BUDGET observed nothing: its empty output is the
    absence of a reading, not a gate whose status cannot be read, and the two
    owe opposite treatments. Reporting the diagnostic there ended a bounded
    wait on its own instrument's slowness — measured 2026-10-12 and again
    2026-10-13 on this host, where a `gate-status` call takes about 0.3s
    against the one-second per-probe budget and an ordinary load spike pushes
    it past that. Three waits returned `target-ended` with their trigger in
    state `UNAVAILABLE`, one of them almost six hours short of its deadline,
    while `gate-status` reported `RUNNING` for the same gate moments later and
    its runner process was alive.

    A probe that COMPLETED and printed no state line is the genuinely
    unreadable target the contract's distinct unavailable outcome is for, and
    keeps it. The state line is therefore looked for FIRST: a reaped child's
    PARTIAL output still reaches here, so a probe that printed its state and
    was then reaped did observe the gate and is read as having done so.
    """
    state_match = _STATE_PATTERN.search(output)
    if state_match is None:
        if probe_exit_code == _TIMEOUT_EXIT_CODE:
            return None
        return _unavailable(target=target, observed_at=observed_at)
    state = state_match.group(1)
    exit_match = _EXIT_PATTERN.search(output)
    exit_code = int(exit_match.group(1)) if exit_match is not None else None
    return GateObservation(
        target=target,
        state=state,
        exit_code=exit_code,
        observed_at=observed_at,
        fresh=True,
    )


@dataclass(kw_only=True)
class _CommandTask:
    target: GateTarget
    command_prefix: tuple[str, ...]
    observed_at: float
    timeout_seconds: float
    result: GateObservation | None = field(default=None, init=False)
    thread: threading.Thread | None = field(default=None, init=False)
    ready: threading.Event = field(default_factory=threading.Event, init=False)
    cancel_requested: bool = field(default=False, init=False)
    native_thread_id: int | None = field(default=None, init=False)
    # This probe FINISHED without observing the target, because its own budget
    # reaped it. It is its own field rather than an absent `result`, which a
    # probe still in flight also has: the two are indistinguishable from the
    # result alone, and they owe opposite handling — one is waited on, the
    # other is retired so a fresh probe can take the reading.
    unobserved: bool = field(default=False, init=False)

    def start(self) -> None:
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self) -> None:
        self.native_thread_id = threading.get_native_id()
        self.ready.set()
        if self.cancel_requested:
            # Cancellation landed before this worker reached its probe, so no
            # child is spawned at all. This is what makes `cancel`'s skip of
            # the child scan SOUND rather than fail-open: without it an unready
            # task would go on to spawn a probe nothing kills, while
            # cancellation reported itself clean.
            return
        observation = _gate_status_observation(
            target=self.target,
            observed_at=self.observed_at,
            command_prefix=self.command_prefix,
            timeout_seconds=self.timeout_seconds,
            start_new_session=True,
        )
        if self.cancel_requested:
            # A cancelled probe's reading is discarded, and so is its failure
            # to take one: cancellation already released this task, so marking
            # it unobserved would say something about a probe nobody is still
            # waiting on.
            return
        if observation is None:
            self.unobserved = True
            return
        self.result = observation

    def poll(self) -> GateObservation | None:
        return self.result

    def cancel(self, *, timeout_seconds: float) -> None:
        """Stop this probe's observation. NEVER raises on a lost race.

        `run_wait` cancels on every return path, the successful first-event one
        included, so an exception here would discard a bounded result that had
        already been computed and report the whole wait as a crash. Each way
        the task can win the race is therefore an ordinary outcome: an unready
        task has no thread id to scan, an exited task has no task directory and
        has already reaped its child, and a child that exits before the signal
        is a group that is simply gone.
        """
        started = time.monotonic()
        self.cancel_requested = True
        _ = self.ready.wait(timeout=timeout_seconds)
        native_thread_id = self.native_thread_id
        if native_thread_id is not None:
            task_dir = _probe_task_dir(native_thread_id=native_thread_id)
            for pid in _thread_child_pids(task_dir=task_dir):
                _kill_probe_group(pid=pid)
        thread = self.thread
        if thread is not None:
            thread.join(timeout=max(0.0, timeout_seconds - (time.monotonic() - started)))


def _probe_task_dir(*, native_thread_id: int) -> Path:
    """The `/proc` task directory of one worker thread of THIS process."""
    return Path(f"/proc/{os.getpid()}/task/{native_thread_id}")


def _thread_child_pids(*, task_dir: Path) -> tuple[int, ...]:
    """The probe children one worker thread owns, or none once it has exited.

    An ABSENT task directory means the worker has exited, and an exited worker
    has already reaped the child `subprocess.run` spawned — so there is nothing
    left to kill. That is the normal outcome of a sibling probe finishing
    between the last poll and cancellation, which is precisely why it must not
    raise.

    An EXISTING task whose `children` cannot be read is the opposite case and
    deliberately RE-RAISES: that gauge is blind, and answering "no children"
    there would report a clean cancellation while leaving a live probe child
    running. Do not widen this to swallow every read failure.
    """
    try:
        children = (task_dir / "children").read_text(encoding="utf-8")
    except OSError:
        if task_dir.exists():
            raise
        return ()
    return tuple(int(pid) for pid in children.split())


def _kill_probe_group(*, pid: int) -> None:
    """SIGKILL one probe child's group, tolerating a group that already went.

    `ProcessLookupError` is the same race one level down — the child exiting
    between the children read and the signal — and is not a fault. Every other
    `OSError`, a permission failure say, still raises: that one says the kill
    was REFUSED rather than unnecessary.
    """
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        return


@dataclass(kw_only=True)
class GateStatusProbe:
    target: GateTarget
    repository: Path
    command_prefix: tuple[str, ...]
    timeout_seconds: float
    task: _CommandTask | None = field(default=None, init=False)

    @property
    def active(self) -> bool:
        return self.task is not None

    def poll(self, *, now: float) -> GateObservation | None:
        generation_observation = _generation_observation(target=self.target, observed_at=now)
        if generation_observation is not None:
            return observe_gate_target(
                target=self.target,
                observed_at=now,
                command_prefix=self.command_prefix,
                timeout_seconds=self.timeout_seconds,
            )
        if self.task is None:
            self.task = _CommandTask(
                target=self.target,
                command_prefix=self.command_prefix,
                observed_at=now,
                timeout_seconds=self.timeout_seconds,
            )
            self.task.start()
        task = self.task
        observation = task.poll()
        if observation is None:
            if task.unobserved:
                # The probe was reaped by its own budget, so it is RETIRED
                # here rather than kept. That is what lets the next round
                # launch a fresh probe inside the same deadline — keeping it
                # would leave a finished task answering None for the rest of
                # the wait, which is a hang traded for the false verdict.
                self.task = None
            return None
        self.task = None
        return observation

    def cancel(self, *, timeout_seconds: float) -> None:
        if self.task is not None:
            self.task.cancel(timeout_seconds=timeout_seconds)
        self.task = None


@dataclass(frozen=True, kw_only=True)
class GateStatusLauncher:
    repository: Path
    command_prefix: tuple[str, ...] = _DEFAULT_COMMAND

    def launch(self, *, target: GateTarget, timeout_seconds: float) -> GateStatusProbe:
        return GateStatusProbe(
            target=target,
            repository=self.repository,
            command_prefix=self.command_prefix,
            timeout_seconds=min(1.0, max(0.01, timeout_seconds)),
        )


def _gate_status_observation(
    *,
    target: GateTarget,
    observed_at: float,
    command_prefix: tuple[str, ...],
    timeout_seconds: float,
    start_new_session: bool,
) -> GateObservation | None:
    """One probe of this gate, or None when the probe took no reading."""
    generation_observation = _generation_observation(target=target, observed_at=observed_at)
    if generation_observation is not None:
        return generation_observation
    result: CommandResult = ShellCommandRunner().run(
        argv=[*command_prefix, target.run_id],
        cwd=target.gate_store_root / target.run_id,
        timeout_seconds=timeout_seconds,
        start_new_session=start_new_session,
    )
    return _parse_status(
        target=target,
        output=result.stdout + result.stderr,
        probe_exit_code=result.exit_code,
        observed_at=observed_at,
    )


def observe_gate_target(
    *,
    target: GateTarget,
    observed_at: float,
    command_prefix: tuple[str, ...] = _DEFAULT_COMMAND,
    timeout_seconds: float = 1.0,
    start_new_session: bool = False,
) -> GateObservation:
    """One SYNCHRONOUS reading of a gate, reporting a reaped probe UNAVAILABLE.

    The retry that makes "no reading" a useful answer needs a later round to
    take one in, and a single blocking observation — what the inventory and
    check surfaces take — has none. So it reports the unreadable-target
    diagnostic rather than inventing a state or returning nothing a caller
    could render. `GateStatusProbe` is the path that retries.
    """
    observation = _gate_status_observation(
        target=target,
        observed_at=observed_at,
        command_prefix=command_prefix,
        timeout_seconds=timeout_seconds,
        start_new_session=start_new_session,
    )
    if observation is None:
        return _unavailable(target=target, observed_at=observed_at)
    return observation
