"""Record and release controller-owned rollback conflicts on an incident attempt.

The incident phase table owns the lifecycle mapping. A conflict is retained
with its release condition, then a release returns to `reverting` until the
controller has a receipt, or advances to `collecting-failures` once it does.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import TYPE_CHECKING, Any, cast

from livespec_orchestrator_beads_fabro._incident_authority_types import (
    AuthorityRefusal,
    IncidentAttempt,
    IncidentReading,
)
from livespec_orchestrator_beads_fabro._incident_entry import (
    incident_claim_decided,
    prior_claim,
    takeover_metadata,
)
from livespec_orchestrator_beads_fabro._incident_phases import (
    RECOVERY_PHASE,
    lifecycle_state_for,
)
from livespec_orchestrator_beads_fabro._incident_recovery_plan import (
    RECOVERY_MARKER,
    RecoveryPlan,
    operation_digest,
    recovery_comment,
    recovery_record,
)
from livespec_orchestrator_beads_fabro._store_claim_tokens import change_claim
from livespec_orchestrator_beads_fabro.effects import parse_json
from livespec_orchestrator_beads_fabro.effects._incident_authority_transition import (
    commit_transition,
)
from livespec_orchestrator_beads_fabro.effects._incident_entry_writer import (
    require_current_generation,
)
from livespec_orchestrator_beads_fabro.incident_regression_recovery import (
    RECOVERY_WRITER,
    RecoveryEntry,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient

__all__: list[str] = [
    "RollbackConflict",
    "RollbackResolution",
    "record_rollback_conflict",
    "resolve_rollback_conflict",
]

_CONFLICT_INTENT = "incident-rollback-conflict"
_RELEASE_INTENT = "incident-rollback-conflict-release"


@dataclass(frozen=True, kw_only=True)
class RollbackConflict:
    """The controller's inverse-patch conflict and its exact release condition."""

    receipt: str
    release_condition: str


@dataclass(frozen=True, kw_only=True)
class RollbackResolution:
    """The satisfied condition and, when available, the controller revert receipt."""

    release_condition: str
    revert_receipt_id: str
    revert_commit: str


def _refuse(*, code: str, detail: str) -> AuthorityRefusal:
    return AuthorityRefusal(code=code, detail=detail)


def _append(*, client: BeadsClient, item_id: str, record: dict[str, Any]) -> None:
    body = recovery_comment(record=record)
    if body not in {row.get("text") for row in client.list_comments(issue_id=item_id)}:
        client.add_comment(issue_id=item_id, body=body)


def _commit(
    *, client: BeadsClient, reading: IncidentReading, plan: RecoveryPlan
) -> RecoveryEntry | AuthorityRefusal:
    committed = commit_transition(client=client, observed=reading, successor=plan.attempt)
    if isinstance(committed, AuthorityRefusal):
        return committed
    _append(client=client, item_id=plan.attempt.item_id, record=plan.record)
    return RecoveryEntry(
        reading=committed, operation_id=plan.operation_id, lifecycle_state=plan.lifecycle_state
    )


def _conflict_record(*, client: BeadsClient, attempt: IncidentAttempt) -> dict[str, Any] | None:
    for row in client.list_comments(issue_id=attempt.item_id):
        text = row.get("text")
        if not isinstance(text, str) or not text.startswith(RECOVERY_MARKER):
            continue
        parsed = parse_json(text=text[len(RECOVERY_MARKER) :])
        if not isinstance(parsed, dict):
            continue
        stored = cast("dict[str, Any]", parsed)
        if (
            stored.get("kind") == "rollback-conflict"
            and stored.get("item_id") == attempt.item_id
            and stored.get("operation_id") == attempt.operation_id
            and stored.get("generation") == attempt.generation
        ):
            return stored
    return None


def _claim(
    *, client: BeadsClient, before: IncidentAttempt, entry: RecoveryEntry, intent: str
) -> AuthorityRefusal | None:
    successor = entry.reading.attempt
    record = client.show_issue(issue_id=successor.item_id)
    decided = incident_claim_decided(
        operation_id=successor.operation_id,
        generation=successor.generation,
        owner=successor.owner,
    )
    if record.get("status") == entry.lifecycle_state and decided(record):
        return None
    current = require_current_generation(client=client, observed=entry.reading)
    if isinstance(current, AuthorityRefusal):
        return current
    result = change_claim(
        client=client,
        work_item_id=successor.item_id,
        writer=RECOVERY_WRITER,
        intent=intent,
        claim_tokens=True,
        status=entry.lifecycle_state,
        assignee=successor.owner,
        metadata=takeover_metadata(
            operation_id=successor.operation_id,
            generation=successor.generation,
            owner=successor.owner,
            principal=successor.owner,
            root_token_id=current.committed_token_id,
            prior=prior_claim(record=record),
        ),
        still_as_decided=incident_claim_decided(
            operation_id=before.operation_id,
            generation=before.generation,
            owner=before.owner,
        ),
    )
    return (
        None
        if result.outcome == "applied"
        else _refuse(code="incident-rollback-conflict-lifecycle-refused", detail=result.outcome)
    )


def record_rollback_conflict(
    *, client: BeadsClient, reading: IncidentReading, conflict: RollbackConflict
) -> RecoveryEntry | AuthorityRefusal:
    """Record the owned conflict and select its table-defined blocked state."""
    before = reading.attempt
    if before.phase != RECOVERY_PHASE:
        return _refuse(code="incident-rollback-conflict-not-eligible", detail=before.phase)
    operation_id = operation_digest(
        prefix="rollback-conflict",
        value={
            "item_id": before.item_id,
            "operation_id": before.operation_id,
            "generation": before.generation,
            "conflict": asdict(conflict),
        },
    )
    successor = replace(
        before,
        phase="rollback-conflict",
        operation_id=f"{operation_id}#rollback-conflict",
        generation=before.generation + 1,
    )
    entry = _commit(
        client=client,
        reading=reading,
        plan=RecoveryPlan(
            operation_id=operation_id,
            attempt=successor,
            lifecycle_state=lifecycle_state_for(phase=successor.phase) or "",
            record=recovery_record(
                kind="rollback-conflict", attempt=successor, conflict=asdict(conflict)
            ),
        ),
    )
    if isinstance(entry, AuthorityRefusal):
        return entry
    refusal = _claim(client=client, before=before, entry=entry, intent=_CONFLICT_INTENT)
    return entry if refusal is None else refusal


def _resolution_phase(*, resolution: RollbackResolution) -> str | AuthorityRefusal:
    receipt = (resolution.revert_receipt_id, resolution.revert_commit)
    if any(receipt) and not all(receipt):
        return _refuse(
            code="incident-rollback-conflict-revert-receipt-invalid",
            detail="receipt id and revert commit must both be present",
        )
    return "collecting-failures" if all(receipt) else RECOVERY_PHASE


def resolve_rollback_conflict(
    *, client: BeadsClient, reading: IncidentReading, resolution: RollbackResolution
) -> RecoveryEntry | AuthorityRefusal:
    """Release a conflict to only the phase selected by its receipt evidence."""
    before = reading.attempt
    if before.phase != "rollback-conflict":
        return _refuse(code="incident-rollback-conflict-not-eligible", detail=before.phase)
    record = _conflict_record(client=client, attempt=before)
    if record is None:
        return _refuse(code="incident-rollback-conflict-record-missing", detail=before.operation_id)
    raw_conflict = record.get("conflict")
    stored = cast("dict[str, object]", raw_conflict) if isinstance(raw_conflict, dict) else {}
    condition = stored.get("release_condition")
    if resolution.release_condition != condition:
        return _refuse(
            code="incident-rollback-conflict-release-unmet", detail=resolution.release_condition
        )
    phase = _resolution_phase(resolution=resolution)
    if isinstance(phase, AuthorityRefusal):
        return phase
    operation_id = operation_digest(
        prefix="rollback-release",
        value={
            "item_id": before.item_id,
            "operation_id": before.operation_id,
            "generation": before.generation,
            "resolution": asdict(resolution),
        },
    )
    successor = replace(
        before,
        phase=phase,
        operation_id=f"{operation_id}#{phase}",
        generation=before.generation + 1,
    )
    kind = "revert-receipt" if phase == "collecting-failures" else "rollback-release"
    entry = _commit(
        client=client,
        reading=reading,
        plan=RecoveryPlan(
            operation_id=operation_id,
            attempt=successor,
            lifecycle_state=lifecycle_state_for(phase=phase) or "",
            record=recovery_record(kind=kind, attempt=successor, resolution=asdict(resolution)),
        ),
    )
    if isinstance(entry, AuthorityRefusal):
        return entry
    refusal = _claim(client=client, before=before, entry=entry, intent=_RELEASE_INTENT)
    return entry if refusal is None else refusal
