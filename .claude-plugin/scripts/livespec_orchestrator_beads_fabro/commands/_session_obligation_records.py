"""The durable launch obligation a dispatch or delegation records before its effect.

`contracts.md` section "Launch obligations and consumed recovery" puts the
registration BEFORE the external effect: "Dispatch/delegation MUST persist
intent, session/repository/authorization scope, canonical result/epoch/original
deadline and independently verifiable wake/consumer coverage BEFORE reporting a
protected launch. It MUST attach the actual gate/run/delegation identity." This
module is the durable record those two transitions write, and nothing else —
the coverage grade lives in `_session_obligation_coverage`, the ordering in
`_session_obligation_launch`, and the crash repair in
`_session_obligation_reconcile`.

WHY THE RECORD CARRIES A RESULT *IDENTITY* AND NOT A RESULT. The canonical
required result, its reader, its epoch and its original deadline belong to the
relay contract, and the same section forbids a second one: "This contract MUST
NOT define a second result enum, independently reset an obligation deadline or
equate wait completion with result fulfillment." So the record stores the
rendered `ResultReference.identity` the relay already owns plus the epoch and
the original deadline AS GIVEN, and no code here ever computes a deadline. A
record that held a parsed target would be a second result model with a second
grammar to drift from.

WHY INTENT AND ATTACHMENT ARE TWO WRITES. A crash can land between them — that
is the whole condition the reconciliation exists for — so the record has to be
legible in the half state. One combined write would make the half state
UNREPRESENTABLE, which sounds safer and is not: the external effect still
happened, and the only record of it would be gone.

WHY ATTACHMENT MUTATES EXACTLY TWO FIELDS. `attach_launch_target` re-reads the
record and writes `target` and `attached_at` over it. The alternative — rebuild
the payload from the caller's inputs — passes every test whose fixture happens
to supply the original values, and silently rewrites the epoch, the deadline or
the authority of a record whose caller has moved on. Preserving them becomes a
property of the write rather than a rule each caller remembers.

WHY AN UNREADABLE STORE IS A DIAGNOSTIC AND NEVER AN EMPTY SET. The same
section: "Missing/unreadable authority MUST be unobservable, not no
obligations." `outstanding_obligations` therefore reports the store it could not
list as a diagnostic beside whatever it did read, because an empty tuple is
indistinguishable at every surface from a host with no outstanding work — and
the two support opposite conclusions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from uuid import uuid4

from livespec_orchestrator_beads_fabro.commands._session_wait_lock import (
    LockBudget,
    run_with_wait_store_lock,
)

__all__: list[str] = [
    "ATTACH_ABSENT",
    "ATTACH_ALREADY_ATTACHED",
    "ATTACH_ATTACHED",
    "ATTACH_UNAVAILABLE",
    "DIAGNOSTIC_INVALID_RECORD",
    "DIAGNOSTIC_UNREADABLE_RECORD",
    "DIAGNOSTIC_UNREADABLE_STORE",
    "DIAGNOSTIC_UNSUPPORTED_SCHEMA",
    "INTENT_ALREADY_RECORDED",
    "INTENT_RECORDED",
    "INTENT_UNAVAILABLE",
    "OBLIGATION_SCHEMA_VERSION",
    "LaunchAuthority",
    "LaunchIntent",
    "LaunchTarget",
    "ObligationCensus",
    "ObligationRead",
    "attach_launch_target",
    "obligation_record_path",
    "outstanding_obligations",
    "read_obligation_record",
    "record_launch_intent",
    "write_obligation_record",
]

OBLIGATION_SCHEMA_VERSION = 1

DIAGNOSTIC_UNREADABLE_RECORD = "unreadable-record"
DIAGNOSTIC_INVALID_RECORD = "invalid-record"
DIAGNOSTIC_UNSUPPORTED_SCHEMA = "unsupported-schema"
DIAGNOSTIC_UNREADABLE_STORE = "unreadable-store"

INTENT_RECORDED = "recorded"
INTENT_ALREADY_RECORDED = "already-recorded"
INTENT_UNAVAILABLE = "unavailable"

ATTACH_ATTACHED = "attached"
ATTACH_ALREADY_ATTACHED = "already-attached"
ATTACH_ABSENT = "absent"
ATTACH_UNAVAILABLE = "unavailable"

# Every field a version-1 record carries. A record missing or mistyping any of
# them is INVALID rather than partially usable, for the reason the sibling wait
# store gives: a consumer that defaulted one in would be inventing the deadline,
# the epoch or the owner it never read.
_REQUIRED_FIELDS = frozenset(
    {
        "attached_at",
        "authority",
        "coverage",
        "intent_recorded_at",
        "operation_id",
        "original_deadline",
        "required_result_identity",
        "result_epoch",
        "target",
    }
)


@dataclass(frozen=True, kw_only=True)
class LaunchAuthority:
    """The session, repository and authorization scope one launch is bound to.

    All four are supplied by the caller rather than resolved here, because the
    two callers resolve them differently — a dispatch knows its invoker and the
    item's plan, a delegation knows the coordinator pane's session — and a
    resolver here would have to guess which one it was serving.
    """

    session_id: str
    repository: Path
    invoker: str
    scope: str

    def record_payload(self) -> dict[str, object]:
        return {
            "invoker": self.invoker,
            "repository": str(self.repository),
            "scope": self.scope,
            "session_id": self.session_id,
        }


@dataclass(frozen=True, kw_only=True)
class LaunchIntent:
    """One launch about to happen, under the stable identity that survives a crash.

    `operation_id` is the STABLE operation identity the contract reconciles by,
    so it must be derived from the work rather than from the attempt: a fresh id
    per attempt would make every post-crash resumption look like a new launch
    and duplicate the external effect.
    """

    operation_id: str
    authority: LaunchAuthority
    required_result_identity: str
    result_epoch: int
    original_deadline: str


@dataclass(frozen=True, kw_only=True)
class LaunchTarget:
    """The real gate, run or delegation identity a launch is attached to."""

    kind: str
    identity: str

    def record_payload(self) -> dict[str, object]:
        return {"identity": self.identity, "kind": self.kind}


@dataclass(frozen=True, kw_only=True)
class ObligationRead:
    payload: dict[str, object] | None
    diagnostic: str | None


@dataclass(frozen=True, kw_only=True)
class ObligationCensus:
    """Obligations read, plus the diagnostic of anything that could not be."""

    records: tuple[dict[str, object], ...]
    diagnostics: tuple[str, ...]


def obligation_record_path(*, obligation_store_root: Path, operation_id: str) -> Path:
    return obligation_store_root / f"{operation_id}.json"


def write_obligation_record(*, path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid4().hex}.tmp"
    _ = temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _ = temporary.replace(path)


def read_obligation_record(*, path: Path) -> ObligationRead:
    """Read one obligation, reporting every unusable shape as a diagnostic.

    This NEVER raises, and the reason is the one the contract states for
    authority: a record nobody can parse is UNOBSERVABLE, not an absence of
    work. A reader that raised would take down the census that exists to
    surface it; one that returned an empty payload would report a clean,
    plausible, wrong answer.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ObligationRead(payload=None, diagnostic=None)
    except OSError:
        return ObligationRead(payload=None, diagnostic=DIAGNOSTIC_UNREADABLE_RECORD)
    return _parsed_record(raw=raw)


def _parsed_record(*, raw: str) -> ObligationRead:
    """Grade the bytes of a record that was read, apart from reading it.

    Split from the read for the reason the formatter cares about and the reader
    benefits from either way: the two halves answer different questions — could
    the file be read at all, and does what it holds mean anything — and only the
    first of them can report an absence.
    """
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return ObligationRead(payload=None, diagnostic=DIAGNOSTIC_INVALID_RECORD)
    if not isinstance(loaded, dict):
        return ObligationRead(payload=None, diagnostic=DIAGNOSTIC_INVALID_RECORD)
    payload = cast("dict[str, object]", loaded)
    if payload.get("schema_version") != OBLIGATION_SCHEMA_VERSION:
        return ObligationRead(payload=None, diagnostic=DIAGNOSTIC_UNSUPPORTED_SCHEMA)
    if not _well_formed(payload=payload):
        return ObligationRead(payload=None, diagnostic=DIAGNOSTIC_INVALID_RECORD)
    return ObligationRead(payload=payload, diagnostic=None)


def _well_formed(*, payload: dict[str, object]) -> bool:
    """Whether a version-1 record carries every field at an indexable type."""
    return all(
        (
            payload.keys() >= _REQUIRED_FIELDS,
            isinstance(payload.get("authority"), dict),
            isinstance(payload.get("coverage"), dict),
            isinstance(payload.get("operation_id"), str),
            isinstance(payload.get("original_deadline"), str),
            isinstance(payload.get("required_result_identity"), str),
            isinstance(payload.get("result_epoch"), int),
            not isinstance(payload.get("result_epoch"), bool),
        )
    )


def record_launch_intent(
    *,
    intent: LaunchIntent,
    coverage: dict[str, object],
    obligation_store_root: Path,
    recorded_at: float,
    lock_budget: LockBudget | None = None,
) -> str:
    """Record one launch intent, or report that its identity already stands.

    An EXISTING record for the same operation id is `already-recorded` and is
    left exactly as it is. Overwriting it would reset the intent instant of a
    launch that may already have produced its effect, which is the one piece of
    evidence the reconciliation uses to decide that an effect may exist at all.
    """
    path = obligation_record_path(
        obligation_store_root=obligation_store_root, operation_id=intent.operation_id
    )
    result = run_with_wait_store_lock(
        wait_store_root=obligation_store_root,
        budget=lock_budget,
        action=lambda: _record_launch_intent(
            path=path,
            intent=intent,
            coverage=coverage,
            recorded_at=recorded_at,
        ),
    )
    return INTENT_UNAVAILABLE if result is None else result


def _record_launch_intent(
    *,
    path: Path,
    intent: LaunchIntent,
    coverage: dict[str, object],
    recorded_at: float,
) -> str:
    if path.exists():
        return INTENT_ALREADY_RECORDED
    payload: dict[str, object] = {
        "attached_at": None,
        "authority": intent.authority.record_payload(),
        "coverage": coverage,
        "intent_recorded_at": recorded_at,
        "operation_id": intent.operation_id,
        "original_deadline": intent.original_deadline,
        "required_result_identity": intent.required_result_identity,
        "result_epoch": intent.result_epoch,
        "schema_version": OBLIGATION_SCHEMA_VERSION,
        "target": None,
    }
    write_obligation_record(path=path, payload=payload)
    return INTENT_RECORDED


def attach_launch_target(
    *,
    obligation_store_root: Path,
    operation_id: str,
    target: LaunchTarget,
    attached_at: float,
    lock_budget: LockBudget | None = None,
) -> str:
    """Attach the real target identity to an obligation already recorded.

    An obligation that ALREADY names a target is `already-attached` and is not
    rewritten, even when the incoming identity differs. Two identities for one
    operation id means the effect was observed twice, and the first reading is
    the one the consumer may already have acted on.
    """
    path = obligation_record_path(
        obligation_store_root=obligation_store_root, operation_id=operation_id
    )
    result = run_with_wait_store_lock(
        wait_store_root=obligation_store_root,
        budget=lock_budget,
        action=lambda: _attach_launch_target(
            path=path,
            target=target,
            attached_at=attached_at,
        ),
    )
    return ATTACH_UNAVAILABLE if result is None else result


def _attach_launch_target(*, path: Path, target: LaunchTarget, attached_at: float) -> str:
    loaded = read_obligation_record(path=path)
    if loaded.payload is None:
        return ATTACH_ABSENT
    payload = loaded.payload
    if payload["target"] is not None:
        return ATTACH_ALREADY_ATTACHED
    payload["target"] = target.record_payload()
    payload["attached_at"] = attached_at
    write_obligation_record(path=path, payload=payload)
    return ATTACH_ATTACHED


def outstanding_obligations(*, obligation_store_root: Path) -> ObligationCensus:
    """Every obligation in the store that no target result has discharged yet.

    Discovery is INDEPENDENT of the session-wait store, which is what makes an
    obligation survive a coordinator that never armed a wait: this walk reads
    the launch records themselves, so "no wait row" cannot read as "no
    outstanding work". A store that cannot be listed is reported as a
    diagnostic, never as an empty census.
    """
    try:
        entries = sorted(obligation_store_root.glob("*.json"))
    except OSError:
        return ObligationCensus(records=(), diagnostics=(DIAGNOSTIC_UNREADABLE_STORE,))
    records: list[dict[str, object]] = []
    diagnostics: list[str] = []
    for entry in entries:
        read = read_obligation_record(path=entry)
        if read.payload is None:
            # An entry the listing named and the read could not resolve is
            # UNREADABLE even when the read reports no diagnostic of its own:
            # that happens when the file is removed between the two, and
            # "listed, then gone" is an observation rather than an absence.
            diagnostics.append(read.diagnostic or DIAGNOSTIC_UNREADABLE_RECORD)
        else:
            records.append(read.payload)
    return ObligationCensus(records=tuple(records), diagnostics=tuple(diagnostics))
