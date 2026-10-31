"""Per-phase CPU accounting for work that precedes a Fabro launch."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, TypeVar

from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

__all__: list[str] = [
    "PrelaunchCheckpoint",
    "PrelaunchCpuProfile",
    "drive_tree_cpu_seconds",
    "ignore_prelaunch_checkpoint",
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

    journal: _Journal
    work_item_id: str
    dispatch_id: str
    cpu_seconds: Callable[[], float]
    _last_cpu_seconds: float = field(init=False)

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

    def __post_init__(self) -> None:
        self._last_cpu_seconds = self.cpu_seconds()

    def phase(self, *, name: str, action: Callable[[], _Result]) -> _Result:
        """Run one phase and append its whole-process-tree CPU delta."""
        try:
            return action()
        finally:
            self.checkpoint(name=name)

    def checkpoint(self, *, name: str) -> None:
        """Record CPU since the preceding pre-launch phase boundary."""
        current = self.cpu_seconds()
        self.journal.append(
            record={
                "stage": "pre-launch-cpu",
                "work_item_id": self.work_item_id,
                "dispatch_id": self.dispatch_id,
                "phase": name,
                "cpu_seconds": round(max(0.0, current - self._last_cpu_seconds), 6),
            }
        )
        self._last_cpu_seconds = current


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
