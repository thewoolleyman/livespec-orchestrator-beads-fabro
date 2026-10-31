"""Per-phase CPU accounting for work that precedes a Fabro launch."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, TypeVar

__all__: list[str] = ["PrelaunchCpuProfile"]

_Result = TypeVar("_Result")


class _Journal(Protocol):
    def append(self, *, record: dict[str, object]) -> None:
        """Append one dispatch-journal record."""


@dataclass(frozen=True, kw_only=True)
class PrelaunchCpuProfile:
    """Append one CPU delta for each completed pre-launch phase."""

    journal: _Journal
    work_item_id: str
    dispatch_id: str
    cpu_seconds: Callable[[], float]

    def phase(self, *, name: str, action: Callable[[], _Result]) -> _Result:
        """Run one phase and append its whole-process-tree CPU delta."""
        before = self.cpu_seconds()
        try:
            return action()
        finally:
            self.journal.append(
                record={
                    "stage": "pre-launch-cpu",
                    "work_item_id": self.work_item_id,
                    "dispatch_id": self.dispatch_id,
                    "phase": name,
                    "cpu_seconds": round(max(0.0, self.cpu_seconds() - before), 6),
                }
            )
