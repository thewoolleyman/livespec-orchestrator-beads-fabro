"""Per-phase CPU accounting for work that precedes a Fabro launch."""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol, TypeVar, runtime_checkable

from livespec_orchestrator_beads_fabro.commands._dispatcher_journal_file import utc_now_iso
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

__all__: list[str] = [
    "PrelaunchCheckpoint",
    "PrelaunchCpuProfile",
    "PrelaunchStep",
    "PrelaunchStepJournal",
    "drive_process_age_seconds",
    "drive_tree_cpu_seconds",
    "ignore_prelaunch_checkpoint",
    "prelaunch_phase",
    "process_age_seconds",
    "process_tree_cpu_seconds",
]

_Result = TypeVar("_Result")


class PrelaunchCheckpoint(Protocol):
    """Records the CPU spent since the preceding pre-launch phase boundary."""

    def __call__(self, *, name: str) -> None:
        """Close the named pre-launch phase."""


@runtime_checkable
class PrelaunchStepJournal(Protocol):
    """Journals the start and the end of one pre-launch step.

    A checkpoint that also satisfies this protocol makes `prelaunch_phase`
    journal the step's start, and its end with the outcome, so a step that is
    still running when the Dispatcher is killed has a start record naming it.
    """

    def step_started(self, *, name: str) -> None:
        """Journal that the named step has started."""

    def step_ended(self, *, name: str, outcome: str) -> None:
        """Journal that the named step has ended with `outcome`."""


@dataclass(kw_only=True)
class PrelaunchStep:
    """The outcome a pre-launch step reports; `completed` unless the body says otherwise."""

    outcome: str = "completed"


class _Journal(Protocol):
    def append(self, *, record: dict[str, object]) -> None:
        """Append one dispatch-journal record."""


@dataclass(kw_only=True)
class PrelaunchCpuProfile:
    """Append one CPU delta for each completed pre-launch phase."""

    dispatch_id: str
    cpu_seconds: Callable[[], float]
    journal: _Journal | None = None
    work_item_id: str | None = None
    baseline_cpu_seconds: float | None = None
    pass_id: str | None = None
    clock: Callable[[], float] = time.monotonic
    checkpoint: _ProfileCheckpoint = field(init=False)
    _last_cpu_seconds: float = field(init=False)
    _open_steps: dict[str, float] = field(init=False, default_factory=dict)
    _held: list[dict[str, object]] = field(init=False, default_factory=list)
    _history: list[dict[str, object]] = field(init=False, default_factory=list)

    @classmethod
    def for_drive(
        cls, *, journal: _Journal, work_item_id: str, dispatch_id: str
    ) -> PrelaunchCpuProfile:
        """Profile the live process tree of the drive running this code."""
        return cls(
            journal=journal,
            work_item_id=work_item_id,
            dispatch_id=dispatch_id,
            cpu_seconds=drive_tree_cpu_seconds,
        )

    @classmethod
    def for_drive_launch(cls, *, dispatch_id: str) -> PrelaunchCpuProfile:
        """Profile from the drive's own start, before its journal or item is known.

        Rows are held, stamped with the time each phase closed, until `bind`
        names the journal and the work item the drive dispatches. The first row
        carries the CPU the drive spent starting up, because the baseline is zero.
        """
        profile = cls(
            dispatch_id=dispatch_id,
            cpu_seconds=drive_tree_cpu_seconds,
            baseline_cpu_seconds=0.0,
        )
        age = drive_process_age_seconds()
        profile.record_step(event="start", name="drive-startup", at=_seconds_ago(seconds=age))
        profile.checkpoint(name="drive-startup")
        profile.record_step(
            event="end", name="drive-startup", elapsed_seconds=age, outcome="completed"
        )
        return profile

    def __post_init__(self) -> None:
        self._last_cpu_seconds = (
            self.cpu_seconds() if self.baseline_cpu_seconds is None else self.baseline_cpu_seconds
        )
        self.pass_id = self.dispatch_id if self.pass_id is None else self.pass_id
        self.checkpoint = _ProfileCheckpoint(profile=self)

    def bind(self, *, journal: _Journal, work_item_id: str) -> None:
        """Name the journal and work item, then append every row held so far."""
        self.journal = journal
        self.work_item_id = work_item_id
        held, self._held = self._held, []
        for record in held:
            journal.append(record={**record, "work_item_id": work_item_id})

    def fork(self, *, dispatch_id: str) -> PrelaunchCpuProfile:
        """Profile another dispatch this drive launches, starting from every row so far.

        The fork re-states each row under its own dispatch id, held until `bind`
        names its journal and work item, so a dispatch the drive launches after
        the first still shows the pre-admission phases it waited behind.
        """
        forked = PrelaunchCpuProfile(
            dispatch_id=dispatch_id,
            cpu_seconds=self.cpu_seconds,
            pass_id=self.pass_id,
            clock=self.clock,
        )
        forked.restate(rows=self._history)
        return forked

    def restate(self, *, rows: list[dict[str, object]]) -> None:
        """Hold each row, under this profile's dispatch id, until `bind` appends it."""
        self._held.extend({**row, "dispatch_id": self.dispatch_id} for row in rows)

    def phase(self, *, name: str, action: Callable[[], _Result]) -> _Result:
        """Run one phase and append its whole-process-tree CPU delta."""
        with self.during(name=name):
            return action()

    def during(self, *, name: str) -> AbstractContextManager[PrelaunchStep]:
        """Bracket one phase so its rows are appended whether it returns or raises."""
        return prelaunch_phase(checkpoint=self.checkpoint, name=name)

    def step_started(self, *, name: str) -> None:
        """Journal the start of the named step and remember when it began."""
        self._open_steps[name] = self.clock()
        self.record_step(event="start", name=name)

    def step_ended(self, *, name: str, outcome: str) -> None:
        """Journal the end of the named step with its elapsed seconds and outcome."""
        elapsed = max(0.0, self.clock() - self._open_steps.pop(name))
        self.record_step(event="end", name=name, elapsed_seconds=round(elapsed, 6), outcome=outcome)

    def record_step(
        self,
        *,
        event: str,
        name: str,
        elapsed_seconds: float | None = None,
        outcome: str | None = None,
        at: str | None = None,
    ) -> None:
        """Append one start or end record for a pre-launch step, held until `bind`."""
        record: dict[str, object] = {
            "stage": "pre-launch-step",
            "event": event,
            "step": name,
            "dispatch_id": self.dispatch_id,
            "pass_id": self.pass_id,
        }
        if elapsed_seconds is not None:
            record["elapsed_seconds"] = elapsed_seconds
        if outcome is not None:
            record["outcome"] = outcome
        stamped: dict[str, object] = {**record, "at": at or utc_now_iso()}
        self._history.append(stamped)
        if self.journal is None or self.work_item_id is None:
            self._held.append(stamped)
        else:
            self.journal.append(record={**record, "work_item_id": self.work_item_id})

    def close_phase(self, *, name: str) -> None:
        """Record CPU since the preceding pre-launch phase boundary."""
        current = self.cpu_seconds()
        record: dict[str, object] = {
            "stage": "pre-launch-cpu",
            "dispatch_id": self.dispatch_id,
            "phase": name,
            "cpu_seconds": round(max(0.0, current - self._last_cpu_seconds), 6),
        }
        self._last_cpu_seconds = current
        stamped: dict[str, object] = {**record, "at": utc_now_iso()}
        self._history.append(stamped)
        if self.journal is None or self.work_item_id is None:
            self._held.append(stamped)
        else:
            self.journal.append(record={**record, "work_item_id": self.work_item_id})


class _ProfileCheckpoint:
    """The profile's checkpoint: closes a CPU row and journals the step boundaries."""

    def __init__(self, *, profile: PrelaunchCpuProfile) -> None:
        self._profile = profile

    def __call__(self, *, name: str) -> None:
        """Close the named pre-launch phase's CPU row."""
        self._profile.close_phase(name=name)

    def step_started(self, *, name: str) -> None:
        """Journal the start of the named step."""
        self._profile.step_started(name=name)

    def step_ended(self, *, name: str, outcome: str) -> None:
        """Journal the end of the named step."""
        self._profile.step_ended(name=name, outcome=outcome)


@contextmanager
def prelaunch_phase(*, checkpoint: PrelaunchCheckpoint, name: str) -> Iterator[PrelaunchStep]:
    """Journal the named step's start, then its CPU row and end when the body returns or raises.

    The end record carries `failed` when the body raises. A body that withholds
    the dispatch without raising sets `step.outcome` itself, for example to
    `refused`, so the refusal is journaled before the caller acts on it.
    """
    step = PrelaunchStep()
    steps = checkpoint if isinstance(checkpoint, PrelaunchStepJournal) else None
    if steps is not None:
        steps.step_started(name=name)
    returned = False
    try:
        yield step
        returned = True
    finally:
        if not returned:
            step.outcome = "failed"
        try:
            checkpoint(name=name)
        finally:
            if steps is not None:
                steps.step_ended(name=name, outcome=step.outcome)


def ignore_prelaunch_checkpoint(*, name: str) -> None:
    """Record nothing; the default for a caller that keeps no pre-launch profile."""
    del name


def drive_tree_cpu_seconds() -> float:
    """CPU seconds this drive's whole live process tree has spent so far."""
    return process_tree_cpu_seconds(
        root=Path("/proc"), pid=os.getpid(), clock_ticks=os.sysconf("SC_CLK_TCK")
    )


def drive_process_age_seconds() -> float:
    """Seconds since this drive's process started."""
    return process_age_seconds(
        root=Path("/proc"), pid=os.getpid(), clock_ticks=os.sysconf("SC_CLK_TCK")
    )


def process_age_seconds(*, root: Path, pid: int, clock_ticks: int) -> float:
    """Seconds `pid` has been alive: the system uptime less its start time, or 0.0 unread."""
    uptime = attempt(
        action=lambda: float((root / "uptime").read_text(encoding="utf-8").split()[0]),
        exceptions=(OSError, ValueError, IndexError),
    )
    stat = attempt(
        action=lambda: (root / str(pid) / "stat").read_text(encoding="utf-8"),
        exceptions=(OSError,),
    )
    if isinstance(uptime, AttemptFailure) or isinstance(stat, AttemptFailure):
        return 0.0
    started = int(stat.rpartition(")")[2].split()[19]) / clock_ticks
    return max(0.0, uptime - started)


def _seconds_ago(*, seconds: float) -> str:
    moment = datetime.now(timezone.utc) - timedelta(seconds=seconds)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def process_tree_cpu_seconds(*, root: Path, pid: int, clock_ticks: int) -> float:
    """Sum utime, stime, cutime and cstime over `pid` and every live descendant.

    `os.times()` sees a child only once it is reaped, so a `fabro run` still
    running reads as zero there. Each live process carries the CPU of the
    children it has already reaped, which no ancestor has counted yet, so the sum
    over the live tree counts every second exactly once.
    """
    ticks_by_pid: dict[int, int] = {}
    children: dict[int, list[int]] = {}
    for entry in root.iterdir():
        row = _stat_row(path=entry / "stat") if entry.name.isdigit() else None
        if row is not None:
            parent, ticks = row
            ticks_by_pid[int(entry.name)] = ticks
            children.setdefault(parent, []).append(int(entry.name))
    total = 0
    pending = [pid]
    while pending:
        current = pending.pop()
        total += ticks_by_pid.get(current, 0)
        pending.extend(children.get(current, ()))
    return total / clock_ticks


def _stat_row(*, path: Path) -> tuple[int, int] | None:
    text = attempt(action=lambda: path.read_text(encoding="utf-8"), exceptions=(OSError,))
    if isinstance(text, AttemptFailure):
        return None
    fields = text.rpartition(")")[2].split()
    return int(fields[1]), sum(int(one) for one in fields[11:15])
