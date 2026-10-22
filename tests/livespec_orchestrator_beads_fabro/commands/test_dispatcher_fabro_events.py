"""Tests for bounded, failure-aware Dispatcher Fabro event reads."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._fabro_port_types import FabroEventsResult

_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_fabro_events.py"
)
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_events"


@dataclass(kw_only=True)
class _EventsCall:
    run_id: str
    timeout_seconds: float
    tail: int | None


@dataclass(kw_only=True)
class _Port:
    results: list[FabroEventsResult]
    calls: list[_EventsCall]

    def events(
        self,
        *,
        run_id: str,
        timeout_seconds: float,
        tail: int | None,
    ) -> FabroEventsResult:
        self.calls.append(_EventsCall(run_id=run_id, timeout_seconds=timeout_seconds, tail=tail))
        return self.results.pop(0)


def _events_module() -> Any:
    assert _MODULE_PATH.is_file()
    return importlib.import_module(_MODULE_NAME)


def _success() -> FabroEventsResult:
    return FabroEventsResult(
        command=CommandResult(
            exit_code=0, stdout='[{"timestamp": "2026-10-22T00:00:00Z"}]', stderr=""
        ),
        payload=[],
    )


def test_reader_bounds_every_read_after_its_first_observation(tmp_path: Path) -> None:
    module = _events_module()
    port = _Port(results=[_success(), _success()], calls=[])
    reader = module.FabroEventsReader(
        port=port,
        work_item_id="bd-ib-2dlh7m",
        factory="petri",
        caller="progress-watchdog",
        journal=object(),
        slots_root=tmp_path,
    )

    _ = reader.read(run_id="run-1", timeout_seconds=60.0)
    _ = reader.read(run_id="run-1", timeout_seconds=60.0)

    assert [call.tail for call in port.calls] == [None, module.FABRO_EVENTS_TAIL]
