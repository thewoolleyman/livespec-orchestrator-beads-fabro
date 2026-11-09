"""Planning a corrected repair after its expedited PR closed unmerged on a failed fast check.

Pure. `SPECIFICATION/contracts.md` section "Carrier identity before and after
PR creation": a `repair` attempt whose `pr-bound` expedited pull request failed
a retained fast check before merge may be followed by a corrected `repair`
attempt on the same item, as the next generation on a fresh `branch-reserved`
carrier under a different target ref. The bound carrier stays in history as
recorded. The forge facts are the gate: the bound PR closed and not merged at
the carrier's exact head and ref, and the named run completed with conclusion
failure on that head. The failed run joins the item's retained failures, so the
unchanged-reland rule refuses a correction at that head or citing that run.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._incident_authority_types import (
    AuthorityRefusal,
    IncidentReading,
)
from livespec_orchestrator_beads_fabro._incident_carrier import PrBound
from livespec_orchestrator_beads_fabro._incident_phases import lifecycle_state_for
from livespec_orchestrator_beads_fabro._incident_recovery_correction import (
    Correction,
    corrected_successor,
    correction_refusal,
)
from livespec_orchestrator_beads_fabro._incident_recovery_plan import (
    Finding,
    RecoveryPlan,
    operation_digest,
    recovery_record,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._incident_authority_types import IncidentAttempt

__all__: list[str] = [
    "CARRIER_MISMATCH",
    "NOT_ELIGIBLE",
    "PR_NOT_CLOSED_UNMERGED",
    "RUN_NOT_FAILED_ON_HEAD",
    "TARGET_REUSED",
    "UNMERGED_SOURCE",
    "UnmergedFailure",
    "plan_unmerged_correction",
    "unmerged_eligible",
]

NOT_ELIGIBLE = "incident-correction-not-eligible"
PR_NOT_CLOSED_UNMERGED = "incident-correction-pr-not-closed-unmerged"
CARRIER_MISMATCH = "incident-correction-carrier-mismatch"
RUN_NOT_FAILED_ON_HEAD = "incident-correction-run-not-failed-on-head"
TARGET_REUSED = "incident-correction-target-reused"
UNMERGED_SOURCE = "unmerged-pull-request"
_REPAIR = "repair"
_CLOSED = "CLOSED"
_FAILURE = "failure"
_REFS_HEADS = "refs/heads/"


@dataclass(frozen=True, kw_only=True)
class UnmergedFailure:
    """The bound PR and the named run, exactly as the forge reported them."""

    pr_number: int
    pr_state: str
    head_ref: str
    pr_head: str
    run_id: str
    run_head: str
    run_conclusion: str
    run_complete: bool


def _refuse(*, code: str, detail: str) -> AuthorityRefusal:
    return AuthorityRefusal(code=code, detail=detail)


def unmerged_eligible(*, reading: IncidentReading) -> bool:
    """Whether the observed attempt is the current `repair` bound to a real PR."""
    attempt = reading.attempt
    return (
        reading.is_current
        and attempt.phase == _REPAIR
        and isinstance(attempt.carrier, PrBound)
        and attempt.pr_number > 0
    )


def _forge_refusal(
    *, attempt: IncidentAttempt, carrier: PrBound, observed: UnmergedFailure
) -> AuthorityRefusal | None:
    """Why the forge does not show this carrier's PR closed unmerged after a failed run."""
    pr = f"PR #{attempt.pr_number}"
    if observed.pr_number != attempt.pr_number or observed.pr_state != _CLOSED:
        return _refuse(
            code=PR_NOT_CLOSED_UNMERGED, detail=f"{pr} is {observed.pr_state}, not closed unmerged"
        )
    if (
        _REFS_HEADS + observed.head_ref != carrier.target_ref
        or observed.pr_head != carrier.remote_head
    ):
        detail = f"{pr} is {observed.head_ref} at {observed.pr_head}, not {carrier.remote_head}"
        return _refuse(code=CARRIER_MISMATCH, detail=detail)
    failed = observed.run_complete and observed.run_conclusion == _FAILURE
    if not failed or observed.run_head != carrier.remote_head:
        detail = (
            f"run {observed.run_id} concluded {observed.run_conclusion or 'nothing'} "
            f"at {observed.run_head}, not failure at {carrier.remote_head}"
        )
        return _refuse(code=RUN_NOT_FAILED_ON_HEAD, detail=detail)
    return None


def plan_unmerged_correction(
    *,
    reading: IncidentReading,
    observed: UnmergedFailure,
    prior: tuple[Finding, ...],
    correction: Correction,
    target_ref: str,
) -> RecoveryPlan | AuthorityRefusal:
    """A corrected `repair` that retains the failed run and leaves the bound carrier as recorded."""
    current = reading.attempt
    if not unmerged_eligible(reading=reading) or not isinstance(current.carrier, PrBound):
        return _refuse(code=NOT_ELIGIBLE, detail=current.phase)
    carrier = current.carrier
    refusal = _forge_refusal(attempt=current, carrier=carrier, observed=observed)
    if refusal is not None:
        return refusal
    if target_ref == carrier.target_ref:
        return _refuse(code=TARGET_REUSED, detail=target_ref)
    failure = Finding(
        surface="pull-request",
        subject=f"pull-request#{current.pr_number}",
        run_id=observed.run_id,
        failed_head=carrier.remote_head,
        attributed_commit=carrier.remote_head,
        master_healthy=True,
    )
    retained = (*(f for f in prior if f != failure), failure)
    refusal = correction_refusal(correction=correction, retained=retained, current=current)
    if refusal is not None:
        return refusal
    operation_id = operation_digest(
        prefix="correction",
        value={
            "item_id": current.item_id,
            "operation_id": current.operation_id,
            "generation": current.generation,
            "source": UNMERGED_SOURCE,
            "failed_run": observed.run_id,
            "correction": asdict(correction),
        },
    )
    successor = corrected_successor(
        current=current, operation_id=operation_id, correction=correction, target_ref=target_ref
    )
    record = recovery_record(
        kind="corrected-attempt",
        attempt=successor,
        source=UNMERGED_SOURCE,
        superseded_attempt_id=current.attempt_id,
        superseded_generation=current.generation,
        closed_pr_number=current.pr_number,
        retained_failures=[asdict(f) for f in retained],
        correction=asdict(correction),
    )
    return RecoveryPlan(
        operation_id=operation_id,
        attempt=successor,
        lifecycle_state=lifecycle_state_for(phase=_REPAIR) or "",
        record=record,
    )
