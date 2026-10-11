"""Post-dispatch `run_turn` telemetry assertion for the Dispatcher."""

from __future__ import annotations

from collections.abc import Mapping
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_turn_telemetry_export import (
    factory_run_turn_observation,
    run_turn_telemetry_block,
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
    observation: str | None


def append_run_turn_checks(
    *,
    outcomes: tuple[DispatchOutcome, ...],
    journal: JournalWriter,
    journal_path: Path,
    repo: Path,
    sink: RunTurnSink,
) -> None:
    """Append one non-blocking `run_turn` export assertion per green dispatch."""
    dispatches = _dispatches_by_item(
        records=read_journal_records(journal_path=journal_path),
        block=run_turn_telemetry_block(repo=repo),
    )
    for outcome in outcomes:
        if outcome.status != "green":
            continue
        observation = dispatches.get(
            outcome.work_item_id,
            _DispatchRunTurnObservation(
                dispatch_id="",
                started_at_epoch=None,
                observation=None,
            ),
        )
        journal.append(
            record=run_turn_check_record(
                sink=sink,
                work_item_id=outcome.work_item_id,
                dispatch_id=observation.dispatch_id,
                started_at_epoch=observation.started_at_epoch,
                observation=observation.observation,
            )
        )


def _dispatches_by_item(
    *, records: tuple[dict[str, object], ...], block: Mapping[str, object] | None
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
                observation=_observation_from_dispatch_record(record=record, block=block),
            )
    return dispatches


def _epoch(*, record: dict[str, object]) -> float | None:
    value = record.get("started_at_epoch")
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _observation_from_dispatch_record(
    *, record: dict[str, object], block: Mapping[str, object] | None
) -> str | None:
    """Why this dispatch's `run_turn` telemetry is unreadable here, or `None`.

    A record naming NO factory is answered without consulting the configuration
    at all: there is no factory to ask about, and the dispatch therefore ran
    against whatever ambient engine this host resolves — which is this host's.
    So this arm reports OBSERVABLE even where the configuration is unreadable,
    because nothing it could have read bears on the answer.
    """
    factory = record.get("dispatch_factory")
    if not isinstance(factory, str) or factory == "":
        return None
    return factory_run_turn_observation(block=block, factory=factory)
