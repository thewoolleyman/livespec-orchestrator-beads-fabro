"""Record the repayment phases a dispatch skipped, from the item's own evidence.

An incident repayment item can travel `ready` -> `active` -> `acceptance`
through ordinary admission while its chain still names `repayment-admission`
(bd-ib-wz6bsa, measured on livespec-57r6qo). Every forward step of
`advance_repayment` is paired with a lifecycle state the item has already
left, and `bind-repayment-acceptance` names a `repayment-active` attempt, so
nothing could move the chain again.

`recover_repayment_phases` records the skipped `repayment-ready` and
`repayment-active` generations from what the ledger already proves: the item
rests `active` or `acceptance`, assigned `fabro`, under a factory dispatch
claim stamp. The dispatcher claims only an item ordinary admission approved to
`ready`, so that stamp also evidences the approval `repayment-ready` records.
It writes no lifecycle status; each generation goes through the same
conditional transition every repayment writer uses. A repeated delivery,
which re-reads the original admission generation as history, recovers the
recorded generations and writes nothing; a successor the chain has not recorded
is committed only against the current generation, so the transition writer
refuses a stale observation by name.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._incident_authority_types import (
    AuthorityRefusal,
    IncidentReading,
)
from livespec_orchestrator_beads_fabro._incident_phases import REPAYMENT_PHASES, lifecycle_state_for
from livespec_orchestrator_beads_fabro._incident_repayment_plan import REPAYMENT_OWNER
from livespec_orchestrator_beads_fabro.incident_normal_repayment import (
    RepaymentEntry,
    factory_claimed,
    record_repayment_successor,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient

__all__: list[str] = ["RECOVERABLE_STATUSES", "recover_repayment_phases"]

# The lifecycle states an item reaches only after a factory claimed it.
RECOVERABLE_STATUSES: frozenset[str] = frozenset(("active", "acceptance"))
# The states ordinary admission has not yet claimed, where advance-repayment records the phase.
_AWAITING_CLAIM: frozenset[str] = frozenset(("pending-approval", "ready"))
_ADMISSION, _READY, _ACTIVE = REPAYMENT_PHASES[:3]


def _refuse(*, code: str, detail: str) -> AuthorityRefusal:
    return AuthorityRefusal(code=code, detail=detail)


def recover_repayment_phases(
    *, client: BeadsClient, reading: IncidentReading
) -> RepaymentEntry | AuthorityRefusal:
    """Record each skipped phase up to `repayment-active`, or name why it may not."""
    attempt = reading.attempt
    if attempt.phase not in (_ADMISSION, _READY):
        return _refuse(code="incident-repayment-recovery-not-needed", detail=attempt.phase)
    record = client.show_issue(issue_id=attempt.item_id)
    status = record.get("status")
    if status in _AWAITING_CLAIM:
        detail = f"item rests at {status}; advance-repayment records this phase"
        return _refuse(code="incident-repayment-recovery-premature", detail=detail)
    if status not in RECOVERABLE_STATUSES:
        detail = f"item rests at {status}, outside the repayment dispatch path"
        return _refuse(code="incident-repayment-recovery-ineligible", detail=detail)
    if record.get("assignee") != REPAYMENT_OWNER or not factory_claimed(record=record):
        return _refuse(code="incident-repayment-claim-missing", detail=attempt.item_id)
    current, recovered = reading, True
    for phase in REPAYMENT_PHASES[REPAYMENT_PHASES.index(attempt.phase) + 1 : 3]:
        successor = replace(
            current.attempt,
            phase=phase,
            operation_id=f"{attempt.attempt_id}#{phase}",
            generation=current.attempt.generation + 1,
        )
        recorded = record_repayment_successor(client=client, reading=current, successor=successor)
        if isinstance(recorded, AuthorityRefusal):
            return recorded
        current, step_recovered = recorded
        recovered = recovered and step_recovered
    return RepaymentEntry(
        reading=current,
        operation_id=attempt.attempt_id,
        lifecycle_state=lifecycle_state_for(phase=_ACTIVE) or "",
        recovered=recovered,
    )
