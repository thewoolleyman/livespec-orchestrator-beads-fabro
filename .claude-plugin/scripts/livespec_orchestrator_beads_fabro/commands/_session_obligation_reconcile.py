"""Reconciling a crash that landed between launch intent and target attachment.

`contracts.md` section "Launch obligations and consumed recovery" asks for one
specific repair: "reconcile crashes between intent and attachment by stable
operation id without duplicating the external effect", and the matching scenario
adds what the repair must leave alone — it "preserves the original deadline,
epoch and authority without killing the target".

WHY THE OPERATION IDENTITY IS THE WHOLE MECHANISM. The crash window is bounded
by two writes, and on the far side of it an external effect may or may not
exist. The only thing that survives the crash is the id the intent was recorded
under, so reconciliation re-asks the effect's own store what that id produced
rather than inferring anything from the record it crashed writing. An identity
derived per ATTEMPT would make each resumption a new launch and duplicate the
effect, which is why `LaunchIntent` carries a stable one.

WHY NOTHING HERE CAN KILL A TARGET. `LaunchedEffectReader` has exactly one verb
and it reads. The guarantee is therefore structural rather than careful: there
is no kill to reach for, so no edit to this module's control flow can reintroduce
one without also widening that protocol — which is the change a reviewer would
see. The research note's wording is "Never auto-kill a live target to repair
tracking", and a repair pass that could kill is a repair pass that eventually
does, on the arm where its reading disagreed with the record.

WHY AN ALREADY-ATTACHED OBLIGATION DOES NOT ASK THE READER AT ALL. Idempotence
here is not "write the same value twice safely" but "spend no further
observation": the attachment already names the effect, so a second reading could
only either agree — costing a round trip for nothing — or disagree, and a
disagreement is an incident for the consumer to surface rather than a value for
this pass to overwrite.

WHY AN UNOBSERVABLE EFFECT WRITES NOTHING. The same section requires a consumer
that cannot decide to "retain unobservable state if it cannot decide", and the
natural coding of "I could not see an effect" is "there is no effect" — which
would discharge an obligation whose target is alive. So the record is left in its
half state, which is exactly the state that brings the next pass back here.

WHY A MISSING RECORD IS `no-intent` RATHER THAN UNOBSERVABLE. The two are
different facts with different remedies, and the ordering guarantee is what
tells them apart: intent is persisted BEFORE the effect, so no record for an id
means no launch was ever reported under it. An UNREADABLE record is the other
case, and it answers unobservable per the same section's "Missing/unreadable
authority MUST be unobservable, not no obligations".
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from livespec_orchestrator_beads_fabro.commands._session_obligation_records import (
    ATTACH_ATTACHED,
    LaunchTarget,
    attach_launch_target,
    obligation_record_path,
    read_obligation_record,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_lock import LockBudget

__all__: list[str] = [
    "RECONCILE_ALREADY_ATTACHED",
    "RECONCILE_ATTACHED",
    "RECONCILE_ATTACHMENT_UNAVAILABLE",
    "RECONCILE_EFFECT_UNOBSERVABLE",
    "RECONCILE_NO_INTENT",
    "RECONCILE_OBLIGATION_UNOBSERVABLE",
    "LaunchedEffectReader",
    "ReconcileOutcome",
    "reconcile_launch_attachment",
]

RECONCILE_ATTACHED = "attached"
RECONCILE_ALREADY_ATTACHED = "already-attached"
RECONCILE_EFFECT_UNOBSERVABLE = "effect-unobservable"
RECONCILE_OBLIGATION_UNOBSERVABLE = "obligation-unobservable"
RECONCILE_ATTACHMENT_UNAVAILABLE = "attachment-unavailable"
RECONCILE_NO_INTENT = "no-intent"


class LaunchedEffectReader(Protocol):
    """The one read this repair is allowed: what did that operation id launch?

    Deliberately read-only, and deliberately keyed on the operation id rather
    than on anything the half-written record holds — the record is the thing
    the crash interrupted, so the id is all this pass may trust.
    """

    def observe(self, *, operation_id: str) -> LaunchTarget | None: ...


@dataclass(frozen=True, kw_only=True)
class ReconcileOutcome:
    """What one reconciliation pass found, and the obligation it read it from.

    `result_epoch` and `original_deadline` are reported as READ from the
    record, never as supplied by a caller, because reporting the values that
    survived is the only way this pass can evidence that it preserved them.
    Both are `None` exactly when no record could be read.
    """

    state: str
    operation_id: str
    target: LaunchTarget | None
    result_epoch: int | None
    original_deadline: str | None


def reconcile_launch_attachment(
    *,
    obligation_store_root: Path,
    operation_id: str,
    reader: LaunchedEffectReader,
    observed_at: float,
    lock_budget: LockBudget | None = None,
) -> ReconcileOutcome:
    """Complete one obligation's attachment, idempotently, by operation id.

    `lock_budget` is the consumer's own deadline, threaded down so the write
    cannot outlive it. A pass that could not take the store lock reports
    `attachment-unavailable` and leaves the obligation in its half state, which
    is what brings the next pass back to it.
    """
    loaded = read_obligation_record(
        path=obligation_record_path(
            obligation_store_root=obligation_store_root, operation_id=operation_id
        )
    )
    if loaded.payload is None:
        return ReconcileOutcome(
            state=(
                RECONCILE_NO_INTENT
                if loaded.diagnostic is None
                else RECONCILE_OBLIGATION_UNOBSERVABLE
            ),
            operation_id=operation_id,
            target=None,
            result_epoch=None,
            original_deadline=None,
        )
    return _reconciled(
        payload=loaded.payload,
        obligation_store_root=obligation_store_root,
        operation_id=operation_id,
        reader=reader,
        observed_at=observed_at,
        lock_budget=lock_budget,
    )


def _reconciled(
    *,
    payload: dict[str, object],
    obligation_store_root: Path,
    operation_id: str,
    reader: LaunchedEffectReader,
    observed_at: float,
    lock_budget: LockBudget | None,
) -> ReconcileOutcome:
    """Decide one readable obligation's attachment against the real effect.

    Any attachment status other than `attached` is reported as
    `attachment-unavailable` — including a concurrent writer's `already-
    attached`, which is a true attachment THIS pass did not establish. The
    conservative label is the right one because the two cases have one remedy:
    re-read, which the next pass does and which then answers `already-attached`
    from the record itself.
    """
    epoch = cast("int", payload["result_epoch"])
    deadline = cast("str", payload["original_deadline"])
    attached = _recorded_target(payload=payload)
    if attached is not None:
        return ReconcileOutcome(
            state=RECONCILE_ALREADY_ATTACHED,
            operation_id=operation_id,
            target=attached,
            result_epoch=epoch,
            original_deadline=deadline,
        )
    observed = reader.observe(operation_id=operation_id)
    if observed is None:
        return ReconcileOutcome(
            state=RECONCILE_EFFECT_UNOBSERVABLE,
            operation_id=operation_id,
            target=None,
            result_epoch=epoch,
            original_deadline=deadline,
        )
    status = attach_launch_target(
        obligation_store_root=obligation_store_root,
        operation_id=operation_id,
        target=observed,
        attached_at=observed_at,
        lock_budget=lock_budget,
    )
    return ReconcileOutcome(
        state=RECONCILE_ATTACHED if status == ATTACH_ATTACHED else RECONCILE_ATTACHMENT_UNAVAILABLE,
        operation_id=operation_id,
        target=observed if status == ATTACH_ATTACHED else None,
        result_epoch=epoch,
        original_deadline=deadline,
    )


def _recorded_target(*, payload: dict[str, object]) -> LaunchTarget | None:
    """The target a readable record already names, or `None` while it names none.

    A target field that is PRESENT but not a pair of strings is read as naming
    none, so the reconciliation re-asks the effect rather than reporting a
    malformed attachment as a completed one.
    """
    recorded = payload["target"]
    if not isinstance(recorded, dict):
        return None
    fields = cast("dict[str, object]", recorded)
    kind = fields.get("kind")
    identity = fields.get("identity")
    if not isinstance(kind, str) or not isinstance(identity, str):
        return None
    return LaunchTarget(kind=kind, identity=identity)
