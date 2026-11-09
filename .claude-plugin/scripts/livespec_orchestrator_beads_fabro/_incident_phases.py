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
    "MERGED_PHASE",
    "PHASE_LIFECYCLE_STATES",
    "PRE_PR_PHASES",
    "RECOVERY_PHASE",
    "REOPEN_FROM",
    "REPAYMENT_PHASES",
    "closure_successor_allowed",
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
MERGED_PHASE = "master-observation"
_REPAYMENT_ENTRY_FROM = MERGED_PHASE
# A current incident failure moves a merged attempt, a live repayment or a closed
# item into `reverting`: the first master failure of a merged attempt takes the
# same route as a later regression. A corrected repair opens only after the
# revert receipt.
REOPEN_FROM: tuple[str, ...] = (MERGED_PHASE, *REPAYMENT_PHASES, "closed")
RECOVERY_PHASE = "reverting"
CORRECTED_FROM = "collecting-failures"
_CLOSED_PHASE = "closed"


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

    A reopen binds the merged carrier the failure is attributed to, which is not
    any repayment carrier it supersedes; a corrected repair after the
    revert receipt, or after its bound PR closed unmerged on a failed check,
    opens its own fresh reserved branch. Everything else about the attempt
    still has to agree, which the transition writer checks.
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
    return reopen or corrected or _unmerged_correction(before=before, after=after)


def _unmerged_correction(*, before: IncidentAttempt, after: IncidentAttempt) -> bool:
    """A corrected `repair` after the bound expedited PR closed unmerged on a failed check.

    The bound carrier stays in history as recorded; the successor is a new
    attempt on its own fresh reserved branch with no PR. The forge facts that
    admit it (the PR closed unmerged at the bound head, the named run failed on
    that head) are the writer's gate and its retained recovery record.
    """
    return (
        before.phase == after.phase == "repair"
        and isinstance(before.carrier, PrBound)
        and before.pr_number > 0
        and isinstance(after.carrier, BranchReserved)
        and after.carrier.target_ref != before.carrier.target_ref
        and after.pr_number == 0
        and after.attempt_id != before.attempt_id
    )


def closure_successor_allowed(*, before: IncidentAttempt, after: IncidentAttempt) -> bool:
    """Whether `after` may follow `before` as far as the terminal `closed` phase goes.

    `closed` follows only `repayment-acceptance`: the current normal repayment
    carrier merged and its final proof was judged. No writer may record it from
    an expedited merge, an unmerged repayment or an earlier `closed` generation.
    """
    return after.phase != _CLOSED_PHASE or before.phase == REPAYMENT_PHASES[-1]
