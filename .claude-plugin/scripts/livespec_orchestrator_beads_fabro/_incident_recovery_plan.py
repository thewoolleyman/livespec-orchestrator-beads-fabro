"""Planning incident regression recovery: attribution, reopen and deferred findings.

Pure. `SPECIFICATION/contracts.md` section "Expedited incident lifecycle" and the
scenarios "an attributable regression fences repayment and reopens the same
incident" and "a deferred-proof-only finding is repaired without reverting
healthy master". A failure demonstrated on master, another pull request or an
adopted consumer, with change evidence naming a landed incident commit, moves
the SAME item into `reverting` from a merged attempt, a live repayment or
`closed` as the next fenced generation and requests recovery. A defect found
only by deferred factory proof while master stays healthy is owed by the normal
repayment pull request instead, and never reverts the successful merge. The
corrected attempt after a revert is planned in `_incident_recovery_correction`;
final normal repayment stays owed throughout.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from typing import Any

from livespec_orchestrator_beads_fabro._incident_authority_types import (
    AuthorityRefusal,
    IncidentAttempt,
    IncidentReading,
)
from livespec_orchestrator_beads_fabro._incident_carrier import PrBound
from livespec_orchestrator_beads_fabro._incident_phases import (
    RECOVERY_PHASE,
    REOPEN_FROM,
    REPAYMENT_PHASES,
    lifecycle_state_for,
)

__all__: list[str] = [
    "DEFERRED_PROOF",
    "RECOVERY_MARKER",
    "REGRESSION_SURFACES",
    "Finding",
    "FindingDisposition",
    "RecoveryPlan",
    "classify_finding",
    "operation_digest",
    "plan_deferred_finding",
    "plan_reopen",
    "recovery_comment",
    "recovery_record",
]

RECOVERY_MARKER = "livespec-incident-recovery-v1\n"
# `trunk` is the repository's default branch, whatever it is named.
REGRESSION_SURFACES: tuple[str, ...] = ("trunk", "pull-request", "consumer")
DEFERRED_PROOF = "deferred-proof"


@dataclass(frozen=True, kw_only=True)
class Finding:
    """A failure observed after an incident merge, with the change evidence it carries."""

    surface: str
    subject: str
    run_id: str
    failed_head: str
    attributed_commit: str
    master_healthy: bool


@dataclass(frozen=True, kw_only=True)
class FindingDisposition:
    """Where a finding is owed: a recovery reopen, or the normal repayment pull request."""

    kind: str
    obligation: str


@dataclass(frozen=True, kw_only=True)
class RecoveryPlan:
    """One recovery generation to commit, its lifecycle state and its retained record."""

    operation_id: str
    attempt: IncidentAttempt
    lifecycle_state: str
    record: dict[str, Any]


def _refuse(*, code: str, detail: str) -> AuthorityRefusal:
    return AuthorityRefusal(code=code, detail=detail)


def operation_digest(*, prefix: str, value: dict[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return f"{prefix}-{hashlib.sha256(encoded).hexdigest()[:24]}"


def classify_finding(
    *, finding: Finding, attributed: IncidentAttempt
) -> FindingDisposition | AuthorityRefusal:
    """Route a finding: deferred-proof-only stays in repayment; attributed regressions reopen."""
    if finding.surface == DEFERRED_PROOF:
        if not finding.master_healthy:
            return _refuse(
                code="incident-finding-not-isolated",
                detail=f"{finding.run_id}: master is unhealthy; attribute the master failure",
            )
        return FindingDisposition(
            kind="repair-in-repayment", obligation=f"deferred-finding:{finding.run_id}"
        )
    if finding.surface not in REGRESSION_SURFACES:
        return _refuse(code="incident-finding-surface-unknown", detail=finding.surface)
    if finding.attributed_commit not in attributed.landed_commits:
        return _refuse(
            code="incident-regression-unattributed",
            detail=f"{finding.run_id}: {finding.attributed_commit} is no landed incident commit",
        )
    return FindingDisposition(kind="reopen-recovery", obligation=f"recovery:{finding.run_id}")


def recovery_comment(*, record: dict[str, Any]) -> str:
    """The retained canonical recovery record: evidence, never generation authority."""
    return RECOVERY_MARKER + json.dumps(record, sort_keys=True, separators=(",", ":"))


def recovery_record(*, kind: str, attempt: IncidentAttempt, **fields: object) -> dict[str, Any]:
    return {
        "schema": 1,
        "kind": kind,
        "repository": attempt.repository,
        "item_id": attempt.item_id,
        "operation_id": attempt.operation_id,
        "generation": attempt.generation,
        "repayment_owed": True,
        **fields,
    }


def _merged_paths(*, kept: tuple[str, ...], added: tuple[str, ...]) -> tuple[str, ...]:
    return (*kept, *(path for path in added if path not in kept))


def plan_reopen(
    *, reading: IncidentReading, attributed: IncidentAttempt, finding: Finding, owner: str
) -> RecoveryPlan | AuthorityRefusal:
    """Reopen the same item into `reverting` for an attributed regression, or refuse by name."""
    current = reading.attempt
    if not reading.is_current:
        return _refuse(code="incident-reopen-stale-observation", detail=current.item_id)
    if current.phase not in REOPEN_FROM:
        return _refuse(code="incident-reopen-not-eligible", detail=current.phase)
    if (
        (attributed.repository, attributed.item_id) != (current.repository, current.item_id)
        or attributed.generation > current.generation
        or not isinstance(attributed.carrier, PrBound)
    ):
        return _refuse(code="incident-reopen-attribution-mismatch", detail=attributed.attempt_id)
    disposition = classify_finding(finding=finding, attributed=attributed)
    if isinstance(disposition, AuthorityRefusal):
        return disposition
    if disposition.kind != "reopen-recovery":
        return _refuse(
            code="incident-finding-deferred-proof-only",
            detail=f"{disposition.obligation} is owed by the normal repayment pull request",
        )
    operation_id = operation_digest(
        prefix="recovery",
        value={
            "item_id": current.item_id,
            "operation_id": current.operation_id,
            "generation": current.generation,
            "finding": asdict(finding),
        },
    )
    successor = replace(
        attributed,
        attempt_id=operation_id,
        phase=RECOVERY_PHASE,
        operation_id=f"{operation_id}#{RECOVERY_PHASE}",
        generation=current.generation + 1,
        owner=owner,
        original_paths=_merged_paths(kept=current.original_paths, added=attributed.original_paths),
        deferred_work=current.deferred_work,
        repayment_required=True,
    )
    record = recovery_record(
        kind="recovery-request",
        attempt=successor,
        superseded_operation_id=current.operation_id,
        superseded_generation=current.generation,
        attributed_generation=attributed.generation,
        attributed_pr_number=attributed.pr_number,
        retained_failures=[asdict(finding)],
    )
    return RecoveryPlan(
        operation_id=operation_id,
        attempt=successor,
        lifecycle_state=lifecycle_state_for(phase=RECOVERY_PHASE) or "",
        record=record,
    )


def plan_deferred_finding(
    *, reading: IncidentReading, finding: Finding
) -> RecoveryPlan | AuthorityRefusal:
    """Owe a deferred-proof-only defect in the live repayment, leaving master's merge alone.

    The finding becomes recorded deferred debt of the current repayment
    generation, so the repayment pull request's normal validation names it
    outstanding until repaid. Nothing reopens, reverts or leaves repayment.
    """
    current = reading.attempt
    if not reading.is_current or current.phase not in REPAYMENT_PHASES[:3]:
        return _refuse(code="incident-finding-repayment-not-live", detail=current.phase)
    if finding.surface != DEFERRED_PROOF:
        # Master, another pull request or a consumer: a regression, never repayment debt.
        return _refuse(code="incident-finding-requires-recovery", detail=finding.run_id)
    disposition = classify_finding(finding=finding, attributed=current)
    if isinstance(disposition, AuthorityRefusal):
        return disposition
    successor = replace(
        current,
        operation_id=f"{current.attempt_id}#{disposition.obligation}",
        generation=current.generation + 1,
        deferred_work=(*current.deferred_work, disposition.obligation),
    )
    record = recovery_record(kind="deferred-finding", attempt=successor, finding=asdict(finding))
    return RecoveryPlan(
        operation_id=current.attempt_id,
        attempt=successor,
        lifecycle_state=lifecycle_state_for(phase=current.phase) or "",
        record=record,
    )
