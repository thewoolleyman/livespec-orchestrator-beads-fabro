"""The incident phase table: lifecycle pairing and the repayment entry boundary.

`SPECIFICATION/contracts.md` section "Expedited incident lifecycle" publishes
one phase/canonical-lifecycle-state pair per phase. This module is that table,
pure, so the payload decoder, the transition writer and the repayment entrance
read ONE spelling of it. An unknown pair is a named configuration refusal at
every consumer, never a normal-mode fallback.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro._incident_authority_types import IncidentAttempt
from livespec_orchestrator_beads_fabro._incident_carrier import BranchReserved, PrBound

__all__: list[str] = [
    "CORRECTED_FROM",
    "PHASE_LIFECYCLE_STATES",
    "PRE_PR_PHASES",
    "RECOVERY_PHASE",
    "REOPEN_FROM",
    "REPAYMENT_PHASES",
    "fresh_repayment_carrier",
    "lifecycle_state_for",
    "recovery_carrier",
]

# Phase -> canonical lifecycle state, in the contract table's own order.
PHASE_LIFECYCLE_STATES: dict[str, str] = {
    "repair": "active",
    "master-observation": "active",
    "reverting": "active",
    "rollback-conflict": "blocked",
    "collecting-failures": "active",
    "repayment-admission": "pending-approval",
    "repayment-ready": "ready",
    "repayment-active": "active",
    "repayment-acceptance": "acceptance",
    "closed": "done",
}
# The normal repayment phases, in the order one same-item operation walks them.
REPAYMENT_PHASES: tuple[str, ...] = (
    "repayment-admission",
    "repayment-ready",
    "repayment-active",
    "repayment-acceptance",
)
# A snapshot with `pr_number: 0` and no landed pair is legal only while its
# carrier has not been bound: the host repair before its PR, and the fresh
# repayment carrier between its reservation and the factory run's own PR.
PRE_PR_PHASES: frozenset[str] = frozenset(("repair", *REPAYMENT_PHASES[:3]))
_REPAYMENT_ENTRY_FROM = "master-observation"
# An attributable regression reopens a live repayment or a closed item into
# `reverting`; a corrected repair opens only after the revert receipt.
REOPEN_FROM: tuple[str, ...] = (*REPAYMENT_PHASES, "closed")
RECOVERY_PHASE = "reverting"
CORRECTED_FROM = "collecting-failures"


def lifecycle_state_for(*, phase: str) -> str | None:
    """The canonical lifecycle state a phase publishes, or None for an unknown phase."""
    return PHASE_LIFECYCLE_STATES.get(phase)


def fresh_repayment_carrier(*, before: IncidentAttempt, after: IncidentAttempt) -> bool:
    """Whether `after` opens the one same-item repayment on a fresh reserved carrier.

    The expedited carrier merged under `master-observation`, so the repayment
    run needs its own branch: the one place a successor may start a new
    `branch-reserved` carrier instead of advancing the old one. Everything else
    about the attempt still has to agree, which the transition writer checks.
    """
    return (
        before.phase == _REPAYMENT_ENTRY_FROM
        and after.phase == REPAYMENT_PHASES[0]
        and isinstance(before.carrier, PrBound)
        and isinstance(after.carrier, BranchReserved)
        and after.carrier.target_ref != before.carrier.target_ref
        and after.pr_number == 0
    )


def recovery_carrier(*, before: IncidentAttempt, after: IncidentAttempt) -> bool:
    """Whether `after` is a recovery boundary that may name a different carrier.

    A reopen binds the merged carrier the regression is attributed to, which is
    not the repayment carrier it supersedes; a corrected repair after the
    revert receipt opens its own fresh reserved branch. Everything else about
    the attempt still has to agree, which the transition writer checks.
    """
    reopen = (
        before.phase in REOPEN_FROM
        and after.phase == RECOVERY_PHASE
        and isinstance(after.carrier, PrBound)
        and after.pr_number > 0
    )
    corrected = (
        before.phase == CORRECTED_FROM
        and after.phase == "repair"
        and isinstance(after.carrier, BranchReserved)
        and before.carrier is not None
        and after.carrier.target_ref != before.carrier.target_ref
    )
    return reopen or corrected
