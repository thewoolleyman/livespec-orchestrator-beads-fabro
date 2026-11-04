"""Publishes obligation registration, recovery transitions and coverage as events.

`record_transition` is the one place a recovery transition is both written and
published, so the durable record and the telemetry cannot disagree about which
transition happened: the event is built from the record that the append just
wrote, and only when that append actually RECORDED a new observation. A
duplicate converges on the first observation and is counted, never published a
second time; the count rides the events that follow it.

Every event carries the opaque obligation id, the epoch (a string, passed
through exactly as the canonical reader supplied it), the original deadline and
the attempt id. The measurements are the ones that can be taken: latency from
the produced notification, and how far past the original deadline the pass is.
A measurement that cannot be taken is OMITTED and named in
`session.recovery.unavailable`; it is never published as a zero.

A recovery event describes what a consumer did. It never says the original
result was fulfilled: only the canonical result reader can establish that.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._session_obligation_records import LaunchIntent
from livespec_orchestrator_beads_fabro.commands._session_recovery_consumption import (
    transition_instant,
)
from livespec_orchestrator_beads_fabro.commands._session_recovery_records import (
    APPEND_RECORDED,
    TRANSITION_CLAIMED,
    TRANSITION_DEFERRED,
    TRANSITION_EXECUTED,
    TRANSITION_NOTIFICATION,
    TRANSITION_RECEIPT,
    TRANSITION_RECONCILED,
    TRANSITION_STARTED,
    append_recovery_transition,
    read_recovery_record,
    recovery_record_path,
)
from livespec_orchestrator_beads_fabro.commands._session_recovery_safety import (
    BARRIER_COMMIT_HOOK,
    BARRIER_HUMAN_HOLD,
    BARRIER_RED_GREEN_PAIR,
)
from livespec_orchestrator_beads_fabro.commands._session_telemetry_events import (
    EventSink,
    SessionEvent,
    rfc3339,
    session_event,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_lock import LockBudget

__all__: list[str] = [
    "TransitionScope",
    "publish_coverage",
    "publish_registered",
    "publish_transition",
    "record_transition",
]

_TRANSITION_EVENTS: dict[str, str] = {
    TRANSITION_NOTIFICATION: "session.recovery.notification",
    TRANSITION_RECEIPT: "session.recovery.receipt",
    TRANSITION_CLAIMED: "session.recovery.claimed",
    TRANSITION_STARTED: "session.recovery.started",
    TRANSITION_EXECUTED: "session.recovery.executed",
    TRANSITION_DEFERRED: "session.recovery.deferred",
    TRANSITION_RECONCILED: "session.recovery.reconciled",
}
_DEFERRAL_REASONS: dict[str, str] = {
    BARRIER_HUMAN_HOLD: "human_hold",
    BARRIER_COMMIT_HOOK: "commit_or_hook",
    BARRIER_RED_GREEN_PAIR: "red_green_pair",
}
_LATENCY = "session.recovery.latency_seconds"
_OVERDUE = "session.obligation.overdue_seconds"


@dataclass(frozen=True, kw_only=True)
class TransitionScope:
    """Where and when one transition is recorded, and who hears about it."""

    recovery_store_root: Path
    attempt_id: str
    observed_at: float
    lock_budget: LockBudget | None = None
    telemetry: EventSink | None = None


def record_transition(
    *, scope: TransitionScope, transition: str, detail: dict[str, object] | None = None
) -> str:
    """Append one transition and publish it, only when it was newly recorded."""
    status = append_recovery_transition(
        recovery_store_root=scope.recovery_store_root,
        attempt_id=scope.attempt_id,
        transition=transition,
        observed_at=scope.observed_at,
        detail=detail,
        lock_budget=scope.lock_budget,
    )
    if status == APPEND_RECORDED:
        publish_transition(scope=scope, transition=transition, detail=detail)
    return status


def publish_transition(
    *, scope: TransitionScope, transition: str, detail: dict[str, object] | None = None
) -> None:
    """Publish a transition that is already durable, from the record that holds it.

    Public because one transition, execution evidence, is written together with
    its effect in a single locked mutation rather than through the append, and
    it must still reach the sink exactly when that write landed.
    """
    sink = scope.telemetry
    if sink is None or not sink.exporting:
        return
    loaded = read_recovery_record(
        path=recovery_record_path(
            recovery_store_root=scope.recovery_store_root, attempt_id=scope.attempt_id
        )
    )
    if loaded.payload is None:
        return
    sink.emit(
        event=_transition_event(
            payload=loaded.payload,
            transition=transition,
            observed_at=scope.observed_at,
            detail=detail or {},
        )
    )


def _trace_key(*, operation_id: str, epoch: str) -> str:
    return f"obligation:{operation_id}:{epoch}"


def _deadline_epoch(*, deadline: str) -> float | None:
    try:
        parsed = datetime.fromisoformat(deadline.replace("Z", "+00:00"))
    except ValueError:
        return None
    return None if parsed.tzinfo is None else parsed.timestamp()


def _transition_event(
    *, payload: dict[str, object], transition: str, observed_at: float, detail: dict[str, object]
) -> SessionEvent:
    operation_id = str(payload["operation_id"])
    epoch = str(payload["result_epoch"])
    deadline = str(payload["original_deadline"])
    unavailable: list[str] = []
    latency: float | None = None
    if transition != TRANSITION_NOTIFICATION:
        notified = transition_instant(payload=payload, transition=TRANSITION_NOTIFICATION)
        if notified is None or observed_at < notified:
            unavailable.append(_LATENCY)
        else:
            latency = observed_at - notified
    due = _deadline_epoch(deadline=deadline)
    if due is None:
        unavailable.append(_OVERDUE)
    barrier = detail.get("barrier")
    next_action = detail.get("next_action")
    return session_event(
        name=_TRANSITION_EVENTS[transition],
        at=observed_at,
        trace_key=_trace_key(operation_id=operation_id, epoch=epoch),
        attributes={
            "session.obligation.id": operation_id,
            "session.obligation.epoch": epoch,
            "session.obligation.deadline": deadline,
            "session.recovery.attempt_id": str(payload["attempt_id"]),
            "session.recovery.state": transition,
            "session.observation.time": rfc3339(at=observed_at),
            _LATENCY: latency,
            _OVERDUE: None if due is None else max(0.0, observed_at - due),
            "session.recovery.duplicate_count": payload["duplicate_count"],
            "session.recovery.fenced_count": payload["fenced_count"],
            "session.recovery.deferral_reason": (
                _DEFERRAL_REASONS.get(barrier)
                if transition == TRANSITION_DEFERRED and isinstance(barrier, str)
                else None
            ),
            "session.recovery.next_action": (
                next_action
                if transition == TRANSITION_RECONCILED and isinstance(next_action, str)
                else None
            ),
            "session.recovery.unavailable": unavailable or None,
        },
    )


def _launch_attributes(*, intent: LaunchIntent) -> dict[str, object | None]:
    return {
        "session.obligation.id": intent.operation_id,
        "session.obligation.epoch": str(intent.result_epoch),
        "session.obligation.deadline": intent.original_deadline,
        "session.id": intent.authority.session_id,
        "session.repository": intent.authority.repository.name,
    }


def publish_registered(
    *, telemetry: EventSink | None, intent: LaunchIntent, coverage_state: str, at: float
) -> None:
    """Publish that an obligation's launch intent was durably registered."""
    if telemetry is None:
        return
    telemetry.emit(
        event=session_event(
            name="session.obligation.registered",
            at=at,
            trace_key=_trace_key(operation_id=intent.operation_id, epoch=str(intent.result_epoch)),
            attributes={
                **_launch_attributes(intent=intent),
                "session.coverage.state": coverage_state,
                "session.observation.time": rfc3339(at=at),
            },
        )
    )


def publish_coverage(
    *, telemetry: EventSink | None, intent: LaunchIntent | None, state: str, at: float | None
) -> None:
    """Publish the graded coverage state, for a launch or a turn-completion check."""
    if telemetry is None or at is None:
        return
    identity = {} if intent is None else _launch_attributes(intent=intent)
    telemetry.emit(
        event=session_event(
            name="session.recovery.coverage",
            at=at,
            trace_key=(
                "coverage"
                if intent is None
                else _trace_key(operation_id=intent.operation_id, epoch=str(intent.result_epoch))
            ),
            attributes={
                **identity,
                "session.coverage.state": state,
                "session.observation.time": rfc3339(at=at),
            },
        )
    )
