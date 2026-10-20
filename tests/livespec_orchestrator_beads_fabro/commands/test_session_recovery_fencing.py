"""Competing recovery generations: one holder at a time, and a fenced replacement.

Scenario 163 of `SPECIFICATION/scenarios.md` requires "serialized
generation-fenced ownership" over one canonical attempt, and `contracts.md`
section "Launch obligations and consumed recovery" adds the consequence: "a
stale consumer is fenced by generation."
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._session_recovery_lease import (
    CLAIM_ABSENT,
    CLAIM_GRANTED,
    CLAIM_HELD,
    CLAIM_RENEWED,
    CLAIM_TAKEN_OVER,
    CLAIM_UNAVAILABLE,
    CLAIM_UNOBSERVABLE,
    FENCE_CURRENT,
    FENCE_SUPERSEDED,
    FENCE_UNCLAIMED,
    RecoveryClaim,
    claim_recovery,
    fence_state,
    record_fenced_mutation,
)
from livespec_orchestrator_beads_fabro.commands._session_recovery_records import (
    RecoveryAttempt,
    open_recovery_attempt,
    read_recovery_record,
    recovery_record_path,
    write_recovery_record,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_lock import (
    LockBudget,
    wait_store_lock,
)

_ATTEMPT_ID = "attempt-dle6l3-fencing"
_LEASE_SECONDS = 30.0


def _opened_store(*, tmp_path: Path) -> Path:
    store = tmp_path / "recovery"
    _ = open_recovery_attempt(
        recovery_store_root=store,
        attempt=RecoveryAttempt(
            attempt_id=_ATTEMPT_ID,
            operation_id="op-dle6l3-fencing",
            required_result_identity="pull_request_state #2700 state MERGED",
            result_epoch=5,
            original_deadline="2026-10-20T21:00:00Z",
        ),
        opened_at=0.0,
    )
    return store


def _payload(*, store: Path) -> dict[str, object]:
    read = read_recovery_record(
        path=recovery_record_path(recovery_store_root=store, attempt_id=_ATTEMPT_ID)
    )
    assert read.payload is not None
    return read.payload


def _expired_budget() -> LockBudget:
    return LockBudget(deadline=0.0, monotonic=lambda: 1.0, sleeper=lambda **_: None)


def _claim(*, store: Path, consumer: str, now: float) -> RecoveryClaim:
    return claim_recovery(
        recovery_store_root=store,
        attempt_id=_ATTEMPT_ID,
        consumer=consumer,
        now=now,
        lease_seconds=_LEASE_SECONDS,
    )


def test_one_unexpired_lease_admits_its_holder_and_refuses_every_other_consumer(
    *, tmp_path: Path
) -> None:
    store = _opened_store(tmp_path=tmp_path)

    first = claim_recovery(
        recovery_store_root=store,
        attempt_id=_ATTEMPT_ID,
        consumer="overseerd@hp",
        now=10.0,
        lease_seconds=_LEASE_SECONDS,
    )
    assert first.state == CLAIM_GRANTED
    assert first.granted
    assert first.generation == 1
    assert first.holder == "overseerd@hp"
    assert first.lease_expires_at == 40.0

    competitor = claim_recovery(
        recovery_store_root=store,
        attempt_id=_ATTEMPT_ID,
        consumer="overseerd@vps",
        now=11.0,
        lease_seconds=_LEASE_SECONDS,
    )
    assert competitor.state == CLAIM_HELD
    assert not competitor.granted
    assert competitor.holder == "overseerd@hp"
    assert competitor.generation == 1

    renewed = claim_recovery(
        recovery_store_root=store,
        attempt_id=_ATTEMPT_ID,
        consumer="overseerd@hp",
        now=12.0,
        lease_seconds=_LEASE_SECONDS,
    )
    assert renewed.state == CLAIM_RENEWED
    assert renewed.granted
    assert renewed.generation == 1
    assert renewed.lease_expires_at == 42.0


def test_an_expired_lease_is_taken_over_at_a_new_generation_that_fences_the_old_one(
    *, tmp_path: Path
) -> None:
    store = _opened_store(tmp_path=tmp_path)
    first = claim_recovery(
        recovery_store_root=store,
        attempt_id=_ATTEMPT_ID,
        consumer="overseerd@hp",
        now=10.0,
        lease_seconds=_LEASE_SECONDS,
    )

    replacement = claim_recovery(
        recovery_store_root=store,
        attempt_id=_ATTEMPT_ID,
        consumer="overseerd@vps",
        now=100.0,
        lease_seconds=_LEASE_SECONDS,
    )

    assert replacement.state == CLAIM_TAKEN_OVER
    assert replacement.granted
    assert replacement.generation == first.generation + 1
    assert replacement.holder == "overseerd@vps"

    payload = _payload(store=store)
    assert fence_state(payload=payload, consumer="overseerd@vps", generation=2) == FENCE_CURRENT
    assert fence_state(payload=payload, consumer="overseerd@hp", generation=1) == FENCE_SUPERSEDED


def test_a_lapsed_holder_reclaiming_is_itself_given_a_new_generation(*, tmp_path: Path) -> None:
    """A process that let its lease lapse may still be running its own old copy."""
    store = _opened_store(tmp_path=tmp_path)
    _ = _claim(store=store, consumer="overseerd@hp", now=10.0)

    again = claim_recovery(
        recovery_store_root=store,
        attempt_id=_ATTEMPT_ID,
        consumer="overseerd@hp",
        now=500.0,
        lease_seconds=_LEASE_SECONDS,
    )

    assert again.state == CLAIM_TAKEN_OVER
    assert again.generation == 2
    payload = _payload(store=store)
    assert fence_state(payload=payload, consumer="overseerd@hp", generation=1) == FENCE_SUPERSEDED
    assert fence_state(payload=payload, consumer="overseerd@hp", generation=2) == FENCE_CURRENT


def test_an_unclaimed_attempt_fences_every_generation(*, tmp_path: Path) -> None:
    store = _opened_store(tmp_path=tmp_path)

    assert (
        fence_state(payload=_payload(store=store), consumer="overseerd@hp", generation=1)
        == FENCE_UNCLAIMED
    )


def test_a_fenced_mutation_is_counted_rather_than_silently_dropped(*, tmp_path: Path) -> None:
    store = _opened_store(tmp_path=tmp_path)
    _ = _claim(store=store, consumer="overseerd@hp", now=10.0)

    assert record_fenced_mutation(recovery_store_root=store, attempt_id=_ATTEMPT_ID) == 1
    assert record_fenced_mutation(recovery_store_root=store, attempt_id=_ATTEMPT_ID) == 2
    assert _payload(store=store)["fenced_count"] == 2
    assert record_fenced_mutation(recovery_store_root=store, attempt_id="attempt-absent") is None


def test_an_absent_attempt_and_an_unreadable_lease_refuse_rather_than_grant(
    *, tmp_path: Path
) -> None:
    store = _opened_store(tmp_path=tmp_path)

    assert (
        claim_recovery(
            recovery_store_root=store,
            attempt_id="attempt-never-opened",
            consumer="overseerd@hp",
            now=1.0,
            lease_seconds=_LEASE_SECONDS,
        ).state
        == CLAIM_ABSENT
    )

    path = recovery_record_path(recovery_store_root=store, attempt_id=_ATTEMPT_ID)
    payload = _payload(store=store)
    payload["holder"] = "overseerd@hp"
    payload["generation"] = 1
    payload["lease_expires_at"] = "soon"
    write_recovery_record(path=path, payload=payload)

    assert (
        claim_recovery(
            recovery_store_root=store,
            attempt_id=_ATTEMPT_ID,
            consumer="overseerd@vps",
            now=2.0,
            lease_seconds=_LEASE_SECONDS,
        ).state
        == CLAIM_UNOBSERVABLE
    )
    assert _payload(store=store)["holder"] == "overseerd@hp"


def test_a_contended_store_refuses_the_claim_rather_than_granting_it(*, tmp_path: Path) -> None:
    store = _opened_store(tmp_path=tmp_path)

    with wait_store_lock(wait_store_root=store) as acquired:
        assert acquired
        refused = claim_recovery(
            recovery_store_root=store,
            attempt_id=_ATTEMPT_ID,
            consumer="overseerd@hp",
            now=1.0,
            lease_seconds=_LEASE_SECONDS,
            lock_budget=_expired_budget(),
        )
        fenced = record_fenced_mutation(
            recovery_store_root=store,
            attempt_id=_ATTEMPT_ID,
            lock_budget=_expired_budget(),
        )

    assert refused.state == CLAIM_UNAVAILABLE
    assert not refused.granted
    assert refused.generation == 0
    assert fenced is None
    assert _payload(store=store)["holder"] is None
