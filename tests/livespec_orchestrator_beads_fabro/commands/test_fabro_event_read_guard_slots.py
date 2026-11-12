"""Concurrency cases for the Fabro event-read guard."""

from __future__ import annotations

import fcntl
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

from livespec_orchestrator_beads_fabro.commands._fabro_event_read_guard import (
    FabroEventReadGuard,
)


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


def _lock_slots(*, root: Path, factory: str, count: int) -> list[BinaryIO]:
    digest = hashlib.sha256(factory.encode()).hexdigest()
    handles: list[BinaryIO] = []
    for index in range(count):
        handle = (root / f"{digest}-{index}.lock").open("a+b")
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        handles.append(handle)
    return handles


def _release(*, handles: list[BinaryIO]) -> None:
    for handle in handles:
        handle.close()


def test_another_factory_slot_is_used_when_the_first_is_held(tmp_path: Path) -> None:
    held = _lock_slots(root=tmp_path, factory="petri", count=1)
    try:
        journal = _Journal()
        guard = FabroEventReadGuard(journal=journal, slots_root=tmp_path)
        result = guard.read(
            work_item_id="bd-ib-2dlh7m",
            run_id="01RUN",
            factory="petri",
            caller="review-gate-reader",
            timeout_seconds=0.0,
            read=lambda: _Result(command=_Command(exit_code=0, stdout="[]")),
        )
    finally:
        _release(handles=held)

    assert result is not None
    assert journal.records[0]["stage"] == "fabro-events-read-succeeded"


def test_full_factory_capacity_becomes_a_journaled_unobservable_read(tmp_path: Path) -> None:
    held = _lock_slots(root=tmp_path, factory="petri", count=2)
    try:
        now = [0.0]
        journal = _Journal()

        def sleep(seconds: float) -> None:
            now[0] += seconds

        guard = FabroEventReadGuard(
            journal=journal,
            slots_root=tmp_path,
            clock=lambda: now[0],
            sleeper=sleep,
        )
        result = guard.read(
            work_item_id="bd-ib-2dlh7m",
            run_id="01RUN",
            factory="petri",
            caller="review-gate-reader",
            timeout_seconds=0.05,
            read=lambda: _Result(command=_Command(exit_code=0, stdout="[]")),
        )
    finally:
        _release(handles=held)

    assert result is None
    assert journal.records[0]["stage"] == "fabro-events-read-failed"
    assert journal.records[0]["elapsed_seconds"] == 0.05


def test_zero_byte_success_is_a_failed_read(tmp_path: Path) -> None:
    journal = _Journal()
    guard = FabroEventReadGuard(journal=journal, slots_root=tmp_path)

    result = guard.read(
        work_item_id="bd-ib-2dlh7m",
        run_id="01RUN",
        factory="petri",
        caller="preservation-reader",
        timeout_seconds=0.0,
        read=lambda: _Result(command=_Command(exit_code=0, stdout="")),
    )

    assert result is None
    assert journal.records[0]["stage"] == "fabro-events-read-failed"
