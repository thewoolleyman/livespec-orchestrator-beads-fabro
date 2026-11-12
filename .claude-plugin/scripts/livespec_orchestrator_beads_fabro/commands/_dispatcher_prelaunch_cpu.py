"""Per-phase CPU accounting for work that precedes a Fabro launch."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, TypeVar

from livespec_orchestrator_beads_fabro.commands._dispatcher_journal_file import utc_now_iso
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

__all__: list[str] = [
    "PrelaunchCheckpoint",
    "PrelaunchCpuProfile",
    "drive_tree_cpu_seconds",
    "ignore_prelaunch_checkpoint",
    "prelaunch_phase",
    "process_tree_cpu_seconds",
]

_Result = TypeVar("_Result")


class PrelaunchCheckpoint(Protocol):
    """Records the CPU spent since the preceding pre-launch phase boundary."""

    def __call__(self, *, name: str) -> None:
        """Close the named pre-launch phase."""


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
    _last_cpu_seconds: float = field(init=False)
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
        profile.checkpoint(name="drive-startup")
        return profile

    def __post_init__(self) -> None:
        self._last_cpu_seconds = (
            self.cpu_seconds() if self.baseline_cpu_seconds is None else self.baseline_cpu_seconds
        )

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
        forked = PrelaunchCpuProfile(dispatch_id=dispatch_id, cpu_seconds=self.cpu_seconds)
        forked.restate(rows=self._history)
        return forked

    def restate(self, *, rows: list[dict[str, object]]) -> None:
        """Hold each row, under this profile's dispatch id, until `bind` appends it."""
        self._held.extend({**row, "dispatch_id": self.dispatch_id} for row in rows)

    def phase(self, *, name: str, action: Callable[[], _Result]) -> _Result:
        """Run one phase and append its whole-process-tree CPU delta."""
        with self.during(name=name):
            return action()

    def during(self, *, name: str) -> AbstractContextManager[None]:
        """Bracket one phase so its row is appended whether it returns or raises."""
        return prelaunch_phase(checkpoint=self.checkpoint, name=name)

    def checkpoint(self, *, name: str) -> None:
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


@contextmanager
def prelaunch_phase(*, checkpoint: PrelaunchCheckpoint, name: str) -> Iterator[None]:
    """Close the named phase's row when the body returns or raises."""
    try:
        yield
    finally:
        checkpoint(name=name)


def ignore_prelaunch_checkpoint(*, name: str) -> None:
    """Record nothing; the default for a caller that keeps no pre-launch profile."""
    del name


def drive_tree_cpu_seconds() -> float:
    """CPU seconds this drive's whole live process tree has spent so far."""
    return process_tree_cpu_seconds(
        root=Path("/proc"), pid=os.getpid(), clock_ticks=os.sysconf("SC_CLK_TCK")
    )


def process_tree_cpu_seconds(*, root: Path, pid: int, clock_ticks: int) -> float:
    """Sum utime, stime, cutime and cstime over `pid` and every live descendant.

    `os.times()` sees a child only once it is reaped, so a `fabro run` still
    running reads as zero there. Each live process carries the CPU of the
    children it has already reaped, which no ancestor has counted yet, so the sum
    over the live tree counts every second exactly once. Linux exposes each
    process's direct children in its task `children` file, so the normal path
    reads only the drive tree rather than every process on a busy factory host.
    The whole-process scan remains a compatibility fallback for a procfs that
    does not expose that Linux file.
    """
    tree = _descendant_pids(root=root, pid=pid)
    if tree is not None:
        return sum(_ticks_for(path=root / str(child) / "stat") for child in tree) / clock_ticks

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


def _descendant_pids(*, root: Path, pid: int) -> list[int] | None:
    """Return the live tree through procfs child lists, or None when unavailable."""
    pending = [pid]
    tree: list[int] = []
    while pending:
        current = pending.pop()
        children = _child_pids(root=root, pid=current)
        if children is None:
            return None
        tree.append(current)
        pending.extend(children)
    return tree


def _child_pids(*, root: Path, pid: int) -> list[int] | None:
    """Read one process's direct children from Linux procfs."""
    text = attempt(
        action=lambda: (root / str(pid) / "task" / str(pid) / "children").read_text(
            encoding="utf-8"
        ),
        exceptions=(OSError,),
    )
    if isinstance(text, AttemptFailure):
        return None
    return [int(child) for child in text.split()]


def _ticks_for(*, path: Path) -> int:
    """Return one process's CPU ticks, treating a process that exited as zero."""
    row = _stat_row(path=path)
    return 0 if row is None else row[1]


def _stat_row(*, path: Path) -> tuple[int, int] | None:
    text = attempt(action=lambda: path.read_text(encoding="utf-8"), exceptions=(OSError,))
    if isinstance(text, AttemptFailure):
        return None
    fields = text.rpartition(")")[2].split()
    return int(fields[1]), sum(int(one) for one in fields[11:15])
