"""Tests for bounded, failure-aware Fabro event reads."""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_fabro_event_read_guard.py"
)
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._fabro_event_read_guard"


@dataclass(kw_only=True)
class _Command:
    exit_code: int
    stdout: str


@dataclass(kw_only=True)
class _Result:
    command: _Command


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _module() -> Any:
    assert _MODULE_PATH.is_file()
    return importlib.import_module(_MODULE_NAME)


def _success() -> _Result:
    return _Result(command=_Command(exit_code=0, stdout="[]"))


def _failure(*, exit_code: int = 1, stdout: str = "failure") -> _Result:
    return _Result(command=_Command(exit_code=exit_code, stdout=stdout))


def test_failed_reads_back_off_and_a_success_resets_the_attempt(tmp_path: Path) -> None:
    module = _module()
    now = [0.0]
    journal = _Journal()
    guard = module.FabroEventReadGuard(
        journal=journal,
        slots_root=tmp_path,
        clock=lambda: now[0],
        sleeper=lambda _: None,
    )
    calls: list[float] = []

    def read_failure() -> _Result:
        calls.append(now[0])
        return _failure()

    assert (
        guard.read(
            work_item_id="bd-ib-2dlh7m",
            run_id="01RUN",
            factory="petri",
            caller="cost-reader",
            timeout_seconds=30.0,
            read=read_failure,
        )
        is None
    )
    assert calls == [0.0]
    assert journal.records == [
        {
            "stage": "fabro-events-read-failed",
            "work_item_id": "bd-ib-2dlh7m",
            "run_id": "01RUN",
            "factory": "petri",
            "caller": "cost-reader",
            "elapsed_seconds": 0.0,
            "consecutive_attempt": 1,
            "backoff_seconds": 60.0,
        }
    ]
    now[0] = 59.0
    assert (
        guard.read(
            work_item_id="bd-ib-2dlh7m",
            run_id="01RUN",
            factory="petri",
            caller="cost-reader",
            timeout_seconds=30.0,
            read=read_failure,
        )
        is None
    )
    assert calls == [0.0]
    now[0] = 60.0
    assert (
        guard.read(
            work_item_id="bd-ib-2dlh7m",
            run_id="01RUN",
            factory="petri",
            caller="cost-reader",
            timeout_seconds=30.0,
            read=read_failure,
        )
        is None
    )
    assert journal.records[-1]["consecutive_attempt"] == 2
    assert journal.records[-1]["backoff_seconds"] == 120.0
    now[0] = 180.0
    assert (
        guard.read(
            work_item_id="bd-ib-2dlh7m",
            run_id="01RUN",
            factory="petri",
            caller="cost-reader",
            timeout_seconds=30.0,
            read=_success,
        )
        == _success()
    )
    assert journal.records[-1]["stage"] == "fabro-events-read-succeeded"
    assert (
        guard.read(
            work_item_id="bd-ib-2dlh7m",
            run_id="01RUN",
            factory="petri",
            caller="cost-reader",
            timeout_seconds=30.0,
            read=lambda: _failure(stdout=""),
        )
        is None
    )
    assert journal.records[-1]["consecutive_attempt"] == 1
    assert journal.records[-1]["backoff_seconds"] == 60.0
