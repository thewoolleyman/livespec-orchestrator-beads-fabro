"""Planning the revert receipt and the corrected expedited attempt after a reopen.

Pure. `SPECIFICATION/contracts.md` section "Expedited incident lifecycle": a
completed revert and collected failure evidence permit a new repair phase only
with fresh evidence. The controller's revert receipt moves `reverting` to
`collecting-failures`; a corrected `repair` attempt then opens on its own
reserved branch, carries the retained original failures forward, and needs a
fresh repair or a new measured resolution rather than an unchanged reland.
Final normal repayment stays owed throughout.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace

from livespec_orchestrator_beads_fabro._incident_authority_types import (
    AuthorityRefusal,
    IncidentAttempt,
    IncidentReading,
)
from livespec_orchestrator_beads_fabro._incident_carrier import BranchReserved
from livespec_orchestrator_beads_fabro._incident_phases import (
    CORRECTED_FROM,
    RECOVERY_PHASE,
    lifecycle_state_for,
)
from livespec_orchestrator_beads_fabro._incident_recovery_plan import (
    Finding,
    RecoveryPlan,
    operation_digest,
    recovery_record,
)

__all__: list[str] = [
    "Correction",
    "RevertReceipt",
    "corrected_successor",
    "correction_refusal",
    "plan_corrected_attempt",
    "plan_revert_receipt",
]

_CORRECTION_KINDS = ("repair", "measured-resolution")


def _refuse(*, code: str, detail: str) -> AuthorityRefusal:
    return AuthorityRefusal(code=code, detail=detail)


@dataclass(frozen=True, kw_only=True)
class RevertReceipt:
    """The trusted controller's receipt for the recorded inverse recovery."""

    receipt_id: str
    revert_commit: str


@dataclass(frozen=True, kw_only=True)
class Correction:
    """Fresh evidence a corrected expedited attempt needs: a new repair or a measured fix."""

    kind: str
    evidence_id: str
    base: str
    head: str
    staged_tree: str


def plan_revert_receipt(
    *, reading: IncidentReading, receipt: RevertReceipt
) -> RecoveryPlan | AuthorityRefusal:
    """Record the controller's revert receipt: `reverting` becomes `collecting-failures`."""
    current = reading.attempt
    if not reading.is_current or current.phase != RECOVERY_PHASE:
        return _refuse(code="incident-revert-not-eligible", detail=current.phase)
    successor = replace(
        current,
        phase=CORRECTED_FROM,
        operation_id=f"{current.attempt_id}#{CORRECTED_FROM}",
        generation=current.generation + 1,
    )
    record = recovery_record(kind="revert-receipt", attempt=successor, receipt=asdict(receipt))
    return RecoveryPlan(
        operation_id=current.attempt_id,
        attempt=successor,
        lifecycle_state=lifecycle_state_for(phase=CORRECTED_FROM) or "",
        record=record,
    )


def correction_refusal(
    *, correction: Correction, retained: tuple[Finding, ...], current: IncidentAttempt
) -> AuthorityRefusal | None:
    """Why the correction is not fresh: no evidence kind, or an unchanged reland."""
    if correction.kind not in _CORRECTION_KINDS or not correction.evidence_id:
        return _refuse(code="incident-correction-evidence-missing", detail=correction.kind)
    failed_heads = {failure.failed_head for failure in retained}
    reland = correction.head in failed_heads or correction.head in current.landed_commits
    reused = correction.evidence_id in {failure.run_id for failure in retained}
    if (correction.kind == "repair" and reland) or reused:
        return _refuse(
            code="incident-correction-unchanged-reland",
            detail=f"{correction.kind} {correction.evidence_id} at {correction.head}",
        )
    return None


def corrected_successor(
    *, current: IncidentAttempt, operation_id: str, correction: Correction, target_ref: str
) -> IncidentAttempt:
    """The next-generation `repair` attempt on its own fresh reserved branch, owing repayment."""
    return replace(
        current,
        attempt_id=operation_id,
        phase="repair",
        operation_id=f"{operation_id}#repair",
        generation=current.generation + 1,
        base=correction.base,
        head=correction.head,
        pr_number=0,
        landed_commits=(),
        landed_trees=(),
        repayment_required=True,
        carrier=BranchReserved(
            target_ref=target_ref,
            input_parent=correction.base,
            staged_tree=correction.staged_tree,
        ),
    )


def plan_corrected_attempt(
    *,
    reading: IncidentReading,
    retained: tuple[Finding, ...],
    correction: Correction,
    target_ref: str,
) -> RecoveryPlan | AuthorityRefusal:
    """A corrected `repair` attempt that keeps the original failures and owes repayment."""
    current = reading.attempt
    if not reading.is_current or current.phase != CORRECTED_FROM:
        return _refuse(code="incident-correction-not-eligible", detail=current.phase)
    if not retained:
        return _refuse(code="incident-correction-failures-missing", detail=current.item_id)
    refusal = correction_refusal(correction=correction, retained=retained, current=current)
    if refusal is not None:
        return refusal
    operation_id = operation_digest(
        prefix="correction",
        value={
            "item_id": current.item_id,
            "operation_id": current.operation_id,
            "generation": current.generation,
            "correction": asdict(correction),
        },
    )
    successor = corrected_successor(
        current=current, operation_id=operation_id, correction=correction, target_ref=target_ref
    )
    record = recovery_record(
        kind="corrected-attempt",
        attempt=successor,
        retained_failures=[asdict(failure) for failure in retained],
        correction=asdict(correction),
    )
    return RecoveryPlan(
        operation_id=operation_id,
        attempt=successor,
        lifecycle_state=lifecycle_state_for(phase="repair") or "",
        record=record,
    )
