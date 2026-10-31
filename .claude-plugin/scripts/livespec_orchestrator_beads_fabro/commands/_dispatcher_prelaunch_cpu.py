"""Per-phase CPU accounting for work that precedes a Fabro launch."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol, TypeVar

__all__: list[str] = ["PrelaunchCpuProfile"]

_Result = TypeVar("_Result")


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
