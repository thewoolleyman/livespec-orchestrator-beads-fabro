"""What an incident still owes before any route may close it, and what acceptance grades.

Pure. `SPECIFICATION/contracts.md` section "Expedited incident lifecycle": no
accept, reconcile-merged, close/no-change-needed, proof-only resume or automatic
completion path may discharge an incident from its expedited merge alone.
Closure requires the current normal factory repayment PR merged, its normal
master CI successful, marker removal, the manual outcome, repaid verification
and spec debt, and disposition of related failures. Each of those is a NAMED
obligation here, and evidence that is missing, cancelled or unreadable stays an
obligation rather than satisfying completion: an absent observation is never a
pass.

Acceptance receives the original change and evidence corpus plus the follow-up,
not only the marker-removal diff, so the acceptance scope names every earlier
expedited carrier PR next to the current repayment carrier, and refuses to name
a current carrier the chain has not bound.
"""

from __future__ import annotations

from dataclasses import dataclass

from livespec_orchestrator_beads_fabro._incident_authority_types import IncidentAttempt
from livespec_orchestrator_beads_fabro._incident_phases import REPAYMENT_PHASES
from livespec_orchestrator_beads_fabro._incident_repayment_plan import MasterCiRun
from livespec_orchestrator_beads_fabro._incident_repayment_scope import (
    repayment_scope,
    validate_repayment_carrier,
)

__all__: list[str] = [
    "CLOSED_PHASE",
    "COMPLETION_PHASE",
    "IncidentAcceptanceScope",
    "IncidentCompletionEvidence",
    "acceptance_scope",
    "completion_obligations",
    "current_carrier",
]

CLOSED_PHASE = "closed"
# The one phase from which the incident may record `closed`: the current normal
# repayment carrier merged and awaits final proof.
COMPLETION_PHASE = REPAYMENT_PHASES[-1]
_SUCCESS = "success"
_CANCELLED = frozenset(("cancelled", "canceled"))
_NOT_ORIGINAL = frozenset((*REPAYMENT_PHASES, CLOSED_PHASE))


@dataclass(frozen=True, kw_only=True)
class IncidentCompletionEvidence:
    """What was OBSERVED about the repayment; a default field is an unobserved fact.

    `merged_pr_number` is the PR whose merge was observed. `master_ci` is the
    normal master run for the repayment merge, `None` when no run was read.
    `marker_paths` are head-tree paths still carrying the incident marker,
    `None` when the tree was not read. `manual_outcome` is the recorded manual
    outcome of the original behavior. `undisposed_failures` names related
    consumer or PR failures that still lack an owned disposition.
    """

    merged_pr_number: int | None = None
    master_ci: MasterCiRun | None = None
    marker_paths: tuple[str, ...] | None = None
    validated_paths: tuple[str, ...] = ()
    repaid_debt: tuple[str, ...] = ()
    manual_outcome: bool = False
    undisposed_failures: tuple[str, ...] = ()


@dataclass(frozen=True, kw_only=True)
class IncidentAcceptanceScope:
    """The carriers one acceptance pass grades together, or why it cannot grade them."""

    item_id: str
    original_prs: tuple[int, ...]
    current_pr: int | None
    refusal: str | None


def current_carrier(*, attempt: IncidentAttempt) -> int | None:
    """The bound normal repayment PR the chain names as current, if it names one."""
    if attempt.phase in (COMPLETION_PHASE, CLOSED_PHASE) and attempt.pr_number > 0:
        return attempt.pr_number
    return None


def _carrier_obligations(
    *, current: IncidentAttempt, evidence: IncidentCompletionEvidence
) -> list[str]:
    bound = current_carrier(attempt=current)
    if current.phase != COMPLETION_PHASE or bound is None:
        return [f"normal-repayment-unmerged:{current.phase}"]
    merged = evidence.merged_pr_number
    if merged is None:
        return [f"repayment-merge-unobserved:{bound}"]
    if merged != bound:
        return [f"repayment-pr-not-current:{merged}"]
    return [] if current.landed_commits else [f"repayment-landed-commits-unrecorded:{bound}"]


def _master_ci_obligations(*, current: IncidentAttempt, run: MasterCiRun | None) -> list[str]:
    if run is None:
        return ["repayment-master-ci-missing"]
    if run.conclusion in _CANCELLED:
        return [f"repayment-master-ci-cancelled:{run.run_id}"]
    if not run.complete:
        return [f"repayment-master-ci-incomplete:{run.run_id}"]
    if run.conclusion != _SUCCESS:
        return [f"repayment-master-ci-failed:{run.run_id}:{run.conclusion}"]
    if current.phase != COMPLETION_PHASE or run.head not in current.landed_commits:
        # The expedited repair's own master run proves nothing about the repayment.
        return [f"repayment-master-ci-not-for-repayment:{run.head}"]
    return []


def completion_obligations(
    *, history: tuple[IncidentAttempt, ...], evidence: IncidentCompletionEvidence
) -> tuple[str, ...]:
    """Every obligation the incident still owes; empty only when it may record `closed`."""
    if not history:
        return ("incident-history-empty",)
    current = history[-1]
    if current.phase == CLOSED_PHASE:
        return ()
    outstanding = _carrier_obligations(current=current, evidence=evidence)
    outstanding += _master_ci_obligations(current=current, run=evidence.master_ci)
    if evidence.marker_paths is None:
        outstanding.append("marker-removal-unobserved")
    outstanding += validate_repayment_carrier(
        scope=repayment_scope(attempt=current),
        marker_paths=evidence.marker_paths or (),
        validated_paths=evidence.validated_paths,
        repaid_debt=evidence.repaid_debt,
    ).outstanding
    if not evidence.manual_outcome:
        outstanding.append("manual-outcome-missing")
    outstanding += [f"related-failure-undisposed:{name}" for name in evidence.undisposed_failures]
    return tuple(outstanding)


def acceptance_scope(
    *, history: tuple[IncidentAttempt, ...], merged_pr: int | None
) -> IncidentAcceptanceScope:
    """The original expedited carriers plus the current repayment carrier, or a refusal.

    A merged PR the chain does not bind as the current repayment carrier — the
    earlier expedited repair resumed for proof, or a repayment the chain has not
    yet bound — is refused by name rather than graded as the incident's change.
    """
    if not history:
        return IncidentAcceptanceScope(
            item_id="",
            original_prs=(),
            current_pr=None,
            refusal="the incident chain records no attempt to grade",
        )
    latest = history[-1]
    item_id = latest.item_id
    original = tuple(
        sorted(
            {
                attempt.pr_number
                for attempt in history
                if attempt.phase not in _NOT_ORIGINAL and attempt.pr_number > 0
            }
        )
    )
    current = current_carrier(attempt=latest)
    refusal = None
    if current is None:
        refusal = (
            f"incident {item_id} binds no current normal repayment carrier "
            f"(phase {latest.phase}); merged PR #{merged_pr} is not graded as the "
            "incident's change"
        )
    elif merged_pr != current:
        refusal = (
            f"incident {item_id} binds repayment carrier PR #{current}; "
            f"merged PR #{merged_pr} is not the current carrier"
        )
    elif not original:
        refusal = f"incident {item_id} records no original expedited carrier to grade"
    return IncidentAcceptanceScope(
        item_id=item_id, original_prs=original, current_pr=current, refusal=refusal
    )
