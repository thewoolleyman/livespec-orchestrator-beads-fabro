"""Generation-fenced ownership of one canonical recovery attempt.

`contracts.md` section "Launch obligations and consumed recovery" asks for one
specific mechanism: "Recovery MUST use the canonical stable attempt id with
serialized generation-fenced ownership. Duplicate events, concurrent consumers
and restart MUST converge on one observed effect for the supported idempotent
recovery command." It also fixes what happens to the loser: "An expired consumer
lease is claimed by an authorized replacement with a new fencing generation; the
displaced consumer cannot mutate the obligation afterward."

WHY A GENERATION AND NOT JUST A HOLDER NAME. A holder name answers "who holds
it now", which is the wrong question: the dangerous consumer is the one that
held it a moment ago, is still running, and is about to write. It cannot be
asked to notice — a lapsed process has no way to know it lapsed — so the fence
has to be a value it CARRIES and the record can disagree with. `fence_state` is
that disagreement, and it is the only thing between a displaced consumer and a
second command effect.

WHY A LAPSED HOLDER RECLAIMING ALSO GETS A NEW GENERATION. The natural coding
is to renew it — same name, same lease, carry on — and that is the one arm where
a duplicate effect survives: a process whose lease lapsed because it was paused,
not because it died, is still inside its own command when its newer self
reclaims, and under one generation both copies are current. A new generation
fences the lapsed copy of a consumer against itself.

WHY AN UNEXPIRED LEASE REFUSES RATHER THAN QUEUES. Serialization is the whole
guarantee, so the competitor is told `held` and the current holder's name is
reported back to it. There is deliberately no waiting arm here: a consumer that
blocked on another's lease would hold its own observation budget open against a
holder that may never return, and the clause bounds the SCHEDULING of recovery
rather than its queueing.

WHY AN UNREADABLE LEASE REFUSES RATHER THAN LAPSING. The reading itself lives in
`_session_recovery_lease_reading`, which carries that argument; what this module
owes it is the DECISION — a lease it cannot read refuses the claim, rather than
granting a takeover against a holder that may be mid-command.

WHY A REFUSED MUTATION IS COUNTED. `session.recovery.fenced_count` is a
measurement the same section requires, and a fence that discarded the attempt
silently would report a clean zero for a store that displaced a consumer
mid-write — which is precisely the event an operator needs to see.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._session_recovery_lease_reading import (
    StandingLease,
    standing_lease,
)
from livespec_orchestrator_beads_fabro.commands._session_recovery_records import (
    read_recovery_record,
    recovery_record_path,
    write_recovery_record,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_lock import (
    LockBudget,
    run_with_wait_store_lock,
)

__all__: list[str] = [
    "CLAIM_ABSENT",
    "CLAIM_GRANTED",
    "CLAIM_HELD",
    "CLAIM_RENEWED",
    "CLAIM_TAKEN_OVER",
    "CLAIM_UNAVAILABLE",
    "CLAIM_UNOBSERVABLE",
    "FENCE_CURRENT",
    "FENCE_SUPERSEDED",
    "FENCE_UNCLAIMED",
    "RecoveryClaim",
    "claim_recovery",
    "fence_state",
    "record_fenced_mutation",
]

CLAIM_GRANTED = "granted"
CLAIM_RENEWED = "renewed"
CLAIM_TAKEN_OVER = "taken-over"
CLAIM_HELD = "held"
CLAIM_ABSENT = "absent"
CLAIM_UNOBSERVABLE = "unobservable"
CLAIM_UNAVAILABLE = "unavailable"

FENCE_CURRENT = "current"
FENCE_SUPERSEDED = "superseded"
FENCE_UNCLAIMED = "unclaimed"

# The three claim states that admit a consumer to mutate. Kept as one tuple so
# the `granted` property and every caller read the same answer: a second list
# somewhere else is how a state comes to be admitted by one surface and refused
# by another.
_GRANTING_STATES: tuple[str, ...] = (CLAIM_GRANTED, CLAIM_RENEWED, CLAIM_TAKEN_OVER)


@dataclass(frozen=True, kw_only=True)
class RecoveryClaim:
    """One consumer's standing on a canonical recovery attempt.

    `holder` and `generation` are reported even on a REFUSAL, because a refused
    competitor needs to know who holds the attempt and at which generation —
    that is what lets it observe rather than retry blindly.
    """

    state: str
    holder: str | None
    generation: int
    lease_expires_at: float | None

    @property
    def granted(self) -> bool:
        return self.state in _GRANTING_STATES


def fence_state(*, payload: dict[str, object], consumer: str, generation: int) -> str:
    """Whether one consumer at one generation may still mutate this attempt.

    `unclaimed` is kept apart from `superseded` because they are different
    facts: nobody holds the attempt, versus somebody else does. A caller that
    found itself unclaimed must claim before mutating; one that found itself
    superseded must stop.
    """
    recorded = payload["generation"]
    if not isinstance(recorded, int) or recorded == 0:
        return FENCE_UNCLAIMED
    if payload["holder"] == consumer and recorded == generation:
        return FENCE_CURRENT
    return FENCE_SUPERSEDED


def claim_recovery(
    *,
    recovery_store_root: Path,
    attempt_id: str,
    consumer: str,
    now: float,
    lease_seconds: float,
    lock_budget: LockBudget | None = None,
) -> RecoveryClaim:
    """Take, renew or be refused ownership of one attempt, under the store lock."""
    path = recovery_record_path(recovery_store_root=recovery_store_root, attempt_id=attempt_id)
    result = run_with_wait_store_lock(
        wait_store_root=recovery_store_root,
        budget=lock_budget,
        action=lambda: _claim_recovery(
            path=path, consumer=consumer, now=now, lease_seconds=lease_seconds
        ),
    )
    return _UNAVAILABLE_CLAIM if result is None else result


_UNAVAILABLE_CLAIM = RecoveryClaim(
    state=CLAIM_UNAVAILABLE, holder=None, generation=0, lease_expires_at=None
)


def _claim_recovery(
    *, path: Path, consumer: str, now: float, lease_seconds: float
) -> RecoveryClaim:
    loaded = read_recovery_record(path=path)
    if loaded.payload is None:
        return RecoveryClaim(
            state=CLAIM_ABSENT if loaded.diagnostic is None else CLAIM_UNOBSERVABLE,
            holder=None,
            generation=0,
            lease_expires_at=None,
        )
    payload = loaded.payload
    held = standing_lease(payload=payload)
    if held is None:
        return _granted(
            path=path,
            payload=payload,
            consumer=consumer,
            generation=1,
            expires_at=now + lease_seconds,
            state=CLAIM_GRANTED,
        )
    if held.unobservable:
        return RecoveryClaim(
            state=CLAIM_UNOBSERVABLE, holder=None, generation=0, lease_expires_at=None
        )
    return _claim_against_lease(
        path=path,
        payload=payload,
        held=held,
        consumer=consumer,
        now=now,
        lease_seconds=lease_seconds,
    )


def _claim_against_lease(
    *,
    path: Path,
    payload: dict[str, object],
    held: StandingLease,
    consumer: str,
    now: float,
    lease_seconds: float,
) -> RecoveryClaim:
    """Decide one claim against a readable standing lease."""
    if held.expires_at > now:
        if held.holder != consumer:
            return RecoveryClaim(
                state=CLAIM_HELD,
                holder=held.holder,
                generation=held.generation,
                lease_expires_at=held.expires_at,
            )
        return _granted(
            path=path,
            payload=payload,
            consumer=consumer,
            generation=held.generation,
            expires_at=now + lease_seconds,
            state=CLAIM_RENEWED,
        )
    return _granted(
        path=path,
        payload=payload,
        consumer=consumer,
        generation=held.generation + 1,
        expires_at=now + lease_seconds,
        state=CLAIM_TAKEN_OVER,
    )


def _granted(
    *,
    path: Path,
    payload: dict[str, object],
    consumer: str,
    generation: int,
    expires_at: float,
    state: str,
) -> RecoveryClaim:
    """Write one granted lease onto the record, mutating only its three fields.

    Only `holder`, `generation` and `lease_expires_at` move. Rebuilding the
    payload would rewrite the epoch, the deadline and the transitions a previous
    consumer wrote — the evidence this consumer is about to read.
    """
    payload["holder"] = consumer
    payload["generation"] = generation
    payload["lease_expires_at"] = expires_at
    write_recovery_record(path=path, payload=payload)
    return RecoveryClaim(
        state=state, holder=consumer, generation=generation, lease_expires_at=expires_at
    )


def record_fenced_mutation(
    *,
    recovery_store_root: Path,
    attempt_id: str,
    lock_budget: LockBudget | None = None,
) -> int | None:
    """Count one refused mutation, and report the running total.

    `None` is every reason the count could not be written — an absent attempt,
    an unreadable record, a store lock this caller's budget could not take —
    because a caller's remedy is the same in all three and is never to proceed
    with the mutation that was refused.
    """
    path = recovery_record_path(recovery_store_root=recovery_store_root, attempt_id=attempt_id)
    return run_with_wait_store_lock(
        wait_store_root=recovery_store_root,
        budget=lock_budget,
        action=lambda: _record_fenced_mutation(path=path),
    )


def _record_fenced_mutation(*, path: Path) -> int | None:
    loaded = read_recovery_record(path=path)
    if loaded.payload is None:
        return None
    payload = loaded.payload
    counted = cast("int", payload["fenced_count"]) + 1
    payload["fenced_count"] = counted
    write_recovery_record(path=path, payload=payload)
    return counted
