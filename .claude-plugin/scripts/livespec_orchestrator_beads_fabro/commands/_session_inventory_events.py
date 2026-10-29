"""Event builders for one inventory snapshot of the durable wait records.

An inventory invocation publishes a summary plus one observation per wait. The
summary is published even for an empty inventory, as an explicit zero-count
snapshot with its own observation id and time, because an absence of events is
indistinguishable from an inventory that was never read. A wait record that
cannot be read is published as UNAVAILABLE with its diagnostic and no
fabricated state, so a damaged store never reads as a healthy empty one.

Each event passes the rate-limit gate, keyed so that a CHANGE is exported at
once and an unchanged observation at most once a minute.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._session_telemetry_events import (
    SessionEvent,
    rfc3339,
)
from livespec_orchestrator_beads_fabro.commands._session_telemetry_gate import ObservationGate
from livespec_orchestrator_beads_fabro.commands._session_wait_events import (
    Subject,
    build_event,
    observation_signature,
    target_attributes,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_types import observation_is_running
from livespec_orchestrator_beads_fabro.commands.session_wait_inventory import (
    InventoryRecord,
    InventorySnapshot,
)

__all__: list[str] = ["inventory_events"]

_WAITER_GONE_FINDINGS = frozenset({"waiter-missing", "waiter-replaced"})
_STATE_UNAVAILABLE = "unavailable"
_UNAVAILABLE_RECORDS = "wait_record"


def inventory_events(*, snapshot: InventorySnapshot, gate: ObservationGate) -> list[SessionEvent]:
    """The snapshot summary and one observation per wait, each rate limited by the gate."""
    records = snapshot.records
    available = [record for record in records if record.record_state == "available"]
    active = sum(
        1
        for record in available
        if any(observation_is_running(observation=o) for o in record.observations)
    )
    unacknowledged = sum(1 for record in available if not record.acknowledged)
    unavailable = len(records) - len(available)
    events: list[SessionEvent] = []
    summary_signature = f"{len(records)}|{active}|{unacknowledged}|{unavailable}"
    if gate.admit(key="inventory", signature=summary_signature, now=snapshot.observed_at):
        events.append(
            build_event(
                name="session.wait.inventory",
                at=snapshot.observed_at,
                subject=Subject(repository=None, session_id=None, wait_id=None, associations={}),
                attributes={
                    "session.observation.id": snapshot.observation_id,
                    "session.observation.time": rfc3339(at=snapshot.observed_at),
                    "session.inventory.wait_count": len(records),
                    "session.inventory.active_count": active,
                    "session.inventory.unacknowledged_count": unacknowledged,
                    "session.observation.unavailable": (
                        [_UNAVAILABLE_RECORDS] if unavailable else None
                    ),
                },
            )
        )
    for record in records:
        events.extend(_record_events(snapshot=snapshot, record=record, gate=gate))
    return events


def _record_events(
    *, snapshot: InventorySnapshot, record: InventoryRecord, gate: ObservationGate
) -> list[SessionEvent]:
    if record.record_state != "available":
        return _unavailable_record_events(snapshot=snapshot, record=record, gate=gate)
    waiter_alive = not (record.findings & _WAITER_GONE_FINDINGS)
    overdue = (
        None
        if "overdue" not in record.findings or record.deadline_at is None
        else max(0.0, snapshot.observed_at - record.deadline_at)
    )
    events: list[SessionEvent] = []
    for observation in record.observations:
        signature = f"{observation_signature(observation=observation)}|{sorted(record.findings)}"
        key = f"{record.wait_id}\0{observation.target.identity}"
        if not gate.admit(key=key, signature=signature, now=snapshot.observed_at):
            continue
        events.append(
            build_event(
                name="session.wait.observed",
                at=snapshot.observed_at,
                subject=Subject(
                    repository=record.repository,
                    session_id=record.session_id,
                    wait_id=record.wait_id,
                    associations=dict(record.associations),
                ),
                attributes={
                    **target_attributes(target=observation.target),
                    "session.observation.id": snapshot.observation_id,
                    "session.observation.sequence": record.observation_sequence,
                    "session.observation.time": rfc3339(at=snapshot.observed_at),
                    "session.observation.state": observation.state,
                    "session.observation.fresh": observation.fresh,
                    "session.observation.age_seconds": (
                        max(0.0, snapshot.observed_at - observation.observed_at)
                        if observation.fresh
                        else None
                    ),
                    "session.wait.waiter_alive": waiter_alive,
                    "session.wait.acknowledged": record.acknowledged,
                    "session.wait.overdue_seconds": overdue,
                },
            )
        )
    return events


def _unavailable_record_events(
    *, snapshot: InventorySnapshot, record: InventoryRecord, gate: ObservationGate
) -> list[SessionEvent]:
    diagnostic = record.diagnostic or _STATE_UNAVAILABLE
    admitted = gate.admit(
        key=f"{record.wait_id}\0record",
        signature=f"{_STATE_UNAVAILABLE}|{diagnostic}",
        now=snapshot.observed_at,
    )
    if not admitted:
        return []
    return [
        build_event(
            name="session.wait.observed",
            at=snapshot.observed_at,
            subject=Subject(
                repository=None, session_id=None, wait_id=record.wait_id, associations={}
            ),
            attributes={
                "session.observation.id": snapshot.observation_id,
                "session.observation.time": rfc3339(at=snapshot.observed_at),
                "session.observation.state": _STATE_UNAVAILABLE,
                "session.observation.unavailable": [diagnostic],
            },
        )
    ]
