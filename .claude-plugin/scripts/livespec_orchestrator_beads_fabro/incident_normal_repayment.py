"""Same-item normal factory repayment of a merged expedited incident repair.

`SPECIFICATION/contracts.md` section "Expedited incident lifecycle": after the
expedited merge's complete normal master CI succeeds, the incident enters ONE
same-item normal repayment. This module records each repayment phase as a
generation of the item's incident authority chain, pairs every phase with its
canonical lifecycle state, scrubs both incident execution flags out of a normal
dispatch, names what the repayment carrier still owes, and selects the current
carrier rather than the earlier repair one. Ordinary admission, gates,
provider and capacity policy stay the Dispatcher's; a repayment phase is
recorded only against the lifecycle state ordinary policy already produced.
The eligibility derivation lives in `_incident_repayment_plan`, the scope and
flag rules in `_incident_repayment_scope`; both are re-exported here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._incident_authority_types import (
    AuthorityRefusal,
    IncidentAttempt,
    IncidentReading,
)
from livespec_orchestrator_beads_fabro._incident_phases import REPAYMENT_PHASES, lifecycle_state_for
from livespec_orchestrator_beads_fabro._incident_repayment_plan import (
    REPAYMENT_ENTRY_FROM,
    REPAYMENT_OWNER,
    MasterCiRun,
    RepaymentPlan,
    plan_repayment,
    repayment_operation_id,
)
from livespec_orchestrator_beads_fabro._incident_repayment_scope import (
    INCIDENT_FLAGS,
    RepaymentScope,
    RepaymentValidation,
    incident_flags_delta,
    repayment_brief,
    repayment_scope,
    scrub_incident_flags,
    validate_repayment_carrier,
)
from livespec_orchestrator_beads_fabro._store_claim_tokens import change_claim
from livespec_orchestrator_beads_fabro._store_dispatch_claim import claim_stamp_from_record
from livespec_orchestrator_beads_fabro.effects._incident_authority_reader import read_authority
from livespec_orchestrator_beads_fabro.effects._incident_authority_transition import (
    commit_transition,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient, BeadsRecord

__all__: list[str] = [
    "INCIDENT_FLAGS",
    "REPAYMENT_OWNER",
    "REPAYMENT_WRITER",
    "MasterCiRun",
    "RepaymentEntry",
    "RepaymentPlan",
    "RepaymentScope",
    "RepaymentValidation",
    "advance_repayment",
    "enter_repayment",
    "incident_flags_delta",
    "plan_repayment",
    "repayment_brief",
    "repayment_operation_id",
    "repayment_scope",
    "scrub_incident_flags",
    "select_incident_pull_request",
    "validate_repayment_carrier",
]

REPAYMENT_WRITER = "incident-normal-repayment"
_HOST_STATE = lifecycle_state_for(phase=REPAYMENT_ENTRY_FROM) or ""
_ENTRY_INTENT = "incident-repayment-admission"
_QUERY_FIELDS = ("attempt_id", "phase", "operation_id", "generation", "owner")


@dataclass(frozen=True, kw_only=True)
class RepaymentEntry:
    """A recorded repayment phase; `recovered` means delivery found it already recorded."""

    reading: IncidentReading
    operation_id: str
    lifecycle_state: str
    recovered: bool


def _refuse(*, code: str, detail: str) -> AuthorityRefusal:
    return AuthorityRefusal(code=code, detail=detail)


def _recorded(
    *, client: BeadsClient, successor: IncidentAttempt
) -> IncidentReading | AuthorityRefusal | None:
    """The already recorded generation for this exact successor, if delivery repeats."""
    query = {key: getattr(successor, key) for key in _QUERY_FIELDS}
    found = read_authority(
        client=client,
        repository=successor.repository,
        item_id=successor.item_id,
        query=query,
        historical=True,
    )
    if isinstance(found, AuthorityRefusal):
        return None if found.code == "incident-authority-identity-mismatch" else found
    return found


def _record(
    *, client: BeadsClient, reading: IncidentReading, successor: IncidentAttempt
) -> tuple[IncidentReading, bool] | AuthorityRefusal:
    recorded = _recorded(client=client, successor=successor)
    if isinstance(recorded, AuthorityRefusal):
        return recorded
    if recorded is not None:
        return recorded, True
    committed = commit_transition(client=client, observed=reading, successor=successor)
    if isinstance(committed, AuthorityRefusal):
        return committed
    return committed, False


def enter_repayment(
    *, client: BeadsClient, reading: IncidentReading, master_ci: MasterCiRun, target_ref: str
) -> RepaymentEntry | AuthorityRefusal:
    """Record repayment-admission and return the item to ordinary admission, once.

    The phase is committed through the authority chain's conditional close and
    the lifecycle move through the item's claim token: the same canonical
    boundaries every other writer uses. A repeated delivery recovers the
    recorded generation and writes nothing more.
    """
    plan = plan_repayment(reading=reading, master_ci=master_ci, target_ref=target_ref)
    if isinstance(plan, AuthorityRefusal):
        return plan
    recorded = _record(client=client, reading=reading, successor=plan.attempt)
    if isinstance(recorded, AuthorityRefusal):
        return recorded
    committed, recovered = recorded
    record = client.show_issue(issue_id=plan.attempt.item_id)
    if record.get("status") != plan.lifecycle_state:
        result = change_claim(
            client=client,
            work_item_id=plan.attempt.item_id,
            writer=REPAYMENT_WRITER,
            intent=_ENTRY_INTENT,
            claim_tokens=True,
            status=plan.lifecycle_state,
            clear_assignee=True,
            still_as_decided=lambda row: row.get("status") == _HOST_STATE,
        )
        if result.outcome != "applied":
            return _refuse(code="incident-repayment-lifecycle-refused", detail=result.outcome)
    return RepaymentEntry(
        reading=committed,
        operation_id=plan.operation_id,
        lifecycle_state=plan.lifecycle_state,
        recovered=recovered,
    )


def _phase_refusal(
    *, record: BeadsRecord, attempt: IncidentAttempt, phase: str
) -> AuthorityRefusal | None:
    """Why `phase` may not be recorded now: order, lifecycle pairing or the factory claim."""
    index = REPAYMENT_PHASES.index(phase) if phase in REPAYMENT_PHASES else -1
    if index < 1 or attempt.phase != REPAYMENT_PHASES[index - 1]:
        return _refuse(code="incident-repayment-phase-order", detail=f"{attempt.phase} -> {phase}")
    state = lifecycle_state_for(phase=phase)
    if record.get("status") != state:
        return _refuse(
            code="incident-phase-state-mismatch",
            detail=f"{phase} pairs with {state}, item rests at {record.get('status')}",
        )
    if phase == REPAYMENT_PHASES[2] and (
        record.get("assignee") != REPAYMENT_OWNER or claim_stamp_from_record(record=record) is None
    ):
        return _refuse(code="incident-repayment-claim-missing", detail=attempt.item_id)
    return None


def advance_repayment(
    *,
    client: BeadsClient,
    reading: IncidentReading,
    phase: str,
    admission_complete: bool = False,
) -> RepaymentEntry | AuthorityRefusal:
    """Record the next repayment phase against the lifecycle state ordinary policy produced."""
    attempt = reading.attempt
    if not reading.is_current:
        return _refuse(code="incident-repayment-stale-observation", detail=attempt.item_id)
    if phase == REPAYMENT_PHASES[1] and not admission_complete:
        return _refuse(code="incident-repayment-admission-incomplete", detail=attempt.item_id)
    record = client.show_issue(issue_id=attempt.item_id)
    refusal = _phase_refusal(record=record, attempt=attempt, phase=phase)
    if refusal is not None:
        return refusal
    successor = replace(
        attempt,
        phase=phase,
        operation_id=f"{attempt.attempt_id}#{phase}",
        generation=attempt.generation + 1,
    )
    recorded = _record(client=client, reading=reading, successor=successor)
    if isinstance(recorded, AuthorityRefusal):
        return recorded
    committed, recovered = recorded
    return RepaymentEntry(
        reading=committed,
        operation_id=attempt.attempt_id,
        lifecycle_state=lifecycle_state_for(phase=phase) or "",
        recovered=recovered,
    )


def select_incident_pull_request(
    *, reading: IncidentReading, candidates: Sequence[int]
) -> int | AuthorityRefusal:
    """Select the current attempt's bound PR among merged candidates, never an earlier one."""
    attempt = reading.attempt
    if not reading.is_current:
        return _refuse(code="incident-carrier-stale", detail=attempt.item_id)
    if attempt.pr_number <= 0:
        return _refuse(
            code="incident-carrier-unbound",
            detail=(
                f"{attempt.item_id}: {attempt.phase} has no bound pull request; "
                f"candidates {list(candidates)} are earlier carriers"
            ),
        )
    if attempt.pr_number not in candidates:
        return _refuse(code="incident-carrier-not-merged", detail=str(attempt.pr_number))
    return attempt.pr_number
