"""The consumer and launch paths publish through the same recording seam.

`test_session_recovery_telemetry` drives the recording seam itself; these cases
drive the PUBLIC paths that call it — a real consumer pass over an on-disk
attempt, `protected_launch` and `protected_completion` — because a seam nobody
calls publishes nothing. Each case asserts what a pass actually left in the sink,
including the order relative to the launch effect: registration and coverage must
be published BEFORE the effect runs, since an effect that stalls is exactly the
case the events exist to explain.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._session_obligation_coverage import (
    CoverageDeclaration,
    CoverageReading,
)
from livespec_orchestrator_beads_fabro.commands._session_obligation_launch import (
    protected_completion,
    protected_launch,
)
from livespec_orchestrator_beads_fabro.commands._session_obligation_records import (
    LaunchAuthority,
    LaunchIntent,
    LaunchTarget,
)
from livespec_orchestrator_beads_fabro.commands._session_recovery_action import (
    AuthoritativeEvidence,
    Reading,
)
from livespec_orchestrator_beads_fabro.commands._session_recovery_consumer import (
    ConsumerRequest,
    consume_recovery_obligation,
)
from livespec_orchestrator_beads_fabro.commands._session_recovery_effect import RecoveryEffect
from livespec_orchestrator_beads_fabro.commands._session_recovery_records import (
    TRANSITION_NOTIFICATION,
    RecoveryAttempt,
    open_recovery_attempt,
)
from livespec_orchestrator_beads_fabro.commands._session_recovery_safety import (
    HumanHold,
    SafetyState,
)
from livespec_orchestrator_beads_fabro.commands._session_recovery_telemetry import (
    TransitionScope,
    record_transition,
)
from livespec_orchestrator_beads_fabro.commands._session_telemetry_events import SessionEvent

from tests.integration.session_recovery_doubles import RecordingCommand, RecordingLookup

_ITEM = "bd-ib-dle6l3"
_EPIC = "bd-ib-jnpvh4"
_DEADLINE = "2026-10-21T02:00:00Z"
_DUE = datetime(2026, 10, 21, 2, 0, tzinfo=timezone.utc).timestamp()
_EPOCH = 14
_EFFECT = RecoveryEffect(
    operation=f"reconcile-merged:{_ITEM}",
    identity="gate:20261021T014500Z-7",
    next_action=f"impl:{_ITEM}",
)
_TRANSITIONS = [
    "session.recovery.notification",
    "session.recovery.receipt",
    "session.recovery.claimed",
    "session.recovery.started",
    "session.recovery.executed",
    "session.recovery.reconciled",
]


@dataclass(kw_only=True)
class _Sink:
    exporting: bool = True
    events: list[SessionEvent] = field(default_factory=list)

    def emit(self, *, event: SessionEvent) -> None:
        self.events.append(event)

    def names(self) -> list[str]:
        return [event.name for event in self.events]


def _store(*, tmp_path: Path) -> Path:
    store = tmp_path / "recovery"
    _ = open_recovery_attempt(
        recovery_store_root=store,
        attempt=RecoveryAttempt(
            attempt_id="attempt-1",
            operation_id="op-1",
            required_result_identity="item_status bd-ib-dle6l3 status closed",
            result_epoch=_EPOCH,
            original_deadline=_DEADLINE,
        ),
        opened_at=0.0,
    )
    return store


def _notify(*, store: Path, sink: _Sink) -> None:
    _ = record_transition(
        scope=TransitionScope(
            recovery_store_root=store,
            attempt_id="attempt-1",
            observed_at=_DUE + 10.0,
            telemetry=sink,
        ),
        transition=TRANSITION_NOTIFICATION,
    )


def _evidence() -> AuthoritativeEvidence:
    return AuthoritativeEvidence(
        item_id=_ITEM,
        epic_id=_EPIC,
        recorded_next_operation=f"diagnose-plan-progress:{_EPIC}",
        recorded_operation_completed=True,
        ledger_status=Reading(value="active"),
        merged_pull_request=Reading(value="9117b1c8"),
        remote_run_outcome=Reading(value="succeeded"),
        local_gate_outcome="failed",
        recorded_epoch=_EPOCH,
        current_epoch=_EPOCH,
    )


def _safety(
    *, hold: HumanHold | None = None, commit: bool = False, pair: bool = False
) -> SafetyState:
    return SafetyState(
        hold=hold,
        commit_hook_running=commit,
        red_green_pair_open=pair,
        session_idle=True,
        notification_unanswered=True,
        prose_deadline="we should be done by 14:25",
        stale_diagnostic=f"diagnose-plan-progress:{_EPIC}",
    )


def _consume(*, store: Path, sink: _Sink, safety: SafetyState) -> None:
    _ = consume_recovery_obligation(
        request=ConsumerRequest(
            recovery_store_root=store,
            attempt_id="attempt-1",
            consumer="overseerd@hp",
            observed_at=_DUE + 40.0,
            lease_seconds=30.0,
            telemetry=sink,
        ),
        evidence=_evidence(),
        safety=safety,
        command=RecordingCommand(effect=_EFFECT),
        reader=RecordingLookup(),
    )


def test_a_full_pass_publishes_each_transition_as_its_own_identity_linked_event(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path=tmp_path)
    sink = _Sink()
    _notify(store=store, sink=sink)
    _consume(store=store, sink=sink, safety=_safety())

    assert sink.names() == _TRANSITIONS
    assert len({event.trace_key for event in sink.events}) == 1
    for event in sink.events:
        attributes = event.attributes
        assert attributes["session.obligation.id"] == "op-1"
        assert attributes["session.obligation.epoch"] == "14"
        assert attributes["session.obligation.deadline"] == _DEADLINE
        assert attributes["session.recovery.attempt_id"] == "attempt-1"
        assert attributes["session.recovery.state"] == event.name.removeprefix("session.recovery.")
        assert attributes["session.recovery.duplicate_count"] == 0
        assert attributes["session.recovery.fenced_count"] == 0
        assert "session.recovery.unavailable" not in attributes
        assert "fulfilled" not in " ".join([*attributes, *map(str, attributes.values())])
    notification, receipt, _, started, executed, reconciled = (e.attributes for e in sink.events)
    assert notification["session.observation.time"] == "2026-10-21T02:00:10Z"
    assert "session.recovery.latency_seconds" not in notification
    assert receipt["session.recovery.latency_seconds"] == 30.0
    assert started["session.recovery.latency_seconds"] == 30.0
    assert executed["session.recovery.latency_seconds"] == 30.0
    assert executed["session.obligation.overdue_seconds"] == 40.0
    assert reconciled["session.recovery.next_action"] == _EFFECT.next_action
    assert "session.recovery.next_action" not in executed


@pytest.mark.parametrize(
    ("safety", "reason"),
    [
        (
            _safety(
                hold=HumanHold(
                    authority="maintainer",
                    reason="storage move",
                    owner="thewoolleyman",
                    release_condition="move completes",
                )
            ),
            "human_hold",
        ),
        (_safety(commit=True), "commit_or_hook"),
        (_safety(pair=True), "red_green_pair"),
    ],
)
def test_a_safety_deferral_publishes_its_reason_and_no_execution(
    tmp_path: Path, safety: SafetyState, reason: str
) -> None:
    store = _store(tmp_path=tmp_path)
    sink = _Sink()
    _notify(store=store, sink=sink)
    _consume(store=store, sink=sink, safety=safety)

    assert sink.names() == [
        "session.recovery.notification",
        "session.recovery.receipt",
        "session.recovery.claimed",
        "session.recovery.deferred",
    ]
    assert sink.events[-1].attributes["session.recovery.deferral_reason"] == reason


def _intent(*, repository: Path, operation_id: str = "op-launch") -> LaunchIntent:
    return LaunchIntent(
        operation_id=operation_id,
        authority=LaunchAuthority(
            session_id="session-l",
            repository=repository,
            invoker="role:dispatcher",
            scope="item:bd-ib-zejlae",
        ),
        required_result_identity="item_status bd-ib-zejlae status closed",
        result_epoch=5,
        original_deadline="2026-10-15T09:00:00Z",
    )


def _covered() -> CoverageReading:
    return CoverageReading(
        declaration=CoverageDeclaration(
            runtime="codex",
            runtime_version="0.58.0",
            terminal_backend="herdr",
            terminal_version="1.4.0",
            terminal_instance="tmux:/run/herdr.sock",
            service_identity="overseerd@hp",
            service_generation="1760500000",
            recovery_route="overseer-supervised-service",
            max_observation_interval_seconds=20.0,
            takeover_budget_seconds=20.0,
            proof_artifact="scenario-160-capture",
        )
    )


def _launched(*, operation_id: str) -> LaunchTarget:
    return LaunchTarget(kind="gate", identity=f"gate:/g:{operation_id}")


def _launch(*, operation_id: str) -> LaunchTarget:
    return _launched(operation_id=operation_id)


def test_a_protected_launch_publishes_registration_and_coverage_before_the_effect(
    tmp_path: Path,
) -> None:
    sink = _Sink()
    effect_saw: list[list[str]] = []

    def effect(*, operation_id: str) -> LaunchTarget:
        effect_saw.append(sink.names())
        return _launched(operation_id=operation_id)

    verdict = protected_launch(
        intent=_intent(repository=tmp_path / "project"),
        coverage=_covered(),
        obligation_store_root=tmp_path / "obligations",
        effect=effect,
        now=1_700_000_000.0,
        telemetry=sink,
    )

    assert verdict.protected
    assert effect_saw == [["session.recovery.coverage", "session.obligation.registered"]]
    coverage, registered = (event.attributes for event in sink.events)
    assert coverage["session.coverage.state"] == "verified"
    assert registered["session.obligation.id"] == "op-launch"
    assert registered["session.obligation.epoch"] == "5"
    assert registered["session.obligation.deadline"] == "2026-10-15T09:00:00Z"
    assert registered["session.id"] == "session-l"
    assert registered["session.repository"] == "project"
    assert registered["session.coverage.state"] == "verified"
    assert registered["session.observation.time"] == "2023-11-14T22:13:20Z"
    assert sink.events[0].trace_key == sink.events[1].trace_key == "obligation:op-launch:5"


def test_an_unmonitored_launch_publishes_coverage_but_registers_nothing(tmp_path: Path) -> None:
    sink = _Sink()

    verdict = protected_launch(
        intent=_intent(repository=tmp_path),
        coverage=CoverageReading(declaration=None),
        obligation_store_root=tmp_path / "obligations",
        effect=_launch,
        now=1_700_000_000.0,
        telemetry=sink,
    )

    assert not verdict.protected
    assert sink.names() == ["session.recovery.coverage"]
    assert sink.events[0].attributes["session.coverage.state"] == "unmonitored"


def test_a_repeated_launch_is_not_registered_a_second_time(tmp_path: Path) -> None:
    sink = _Sink()
    intent = _intent(repository=tmp_path)
    for _ in range(2):
        _ = protected_launch(
            intent=intent,
            coverage=_covered(),
            obligation_store_root=tmp_path / "obligations",
            effect=_launch,
            now=1_700_000_000.0,
            telemetry=sink,
        )

    assert sink.names() == [
        "session.recovery.coverage",
        "session.obligation.registered",
        "session.recovery.coverage",
    ]


def test_a_completion_check_publishes_coverage_only_when_it_has_an_instant(
    tmp_path: Path,
) -> None:
    sink = _Sink()
    store = tmp_path / "obligations"

    _ = protected_completion(coverage=_covered(), obligation_store_root=store, telemetry=sink)
    assert sink.events == []
    _ = protected_completion(
        coverage=CoverageReading(declaration=None),
        obligation_store_root=store,
        telemetry=sink,
        now=1_700_000_000.0,
    )

    assert sink.names() == ["session.recovery.coverage"]
    assert sink.events[0].attributes["session.coverage.state"] == "unmonitored"
    assert "session.obligation.id" not in sink.events[0].attributes
