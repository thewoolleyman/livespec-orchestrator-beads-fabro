"""Deriving the one normal repayment operation from a recorded successful attempt.

Pure. `SPECIFICATION/contracts.md` section "Expedited incident lifecycle": after
the expedited merge's complete normal master CI succeeds, the incident enters
ONE same-item normal factory repayment whose eligibility derives from the
recorded successful attempt and the outstanding repayment. The operation id is
a digest of that attempt and the master run, so a restart or duplicate delivery
derives the same operation instead of a second one.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace

from livespec_orchestrator_beads_fabro._incident_authority_types import (
    AuthorityRefusal,
    IncidentAttempt,
    IncidentReading,
)
from livespec_orchestrator_beads_fabro._incident_carrier import BranchReserved
from livespec_orchestrator_beads_fabro._incident_phases import REPAYMENT_PHASES, lifecycle_state_for

__all__: list[str] = [
    "REPAYMENT_ENTRY_FROM",
    "REPAYMENT_ENTRY_PHASE",
    "REPAYMENT_ENTRY_STATE",
    "REPAYMENT_OWNER",
    "MasterCiRun",
    "RepaymentPlan",
    "plan_repayment",
    "repayment_operation_id",
]

# The factory owns every repayment phase; the host owner ends at master-observation.
REPAYMENT_OWNER = "fabro"
REPAYMENT_ENTRY_FROM = "master-observation"
REPAYMENT_ENTRY_PHASE = REPAYMENT_PHASES[0]
REPAYMENT_ENTRY_STATE = lifecycle_state_for(phase=REPAYMENT_ENTRY_PHASE) or ""
_SUCCESS = "success"


@dataclass(frozen=True, kw_only=True)
class MasterCiRun:
    """The complete normal master run observed for one landed incident commit."""

    run_id: str
    head: str
    conclusion: str
    complete: bool


@dataclass(frozen=True, kw_only=True)
class RepaymentPlan:
    """The one repayment operation a successful attempt makes eligible."""

    operation_id: str
    attempt: IncidentAttempt
    lifecycle_state: str


def repayment_operation_id(*, attempt: IncidentAttempt, master_ci: MasterCiRun) -> str:
    """The deterministic operation id: a restart or duplicate delivery derives the same one."""
    digest = hashlib.sha256(
        json.dumps(
            {
                "item_id": attempt.item_id,
                "operation_id": attempt.operation_id,
                "generation": attempt.generation,
                "master_run_id": master_ci.run_id,
                "head": master_ci.head,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return f"repayment-{digest[:24]}"


def _eligible(*, attempt: IncidentAttempt) -> bool:
    return (
        attempt.phase == REPAYMENT_ENTRY_FROM
        and attempt.pr_number > 0
        and bool(attempt.landed_commits)
        and attempt.repayment_required
    )


def _master_ci_complete(*, attempt: IncidentAttempt, master_ci: MasterCiRun) -> bool:
    return (
        master_ci.complete
        and master_ci.conclusion == _SUCCESS
        and master_ci.head in attempt.landed_commits
    )


def plan_repayment(
    *, reading: IncidentReading, master_ci: MasterCiRun, target_ref: str
) -> RepaymentPlan | AuthorityRefusal:
    """Derive the eligible repayment from the recorded successful attempt, or refuse by name."""
    attempt = reading.attempt
    if not reading.is_current:
        return AuthorityRefusal(code="incident-repayment-stale-observation", detail=attempt.item_id)
    if not _eligible(attempt=attempt):
        return AuthorityRefusal(
            code="incident-repayment-not-eligible",
            detail=f"{attempt.item_id}: phase {attempt.phase} has no merged repair owing repayment",
        )
    if not _master_ci_complete(attempt=attempt, master_ci=master_ci):
        return AuthorityRefusal(
            code="incident-repayment-master-ci-outstanding",
            detail=(
                f"{attempt.item_id}: complete normal master CI success for a landed commit "
                f"remains an outstanding obligation (run {master_ci.run_id}: "
                f"{master_ci.conclusion}, complete={master_ci.complete})"
            ),
        )
    operation_id = repayment_operation_id(attempt=attempt, master_ci=master_ci)
    staged_tree = attempt.landed_trees[attempt.landed_commits.index(master_ci.head)]
    successor = replace(
        attempt,
        attempt_id=operation_id,
        phase=REPAYMENT_ENTRY_PHASE,
        operation_id=f"{operation_id}#{REPAYMENT_ENTRY_PHASE}",
        generation=attempt.generation + 1,
        owner=REPAYMENT_OWNER,
        base=master_ci.head,
        head=master_ci.head,
        pr_number=0,
        landed_commits=(),
        landed_trees=(),
        carrier=BranchReserved(
            target_ref=target_ref, input_parent=master_ci.head, staged_tree=staged_tree
        ),
    )
    return RepaymentPlan(
        operation_id=operation_id, attempt=successor, lifecycle_state=REPAYMENT_ENTRY_STATE
    )
