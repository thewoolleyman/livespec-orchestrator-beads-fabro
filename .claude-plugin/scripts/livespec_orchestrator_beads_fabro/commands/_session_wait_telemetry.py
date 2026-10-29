"""Publishes the wait command's lifecycle and inventory as session telemetry events.

The publisher is the one place that knows which facts of a wait become which
event, and what each event is allowed to carry. It receives facts the wait
already computed (it never probes a target, reads a record or runs a command)
and hands curated events to a sink that only enqueues, so nothing here can move
a deadline or change a result.

Identity is repository name, session id and wait id; the target is an opaque
digest of its identity, because a gate or pane identity embeds filesystem
paths that must not leave the host. Work-item, dispatch and run associations
are stamped only when the caller's environment names them, and never invented.
A wait owns one stable trace, so arming, observation, return, acknowledgement
and inventory observations of the same wait join one trace.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from livespec_orchestrator_beads_fabro.commands._dispatcher_correlation import (
    is_identifier_shaped,
)
from livespec_orchestrator_beads_fabro.commands._session_inventory_events import (
    inventory_events,
)
from livespec_orchestrator_beads_fabro.commands._session_telemetry_events import (
    SessionEvent,
    rfc3339,
)
from livespec_orchestrator_beads_fabro.commands._session_telemetry_gate import (
    ObservationGate,
    load_gate,
    save_gate,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_ack import AckFacts
from livespec_orchestrator_beads_fabro.commands._session_wait_events import (
    Subject,
    build_event,
    digest,
    observation_signature,
    target_attributes,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_types import (
    GateObservation,
    WaitRequest,
    WaitResult,
)
from livespec_orchestrator_beads_fabro.commands.session_wait_inventory import InventorySnapshot

__all__: list[str] = [
    "DISPATCH_ENV",
    "FABRO_RUN_ENV",
    "WORK_ITEM_ENV",
    "Associations",
    "EventSink",
    "ObservationReporter",
    "SessionWaitPublisher",
    "associations_from_environ",
    "observation_reporter",
]

WORK_ITEM_ENV = "LIVESPEC_WORK_ITEM_ID"
DISPATCH_ENV = "LIVESPEC_DISPATCH_ID"
FABRO_RUN_ENV = "LIVESPEC_FABRO_RUN_ID"


class EventSink(Protocol):
    @property
    def exporting(self) -> bool: ...

    def emit(self, *, event: SessionEvent) -> None: ...


@dataclass(frozen=True, kw_only=True)
class Associations:
    """Work associations the caller's environment names; each absent when unknown."""

    work_item_id: str | None = None
    dispatch_id: str | None = None
    fabro_run_id: str | None = None

    def attributes(self) -> dict[str, str]:
        """The associations known, under their allowlisted attribute names."""
        named = {
            "work.item.id": self.work_item_id,
            "livespec.dispatch.id": self.dispatch_id,
            "fabro.run_id": self.fabro_run_id,
        }
        return {key: value for key, value in named.items() if value is not None}


def associations_from_environ(*, environ: dict[str, str]) -> Associations:
    """Read the associations, keeping only values shaped like identifiers."""

    def known(*, name: str) -> str | None:
        value = environ.get(name, "").strip()
        return value if value != "" and is_identifier_shaped(value=value) else None

    return Associations(
        work_item_id=known(name=WORK_ITEM_ENV),
        dispatch_id=known(name=DISPATCH_ENV),
        fabro_run_id=known(name=FABRO_RUN_ENV),
    )


@dataclass(kw_only=True)
class SessionWaitPublisher:
    """Turns wait facts into curated events for one command invocation."""

    sink: EventSink
    associations: Associations = field(default_factory=Associations)
    gate_path: Path | None = None
    _wait_gate: ObservationGate = field(default_factory=ObservationGate, init=False, repr=False)
    _polled: dict[str, int] = field(default_factory=dict, init=False, repr=False)

    def armed(self, *, request: WaitRequest, armed_at: float) -> None:
        kinds = {target.kind for target in request.targets}
        identities = sorted(target.identity for target in request.targets)
        self._publish(
            name="session.wait.armed",
            at=armed_at,
            subject=self._request_subject(request=request),
            attributes={
                "session.wait.target.kind": (
                    next(iter(kinds)) if len(kinds) == 1 else ("mixed" if kinds else None)
                ),
                "session.wait.target.id": digest(text="|".join(identities)),
                "session.wait.target_count": len(request.targets),
                "session.wait.budget_seconds": float(request.deadline_seconds),
                "session.observation.time": rfc3339(at=armed_at),
                "session.wait.waiter_alive": True,
            },
        )

    def observed(
        self,
        *,
        request: WaitRequest,
        observation: GateObservation,
        at: float,
        elapsed_seconds: float,
        age_seconds: float,
    ) -> None:
        sequence = self._polled.get(request.wait_id, 0) + 1
        self._polled[request.wait_id] = sequence
        admitted = self._wait_gate.admit(
            key=f"{request.wait_id}\0{observation.target.identity}",
            signature=observation_signature(observation=observation),
            now=at,
        )
        if not admitted:
            return
        self._publish(
            name="session.wait.observed",
            at=at,
            subject=self._request_subject(request=request),
            attributes={
                **target_attributes(target=observation.target),
                "session.observation.id": f"{request.wait_id}:{sequence}",
                "session.observation.sequence": sequence,
                "session.observation.time": rfc3339(at=at),
                "session.observation.state": observation.state,
                "session.observation.fresh": observation.fresh,
                "session.observation.age_seconds": max(0.0, age_seconds),
                "session.wait.elapsed_seconds": max(0.0, elapsed_seconds),
                "session.wait.waiter_alive": True,
            },
        )

    def returned(
        self,
        *,
        request: WaitRequest,
        result: WaitResult,
        at: float,
        elapsed_seconds: float,
        remaining_seconds: float,
    ) -> None:
        trigger = next(
            (t for t in request.targets if t.identity == result.trigger_target),
            None,
        )
        self._publish(
            name="session.wait.returned",
            at=at,
            subject=self._request_subject(request=request),
            attributes={
                **({} if trigger is None else target_attributes(target=trigger)),
                "session.wait.return_reason": result.command_outcome,
                "session.wait.trigger_exit_code": result.trigger_exit_code,
                "session.wait.target_count": len(request.targets),
                "session.wait.budget_seconds": float(request.deadline_seconds),
                "session.wait.elapsed_seconds": max(0.0, elapsed_seconds),
                "session.wait.remaining_seconds": max(0.0, remaining_seconds),
                "session.observation.time": rfc3339(at=at),
            },
        )

    def acknowledged(self, *, facts: AckFacts) -> None:
        self._publish(
            name="session.wait.acknowledged",
            at=facts.at,
            subject=Subject(
                repository=facts.repository,
                session_id=facts.session_id,
                wait_id=facts.wait_id,
                associations=facts.associations,
            ),
            attributes={
                "session.wait.acknowledged": True,
                "session.wait.return_reason": facts.return_reason,
                "session.wait.elapsed_seconds": (
                    None if facts.armed_at is None else max(0.0, facts.at - facts.armed_at)
                ),
                "session.observation.time": rfc3339(at=facts.at),
            },
        )

    def inventory(self, *, snapshot: InventorySnapshot) -> None:
        """Publish the snapshot summary and one observation per wait, rate limited.

        A sink that is not exporting consumes no gate state: a mark recorded for
        an event nobody will receive would suppress the first one that can be.
        """
        if not self.sink.exporting:
            return
        gate = ObservationGate() if self.gate_path is None else load_gate(path=self.gate_path)
        events = inventory_events(snapshot=snapshot, gate=gate)
        for event in events:
            self.sink.emit(event=event)
        if self.gate_path is not None:
            save_gate(path=self.gate_path, gate=gate, now=snapshot.observed_at)

    def associations_record(self) -> dict[str, str]:
        """The associations to persist beside the wait, so later events can name them."""
        return self.associations.attributes()

    def _request_subject(self, *, request: WaitRequest) -> Subject:
        return Subject(
            repository=str(request.repository),
            session_id=request.session_id,
            wait_id=request.wait_id,
            associations=self.associations.attributes(),
        )

    def _publish(
        self,
        *,
        name: str,
        at: float,
        subject: Subject,
        attributes: dict[str, object | None],
    ) -> None:
        self.sink.emit(event=build_event(name=name, at=at, subject=subject, attributes=attributes))


class ObservationReporter(Protocol):
    def __call__(self, *, observation: GateObservation) -> None: ...


def observation_reporter(
    *,
    request: WaitRequest,
    started_at: float,
    monotonic: Callable[[], float],
    wall_clock: Callable[[], float],
) -> ObservationReporter:
    """Report each accepted observation to the wait's publisher, if it has one."""
    publisher = request.publisher

    def report(*, observation: GateObservation) -> None:
        if publisher is None:
            return
        now = monotonic()
        publisher.observed(
            request=request,
            observation=observation,
            at=wall_clock(),
            elapsed_seconds=now - started_at,
            age_seconds=now - observation.observed_at,
        )

    return report
