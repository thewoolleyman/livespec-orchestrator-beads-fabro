"""The durable recovery attempt, and the distinct transitions a consumer writes onto it.

`contracts.md` section "Launch obligations and consumed recovery" enumerates the
transitions and then says what they are for: "Notification production, receipt
acknowledgement, consumer claim, execution start, execution evidence, resulting
next-action reconciliation and target-effect fulfillment MUST be separate
durable observations. Receipt or claim alone MUST NOT mark recovery consumed."
This module is the record those observations land on, and nothing else — the
consumption grade is `_session_recovery_consumption`, the fencing is
`_session_recovery_lease`, the action choice is `_session_recovery_action`.

WHY SEVEN NAMED TRANSITIONS AND NOT A FREE-FORM LOG. A consumer that could
append any string would make "was this recovery consumed?" a question about
vocabulary rather than about evidence, and the grade would then have to guess
which words meant execution. The set is CLOSED for the same reason the relay's
operation grammar is: a typo and an invented token arrive looking identical, and
an invented one must not be able to discharge anything.

WHY NO WRITE HERE CAN CARRY TWO TRANSITIONS. The attempt is opened carrying only
its identities, and every transition is its own call. A single write that could
carry execution evidence alongside the claim would make "receipt or claim alone
MUST NOT mark recovery consumed" a property of each caller's care rather than of
the record's shape.

WHY A DUPLICATE CONVERGES INSTEAD OF APPENDING. The same section requires that
"Duplicate events, concurrent consumers and restart MUST converge on one
observed effect", so a transition already observed is NOT appended a second
time: the first observation — with its instant — is the one a later reader may
already have acted on. The duplicate is COUNTED rather than discarded, because
`session.recovery.duplicate_count` is a measurement the clause asks for, and a
silently dropped event would report a clean zero for a store that saw two.

WHY THE RESULT IDENTITY, EPOCH AND DEADLINE ARRIVE AS GIVEN. They are the relay
contract's, and the same section forbids a second one: "This contract MUST NOT
define a second result enum, independently reset an obligation deadline or
equate wait completion with result fulfillment." Nothing here computes,
defaults or refreshes any of the three, so "a declared changed approach does not
reset the original result deadline" holds because there is no code that could.

WHY AN UNREADABLE RECORD ANSWERS DIFFERENTLY FROM AN ABSENT ONE. The same
section's "Missing/unreadable authority MUST be unobservable, not no
obligations": an append onto a record nobody can parse answers `unobservable`,
which is distinct from `absent` — no attempt was ever opened under that id — and
the two have opposite remedies.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from uuid import uuid4

from livespec_orchestrator_beads_fabro.commands._session_recovery_shape import (
    DIAGNOSTIC_INVALID_RECORD,
    DIAGNOSTIC_UNREADABLE_RECORD,
    RECOVERY_SCHEMA_VERSION,
    RecoveryRead,
    graded_recovery_payload,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_lock import (
    LockBudget,
    run_with_wait_store_lock,
)

__all__: list[str] = [
    "APPEND_ABSENT",
    "APPEND_DUPLICATE",
    "APPEND_RECORDED",
    "APPEND_UNAVAILABLE",
    "APPEND_UNKNOWN_TRANSITION",
    "APPEND_UNOBSERVABLE",
    "OPEN_ALREADY_OPEN",
    "OPEN_OPENED",
    "OPEN_UNAVAILABLE",
    "RECOVERY_TRANSITIONS",
    "TRANSITION_CLAIMED",
    "TRANSITION_DEFERRED",
    "TRANSITION_EXECUTED",
    "TRANSITION_NOTIFICATION",
    "TRANSITION_RECEIPT",
    "TRANSITION_RECONCILED",
    "TRANSITION_STARTED",
    "RecoveryAttempt",
    "append_recovery_transition",
    "observed_transitions",
    "open_recovery_attempt",
    "read_recovery_record",
    "recovery_record_path",
    "write_recovery_record",
]

TRANSITION_NOTIFICATION = "notification"
TRANSITION_RECEIPT = "receipt"
TRANSITION_CLAIMED = "claimed"
TRANSITION_STARTED = "started"
TRANSITION_EXECUTED = "executed"
TRANSITION_DEFERRED = "deferred"
TRANSITION_RECONCILED = "reconciled"

# CLOSED, in the order the clause discusses them. `deferred` sits between
# execution and reconciliation because a safety barrier is observed in place of
# an execution rather than after one.
RECOVERY_TRANSITIONS: tuple[str, ...] = (
    TRANSITION_NOTIFICATION,
    TRANSITION_RECEIPT,
    TRANSITION_CLAIMED,
    TRANSITION_STARTED,
    TRANSITION_EXECUTED,
    TRANSITION_DEFERRED,
    TRANSITION_RECONCILED,
)

OPEN_OPENED = "opened"
OPEN_ALREADY_OPEN = "already-open"
OPEN_UNAVAILABLE = "unavailable"

APPEND_RECORDED = "recorded"
APPEND_DUPLICATE = "duplicate"
APPEND_UNKNOWN_TRANSITION = "unknown-transition"
APPEND_ABSENT = "absent"
APPEND_UNOBSERVABLE = "unobservable"
APPEND_UNAVAILABLE = "unavailable"


@dataclass(frozen=True, kw_only=True)
class RecoveryAttempt:
    """One canonical recovery attempt, under the identities the relay owns.

    `attempt_id` is the relay's stable attempt identity rather than one minted
    here, because the clause reconciles duplicates and takeovers by it: an id
    minted per consumer would make every replacement a fresh attempt and
    duplicate the very command effect the identity exists to converge.
    """

    attempt_id: str
    operation_id: str
    required_result_identity: str
    result_epoch: int
    original_deadline: str


def recovery_record_path(*, recovery_store_root: Path, attempt_id: str) -> Path:
    return recovery_store_root / f"{attempt_id}.json"


def write_recovery_record(*, path: Path, payload: dict[str, object]) -> None:
    """Replace one record atomically, so no reader sees a half-written attempt."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid4().hex}.tmp"
    _ = temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _ = temporary.replace(path)


def read_recovery_record(*, path: Path) -> RecoveryRead:
    """Read one attempt, reporting every unusable shape as a diagnostic.

    This NEVER raises. A record nobody can parse is unobservable rather than
    absent, and a reader that raised would take down the very pass that exists
    to surface it.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return RecoveryRead(payload=None, diagnostic=None)
    except OSError:
        return RecoveryRead(payload=None, diagnostic=DIAGNOSTIC_UNREADABLE_RECORD)
    return _parsed_record(raw=raw)


def _parsed_record(*, raw: str) -> RecoveryRead:
    """Decode the bytes of a record that was read, and hand them to the grade."""
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return RecoveryRead(payload=None, diagnostic=DIAGNOSTIC_INVALID_RECORD)
    return graded_recovery_payload(loaded=loaded)


def observed_transitions(*, payload: dict[str, object]) -> tuple[str, ...]:
    """The transition kinds this record observed, in the order they were written.

    An entry that is not a mapping naming a known transition is skipped rather
    than reported, because the question here is which observations EXIST: an
    entry nothing can read is not an observation of anything.
    """
    entries = cast("list[object]", payload["transitions"])
    named = (
        cast("dict[str, object]", entry).get("transition")
        for entry in entries
        if isinstance(entry, dict)
    )
    return tuple(one for one in named if isinstance(one, str) and one in RECOVERY_TRANSITIONS)


def open_recovery_attempt(
    *,
    recovery_store_root: Path,
    attempt: RecoveryAttempt,
    opened_at: float,
    lock_budget: LockBudget | None = None,
) -> str:
    """Open one attempt's record, or report that its identity already stands.

    An EXISTING record is `already-open` and is left exactly as it is.
    Overwriting it would discard the transitions a previous consumer wrote,
    which is the evidence a replacement consumer reads in order not to execute
    the same command twice.
    """
    path = recovery_record_path(
        recovery_store_root=recovery_store_root, attempt_id=attempt.attempt_id
    )
    result = run_with_wait_store_lock(
        wait_store_root=recovery_store_root,
        budget=lock_budget,
        action=lambda: _open_recovery_attempt(path=path, attempt=attempt, opened_at=opened_at),
    )
    return OPEN_UNAVAILABLE if result is None else result


def _open_recovery_attempt(*, path: Path, attempt: RecoveryAttempt, opened_at: float) -> str:
    if path.exists():
        return OPEN_ALREADY_OPEN
    write_recovery_record(
        path=path,
        payload={
            "attempt_id": attempt.attempt_id,
            "duplicate_count": 0,
            "effect": None,
            "fenced_count": 0,
            "generation": 0,
            "holder": None,
            "lease_expires_at": None,
            "opened_at": opened_at,
            "operation_id": attempt.operation_id,
            "original_deadline": attempt.original_deadline,
            "required_result_identity": attempt.required_result_identity,
            "result_epoch": attempt.result_epoch,
            "schema_version": RECOVERY_SCHEMA_VERSION,
            "transitions": [],
        },
    )
    return OPEN_OPENED


def append_recovery_transition(
    *,
    recovery_store_root: Path,
    attempt_id: str,
    transition: str,
    observed_at: float,
    detail: dict[str, object] | None = None,
    lock_budget: LockBudget | None = None,
) -> str:
    """Record one transition onto an open attempt, once.

    The unknown-transition refusal happens BEFORE the store is touched, so a
    caller naming a word outside the closed set cannot take the lock, cannot
    count a duplicate and leaves no trace of an observation that has no meaning.
    """
    if transition not in RECOVERY_TRANSITIONS:
        return APPEND_UNKNOWN_TRANSITION
    path = recovery_record_path(recovery_store_root=recovery_store_root, attempt_id=attempt_id)
    result = run_with_wait_store_lock(
        wait_store_root=recovery_store_root,
        budget=lock_budget,
        action=lambda: _append_recovery_transition(
            path=path, transition=transition, observed_at=observed_at, detail=detail
        ),
    )
    return APPEND_UNAVAILABLE if result is None else result


def _append_recovery_transition(
    *, path: Path, transition: str, observed_at: float, detail: dict[str, object] | None
) -> str:
    loaded = read_recovery_record(path=path)
    if loaded.payload is None:
        return APPEND_ABSENT if loaded.diagnostic is None else APPEND_UNOBSERVABLE
    payload = loaded.payload
    if transition in observed_transitions(payload=payload):
        payload["duplicate_count"] = cast("int", payload["duplicate_count"]) + 1
        write_recovery_record(path=path, payload=payload)
        return APPEND_DUPLICATE
    entries = cast("list[object]", payload["transitions"])
    entries.append({"detail": detail, "observed_at": observed_at, "transition": transition})
    write_recovery_record(path=path, payload=payload)
    return APPEND_RECORDED
