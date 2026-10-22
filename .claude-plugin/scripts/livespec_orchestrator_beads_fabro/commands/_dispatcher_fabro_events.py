"""Stateful, bounded reads of one Fabro run's event stream."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from livespec_orchestrator_beads_fabro.commands._fabro_port_types import (
    FabroEventsResult,
)

__all__: list[str] = [
    "FABRO_EVENTS_TAIL",
    "FabroEventsReader",
]

FABRO_EVENTS_TAIL = 200


class FabroEventsPort(Protocol):
    """The bounded-events part of the Fabro command facade."""

    def events(
        self,
        *,
        run_id: str,
        timeout_seconds: float,
        tail: int | None,
    ) -> FabroEventsResult:
        """Read one run's events, optionally from a bounded trailing window."""
        ...


@dataclass(kw_only=True)
class FabroEventsReader:
    """Keep each caller's later reads of a run within a bounded tail."""

    port: FabroEventsPort
    work_item_id: str
    factory: str
    caller: str
    journal: object
    slots_root: Path
    _observed_runs: set[str] = field(default_factory=set, init=False, repr=False)

    def read(self, *, run_id: str, timeout_seconds: float) -> FabroEventsResult:
        """Read a run once in full, then use the portable bounded tail."""
        tail = FABRO_EVENTS_TAIL if run_id in self._observed_runs else None
        result = self.port.events(
            run_id=run_id,
            timeout_seconds=timeout_seconds,
            tail=tail,
        )
        self._observed_runs.add(run_id)
        return result
