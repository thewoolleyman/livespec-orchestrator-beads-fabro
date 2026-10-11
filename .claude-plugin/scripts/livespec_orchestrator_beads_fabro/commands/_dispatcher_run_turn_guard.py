"""Post-dispatch `run_turn` telemetry assertion for the Dispatcher."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection_journal import (
    read_journal_records,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_turn_sink import (
    RunTurnSink,
    run_turn_check_record,
)

__all__: list[str] = [
    "append_run_turn_checks",
]


class JournalWriter(Protocol):
    def append(self, *, record: dict[str, object]) -> None:
        """Persist one journal record."""
        ...


@dataclass(frozen=True, kw_only=True)
class _DispatchRunTurnObservation:
    dispatch_id: str
    started_at_epoch: float | None
    observable: bool


def append_run_turn_checks(
    *,
    outcomes: tuple[DispatchOutcome, ...],
    journal: JournalWriter,
    journal_path: Path,
    sink: RunTurnSink,
) -> None:
    """Append one non-blocking `run_turn` export assertion per green dispatch."""
    dispatches = _dispatches_by_item(records=read_journal_records(journal_path=journal_path))
    for outcome in outcomes:
        if outcome.status != "green":
            continue
        observation = dispatches.get(
            outcome.work_item_id,
            _DispatchRunTurnObservation(
                dispatch_id="",
                started_at_epoch=None,
                observable=True,
            ),
        )
        journal.append(
            record=run_turn_check_record(
                sink=sink,
                work_item_id=outcome.work_item_id,
                dispatch_id=observation.dispatch_id,
                started_at_epoch=observation.started_at_epoch,
                observable=observation.observable,
            )
        )


def _dispatches_by_item(
    *, records: tuple[dict[str, object], ...]
) -> dict[str, _DispatchRunTurnObservation]:
    dispatches: dict[str, _DispatchRunTurnObservation] = {}
    for record in records:
        if record.get("stage") != "dispatch-id":
            continue
        work_item_id = record.get("work_item_id")
        dispatch_id = record.get("dispatch_id")
        if isinstance(work_item_id, str) and isinstance(dispatch_id, str):
            dispatches[work_item_id] = _DispatchRunTurnObservation(
                dispatch_id=dispatch_id,
                started_at_epoch=_epoch(record=record),
                observable=_observable_from_dispatch_record(record=record),
            )
    return dispatches


def _epoch(*, record: dict[str, object]) -> float | None:
    value = record.get("started_at_epoch")
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _observable_from_dispatch_record(*, record: dict[str, object]) -> bool:
    """Whether this dispatch's factory exports `run_turn` telemetry to us.

    Read from the dispatch record's OWN snapshot of the resolved factory
    configuration, never from the factory NAME. A name-keyed test could only
    ever answer for the one factory it names: `hp` was hard-coded here, so a
    second factory -- `hp-candidate`, whose Petri-era engine DOES export
    `run_turn` -- was reported as observable or unobservable by whether its
    name happened to differ from `hp`, which is not a fact about telemetry.

    An ABSENT declaration reads as "exports", which is today's answer for
    every factory but `hp` and is the fail-LOUD direction: an unobservable
    marking SUPPRESSES the absence finding `items_with_run_turn_absence`
    surfaces, so defaulting to unobservable would silence the guard for every
    factory nobody had declared yet.
    """
    exports = record.get("dispatch_factory_exports_run_turn_telemetry")
    if isinstance(exports, bool):
        return exports
    return True
