"""Fresh reconciliation of durable host-session wait records."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast
from uuid import uuid4

from livespec_orchestrator_beads_fabro.commands._session_wait_records import (
    DIAGNOSTIC_RECORD_DISPOSED,
    read_wait_record,
    wait_store_lock,
    write_wait_record,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_routing import (
    wait_target_from_payload,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_types import (
    GateObservation,
    WaitTarget,
    observation_is_running,
)

__all__: list[str] = [
    "InventoryRecord",
    "InventorySnapshot",
    "inventory_waits",
]


@dataclass(frozen=True, kw_only=True)
class InventoryRecord:
    wait_id: str
    record_state: str
    diagnostic: str | None
    findings: frozenset[str]
    observations: tuple[GateObservation, ...]
    observation_sequence: int


@dataclass(frozen=True, kw_only=True)
class InventorySnapshot:
    observation_id: str
    observed_at: float
    records: tuple[InventoryRecord, ...]


class TargetObserver(Protocol):
    def __call__(self, *, target: WaitTarget, observed_at: float) -> GateObservation: ...


class ProcessGeneration(Protocol):
    def __call__(self, *, pid: int) -> str | None: ...


def _unavailable_record(
    *,
    wait_id: str,
    diagnostic: str,
    observations: tuple[GateObservation, ...] = (),
) -> InventoryRecord:
    return InventoryRecord(
        wait_id=wait_id,
        record_state="unavailable",
        diagnostic=diagnostic,
        findings=frozenset({diagnostic}),
        observations=observations,
        observation_sequence=0,
    )


def _inventory_record(
    *,
    payload: dict[str, object],
    observed_at: float,
    observe_target: TargetObserver,
    process_generation: ProcessGeneration,
) -> InventoryRecord:
    targets = cast("list[dict[str, object]]", payload["targets"])
    observations = tuple(
        observe_target(
            target=wait_target_from_payload(payload=target_payload),
            observed_at=observed_at,
        )
        for target_payload in targets
    )
    waiter = cast("dict[str, object]", payload["waiter"])
    actual_generation = process_generation(pid=int(str(waiter["pid"])))
    findings: set[str] = set()
    if actual_generation is None:
        findings.add("waiter-missing")
    elif actual_generation != str(waiter["generation"]):
        findings.add("waiter-replaced")
    waiter_unavailable = actual_generation != str(waiter["generation"])
    # Running-ness is per target KIND, so these two tests go through the
    # shared predicate: a `working` pane measured against the gate state name
    # alone would read as a target that had already ended, which is both a
    # missing `running-without-waiter` finding and a fabricated
    # `ended-unacknowledged` one.
    if waiter_unavailable and any(
        observation_is_running(observation=observation) for observation in observations
    ):
        findings.add("running-without-waiter")
    acknowledgement = cast("dict[str, object]", payload["acknowledgement"])
    if not bool(acknowledgement["acknowledged"]) and any(
        not observation_is_running(observation=observation) for observation in observations
    ):
        findings.add("ended-unacknowledged")
    if observed_at > float(str(payload["deadline_at"])) and not bool(payload["return_ready"]):
        findings.add("overdue")
    return InventoryRecord(
        wait_id=str(payload["wait_id"]),
        record_state="available",
        diagnostic=None,
        findings=frozenset(findings),
        observations=observations,
        observation_sequence=int(str(payload["observation_sequence"])) + 1,
    )


def _persist_inventory_record(*, path: Path, record: InventoryRecord) -> InventoryRecord:
    """Write the fresh round back, unless the record was disposed meanwhile.

    The re-read happens under the lock, and the record was readable moments
    ago when this pass started observing its targets. So a record that is not
    readable NOW reached explicit disposition in between — a receipt
    acknowledgement and its bounded retention sweep are exactly that — and
    writing it back would RESURRECT inventory its receiving owner has already
    discharged. The round that was genuinely observed is still reported; only
    the record it belonged to is gone.
    """
    loaded = read_wait_record(path=path)
    if loaded.payload is None:
        return _unavailable_record(
            wait_id=record.wait_id,
            diagnostic=DIAGNOSTIC_RECORD_DISPOSED,
            observations=record.observations,
        )
    payload = loaded.payload
    payload["observation_sequence"] = record.observation_sequence
    payload["observations"] = [
        {
            "exit_code": observation.exit_code,
            "fresh": observation.fresh,
            "observed_at": observation.observed_at,
            "state": observation.state,
            "target": observation.target.identity,
        }
        for observation in record.observations
    ]
    write_wait_record(path=path, payload=payload)
    return record


def inventory_waits(
    *,
    wait_store_root: Path,
    observed_at: float,
    observe_target: TargetObserver,
    process_generation: ProcessGeneration,
) -> InventorySnapshot:
    records: list[InventoryRecord] = []
    wait_store_root.mkdir(parents=True, exist_ok=True)
    for path in sorted(wait_store_root.glob("*.json")):
        loaded = read_wait_record(path=path)
        if loaded.payload is None:
            records.append(
                _unavailable_record(
                    wait_id=path.stem,
                    diagnostic=str(loaded.diagnostic),
                )
            )
            continue
        record = _inventory_record(
            payload=loaded.payload,
            observed_at=observed_at,
            observe_target=observe_target,
            process_generation=process_generation,
        )
        with wait_store_lock(wait_store_root=wait_store_root):
            records.append(_persist_inventory_record(path=path, record=record))
    return InventorySnapshot(
        observation_id=uuid4().hex,
        observed_at=observed_at,
        records=tuple(records),
    )
