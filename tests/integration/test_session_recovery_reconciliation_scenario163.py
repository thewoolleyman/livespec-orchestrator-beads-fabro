"""Scenario 163 — duplicate and stale recovery reconcile safely.

`contracts.md` section "Launch obligations and consumed recovery": "Recovery MUST
use the canonical stable attempt id with serialized generation-fenced ownership.
Duplicate events, concurrent consumers and restart MUST converge on one observed
effect for the supported idempotent recovery command. After an ambiguous
execution crash the consumer MUST query durable command effects before retrying,
retain unobservable state if it cannot decide." And: "A stale pointer to a
completed diagnostic MUST be reconciled; a failed local gate MUST NOT be treated
as proof that its remote run or merged PR failed."

Driven through the PUBLIC consumer surface over a real on-disk store, with ONE
command object shared across every pass so the convergence claim is a count of
real invocations rather than an inspection of returned values.

THE FIXTURE IS THE MEASURED 2026-10-09 CASE. The local gate reported FAILED at
05:19:06Z for a pull request that had merged at 05:18:03Z, the epic's pointer
named a diagnostic that had already completed, and the correct action was the
per-item `reconcile-merged` rather than a redispatch. So the evidence here
carries a failed gate, a merged pull request and a completed pointer together —
which is the only shape where choosing `reconcile-merged` can be attributed to
the forge reading rather than to the ladder having one rung.

THE CONTROL FOR "NO BLIND REDISPATCH" IS THE GREEN-GATE PASS. A build that read
the gate outcome would select differently for a green gate, so the second leg
runs the identical evidence with the gate succeeding and asserts the SAME
operation. Without it, the first leg is equally consistent with a build that
redispatches on any gate failure and happened to be handed a merge.

THE AMBIGUOUS LEG USES A SEPARATE ATTEMPT, because the convergence leg has
already recorded an effect and a recorded effect short-circuits the lookup the
ambiguity exists to exercise.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._session_recovery_action import (
    AuthoritativeEvidence,
    Reading,
)
from livespec_orchestrator_beads_fabro.commands._session_recovery_consumer import (
    ConsumerRequest,
    consume_recovery_obligation,
)
from livespec_orchestrator_beads_fabro.commands._session_recovery_effect import (
    RecoveryEffect,
    recorded_effect,
)
from livespec_orchestrator_beads_fabro.commands._session_recovery_execution import (
    EXECUTION_UNCERTAIN,
)
from livespec_orchestrator_beads_fabro.commands._session_recovery_lease import (
    FENCE_CURRENT,
    FENCE_SUPERSEDED,
    fence_state,
)
from livespec_orchestrator_beads_fabro.commands._session_recovery_outcome import (
    CONSUMER_CONVERGED,
    CONSUMER_EXECUTED,
)
from livespec_orchestrator_beads_fabro.commands._session_recovery_records import (
    TRANSITION_NOTIFICATION,
    RecoveryAttempt,
    append_recovery_transition,
    open_recovery_attempt,
    read_recovery_record,
    recovery_record_path,
)
from livespec_orchestrator_beads_fabro.commands._session_recovery_safety import SafetyState

from tests.integration.session_recovery_doubles import RecordingCommand, RecordingLookup

_ITEM = "bd-ib-dle6l3"
_EPIC = "bd-ib-jnpvh4"
_RECONCILE = f"reconcile-merged:{_ITEM}"
_DEADLINE = "2026-10-21T03:00:00Z"
_EPOCH = 15
_EFFECT = RecoveryEffect(
    operation=_RECONCILE,
    identity="gate:20261021T024500Z-5",
    next_action=f"impl:{_ITEM}",
)


def _notified_store(*, tmp_path: Path, attempt_id: str) -> Path:
    store = tmp_path / "recovery"
    _ = open_recovery_attempt(
        recovery_store_root=store,
        attempt=RecoveryAttempt(
            attempt_id=attempt_id,
            operation_id=f"op-{attempt_id}",
            required_result_identity="pull_request_state #2375 state MERGED",
            result_epoch=_EPOCH,
            original_deadline=_DEADLINE,
        ),
        opened_at=0.0,
    )
    _ = append_recovery_transition(
        recovery_store_root=store,
        attempt_id=attempt_id,
        transition=TRANSITION_NOTIFICATION,
        observed_at=300.0,
    )
    return store


def _payload(*, store: Path, attempt_id: str) -> dict[str, object]:
    read = read_recovery_record(
        path=recovery_record_path(recovery_store_root=store, attempt_id=attempt_id)
    )
    assert read.payload is not None
    return read.payload


def _request(*, store: Path, attempt_id: str, consumer: str, observed_at: float) -> ConsumerRequest:
    return ConsumerRequest(
        recovery_store_root=store,
        attempt_id=attempt_id,
        consumer=consumer,
        observed_at=observed_at,
        lease_seconds=30.0,
    )


def _evidence(*, local_gate_outcome: str = "failed") -> AuthoritativeEvidence:
    """The measured case: failed gate, merged pull request, completed pointer."""
    return AuthoritativeEvidence(
        item_id=_ITEM,
        epic_id=_EPIC,
        recorded_next_operation=f"diagnose-plan-progress:{_EPIC}",
        recorded_operation_completed=True,
        ledger_status=Reading(value="active"),
        merged_pull_request=Reading(value="9117b1c8ea6b8ebb56572a7f91bd86d27a02ee63"),
        remote_run_outcome=Reading(value="succeeded"),
        local_gate_outcome=local_gate_outcome,
        recorded_epoch=_EPOCH,
        current_epoch=_EPOCH,
    )


def _safety() -> SafetyState:
    return SafetyState(
        hold=None,
        commit_hook_running=False,
        red_green_pair_open=False,
        session_idle=True,
        notification_unanswered=True,
        prose_deadline="we should be done by 14:25",
        stale_diagnostic=f"diagnose-plan-progress:{_EPIC}",
    )


def test_scenario_163_duplicate_and_replacement_consumers_yield_one_command_effect(
    *, tmp_path: Path
) -> None:
    attempt = "attempt-scenario163-converge"
    store = _notified_store(tmp_path=tmp_path, attempt_id=attempt)
    command = RecordingCommand(effect=_EFFECT)

    first = consume_recovery_obligation(
        request=_request(
            store=store, attempt_id=attempt, consumer="overseerd@hp", observed_at=310.0
        ),
        evidence=_evidence(),
        safety=_safety(),
        command=command,
        reader=RecordingLookup(),
    )
    duplicate = consume_recovery_obligation(
        request=_request(
            store=store, attempt_id=attempt, consumer="overseerd@hp", observed_at=311.0
        ),
        evidence=_evidence(),
        safety=_safety(),
        command=command,
        reader=RecordingLookup(),
    )
    replacement = consume_recovery_obligation(
        request=_request(
            store=store, attempt_id=attempt, consumer="overseerd@vps", observed_at=900.0
        ),
        evidence=_evidence(),
        safety=_safety(),
        command=command,
        reader=RecordingLookup(),
    )

    assert first.state == CONSUMER_EXECUTED
    assert first.operation == _RECONCILE
    assert duplicate.state == CONSUMER_CONVERGED
    assert replacement.state == CONSUMER_CONVERGED
    assert (first.effect, duplicate.effect, replacement.effect) == (_EFFECT, _EFFECT, _EFFECT)
    assert command.calls == [f"{attempt}:{_RECONCILE}"]

    payload = _payload(store=store, attempt_id=attempt)
    assert recorded_effect(payload=payload) == _EFFECT
    assert replacement.generation == 2
    assert fence_state(payload=payload, consumer="overseerd@vps", generation=2) == FENCE_CURRENT
    assert fence_state(payload=payload, consumer="overseerd@hp", generation=1) == FENCE_SUPERSEDED
    assert payload["original_deadline"] == _DEADLINE
    # Four: each repeat pass re-acknowledges its receipt and re-reconciles its
    # next action, and both converge on the first observation rather than
    # appending. The count is the evidence that they were SEEN, not dropped.
    assert payload["duplicate_count"] == 4


def test_scenario_163_the_same_action_is_selected_whether_the_local_gate_failed(
    *, tmp_path: Path
) -> None:
    """The control: a green gate over identical evidence selects the same action."""
    failed_attempt = "attempt-scenario163-failed-gate"
    green_attempt = "attempt-scenario163-green-gate"
    failed_store = _notified_store(tmp_path=tmp_path / "failed", attempt_id=failed_attempt)
    green_store = _notified_store(tmp_path=tmp_path / "green", attempt_id=green_attempt)

    failed = consume_recovery_obligation(
        request=_request(
            store=failed_store,
            attempt_id=failed_attempt,
            consumer="overseerd@hp",
            observed_at=310.0,
        ),
        evidence=_evidence(local_gate_outcome="failed"),
        safety=_safety(),
        command=RecordingCommand(effect=_EFFECT),
        reader=RecordingLookup(),
    )
    green = consume_recovery_obligation(
        request=_request(
            store=green_store,
            attempt_id=green_attempt,
            consumer="overseerd@hp",
            observed_at=310.0,
        ),
        evidence=_evidence(local_gate_outcome="succeeded"),
        safety=_safety(),
        command=RecordingCommand(effect=_EFFECT),
        reader=RecordingLookup(),
    )

    assert failed.operation == green.operation == _RECONCILE
    assert failed.state == green.state == CONSUMER_EXECUTED
    assert failed.operation != f"impl:{_ITEM}"
    assert failed.operation != f"diagnose-plan-progress:{_EPIC}"


def test_scenario_163_an_ambiguous_receipt_is_looked_up_and_uncertainty_is_retained(
    *, tmp_path: Path
) -> None:
    attempt = "attempt-scenario163-ambiguous"
    store = _notified_store(tmp_path=tmp_path, attempt_id=attempt)
    crashed = RecordingCommand(effect=None)

    ambiguous = consume_recovery_obligation(
        request=_request(
            store=store, attempt_id=attempt, consumer="overseerd@hp", observed_at=310.0
        ),
        evidence=_evidence(),
        safety=_safety(),
        command=crashed,
        reader=RecordingLookup(),
    )
    assert ambiguous.state == EXECUTION_UNCERTAIN
    assert crashed.calls == [f"{attempt}:{_RECONCILE}"]

    blind_command = RecordingCommand(effect=_EFFECT)
    blind_reader = RecordingLookup()
    still_uncertain = consume_recovery_obligation(
        request=_request(
            store=store, attempt_id=attempt, consumer="overseerd@hp", observed_at=311.0
        ),
        evidence=_evidence(),
        safety=_safety(),
        command=blind_command,
        reader=blind_reader,
    )

    assert still_uncertain.state == EXECUTION_UNCERTAIN
    assert blind_reader.calls == [attempt]
    assert blind_command.calls == []
    assert recorded_effect(payload=_payload(store=store, attempt_id=attempt)) is None

    recovering_command = RecordingCommand(effect=_EFFECT)
    lookup = RecordingLookup(effect=_EFFECT)
    recovered = consume_recovery_obligation(
        request=_request(
            store=store, attempt_id=attempt, consumer="overseerd@hp", observed_at=312.0
        ),
        evidence=_evidence(),
        safety=_safety(),
        command=recovering_command,
        reader=lookup,
    )

    assert recovered.state == CONSUMER_CONVERGED
    assert recovered.effect == _EFFECT
    assert lookup.calls == [attempt]
    assert recovering_command.calls == []
    assert recorded_effect(payload=_payload(store=store, attempt_id=attempt)) == _EFFECT
