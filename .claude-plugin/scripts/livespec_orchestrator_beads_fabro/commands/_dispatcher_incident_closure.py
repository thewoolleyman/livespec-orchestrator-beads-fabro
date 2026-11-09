"""The incident closure gate every Dispatcher and valve closure route reads.

`SPECIFICATION/contracts.md` section "Expedited incident lifecycle": no accept,
reconcile-merged, close/no-change-needed, proof-only resume or automatic
completion path may discharge an incident from its expedited merge alone. Each
route reads the item's standing here immediately before its close and holds the
item while the standing names an outstanding obligation; a normal item, which
carries no incident genesis, reads as closable and is unaffected. The proof
pointer is written only for the carrier the chain binds as current, so a resumed
earlier repair PR publishes no pointer that could stand in for final proof.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Literal

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro._incident_repayment_scope import (
    repayment_scope,
    validate_repayment_carrier,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_pointer_write import (
    write_proof_pointer,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_valves import acceptance_decision
from livespec_orchestrator_beads_fabro.commands._incident_authority_completion import (
    pr_head_marker_paths,
)
from livespec_orchestrator_beads_fabro.incident_completion import (
    IncidentAcceptanceScope,
    IncidentStanding,
    incident_acceptance_scope,
    incident_effect_refusal,
    read_incident_standing,
)

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import CommandRunner
    from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
    from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_evidence import ProofLeg
    from livespec_orchestrator_beads_fabro.commands._dispatcher_valves import AcceptanceDecision
    from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = [
    "INCIDENT_HOLD_STAGE",
    "INCIDENT_OBLIGATION_ERR",
    "INCIDENT_POINTER_STAGE",
    "IncidentAcceptance",
    "closure_obligations_for",
    "incident_acceptance_for",
    "incident_decision",
    "incident_hold_record",
    "incident_holds",
    "incident_refusal_detail",
    "incident_standing_for",
]

INCIDENT_HOLD_STAGE = "incident-obligation-outstanding"
INCIDENT_POINTER_STAGE = "incident-proof-pointer-refused"
INCIDENT_OBLIGATION_ERR = "incident-obligation-outstanding"


@dataclass(frozen=True, kw_only=True)
class IncidentAcceptance:
    """One acceptance pass's incident inputs: the standing, what it grades, and its tenant.

    `marker_paths` are the paths of the graded repayment PR's head that still
    carry the incident marker; `None` means that head was not read, which leaves
    `marker-removal-unobserved` standing rather than reporting the marker gone.
    """

    standing: IncidentStanding
    scope: IncidentAcceptanceScope | None
    config: StoreConfig
    marker_paths: tuple[str, ...] | None = None


def incident_standing_for(*, config: StoreConfig, item_id: str) -> IncidentStanding:
    """Read the item's incident standing from the tenant the store descriptor names."""
    return read_incident_standing(client=make_beads_client(config=config), item_id=item_id)


def incident_acceptance_for(
    *,
    config: StoreConfig,
    item_id: str,
    merged_pr: int | None,
    runner: CommandRunner | None = None,
) -> IncidentAcceptance:
    """The standing plus the carriers one acceptance pass of this merge grades.

    When the merge is the chain's current repayment carrier and the tenant
    descriptor names its checkout (`repo_root`), the PR's head is read for the
    incident marker, so a repayment that left it in place is graded with that
    marker named as an outstanding obligation.
    """
    standing = incident_standing_for(config=config, item_id=item_id)
    scope = incident_acceptance_scope(standing=standing, merged_pr=merged_pr)
    return IncidentAcceptance(
        standing=standing,
        scope=scope,
        config=config,
        marker_paths=_repayment_head_markers(
            standing=standing, scope=scope, repo=config.repo_root, runner=runner
        ),
    )


def _repayment_head_markers(
    *,
    standing: IncidentStanding,
    scope: IncidentAcceptanceScope | None,
    repo: Path | None,
    runner: CommandRunner | None,
) -> tuple[str, ...] | None:
    """The marker-carrying paths of the graded repayment PR's head; `()` when none is graded."""
    if scope is None or scope.refusal is not None or scope.current_pr is None:
        return ()
    if repo is None or standing.repository is None:
        return None
    return pr_head_marker_paths(
        runner=runner if runner is not None else ShellCommandRunner(),
        repo=repo,
        repository=standing.repository,
        pr_number=scope.current_pr,
        item_id=standing.item_id,
    )


def _marker_obligations(*, incident: IncidentAcceptance) -> tuple[str, ...]:
    """`marker-present:<path>` for each path of the graded head that still carries the marker."""
    if not incident.marker_paths:
        return ()
    attempt = incident.standing.history[-1]
    scope = repayment_scope(attempt=attempt)
    return validate_repayment_carrier(
        scope=scope,
        marker_paths=incident.marker_paths,
        validated_paths=scope.original_paths,
        repaid_debt=scope.deferred_work,
    ).outstanding


def _refused_effect(
    *, config: StoreConfig, standing: IncidentStanding, effect: Literal["proof", "closure"]
) -> str | None:
    """Revalidate the observed generation right before `effect`; None when it still holds."""
    if standing.reading is None:
        return None
    refusal = incident_effect_refusal(
        client=make_beads_client(config=config), standing=standing, effect=effect
    )
    return None if refusal is None else f"{refusal.code}: {refusal.detail}"


def closure_obligations_for(*, config: StoreConfig, item_id: str) -> tuple[str, ...]:
    """What holds the item open immediately before a close; empty means it may close.

    The standing's obligations first; then the generation it observed is
    revalidated, so a close against a superseded or stale generation is refused.
    """
    standing = incident_standing_for(config=config, item_id=item_id)
    if standing.outstanding:
        return standing.outstanding
    refused = _refused_effect(config=config, standing=standing, effect="closure")
    return () if refused is None else (refused,)


def incident_refusal_detail(*, item_id: str, outstanding: tuple[str, ...]) -> str:
    """One line naming the incident and every obligation that holds it open."""
    return (
        f"work-item {item_id} is an expedited incident whose final normal proof "
        f"is outstanding: {'; '.join(outstanding)}"
    )


def incident_hold_record(
    *, item_id: str, route: str, outstanding: tuple[str, ...]
) -> dict[str, object]:
    """The journal record of a closure route that held an incident open."""
    return {
        "stage": INCIDENT_HOLD_STAGE,
        "work_item_id": item_id,
        "route": route,
        "outstanding": list(outstanding),
    }


def incident_decision(  # noqa: PLR0913 — kw-only; the pointer write's inputs, the incident and the policy.
    *,
    repo: Path,
    item: WorkItem,
    outcome: DispatchOutcome,
    proof: ProofLeg | None,
    journal: JournalFile,
    incident: IncidentAcceptance,
    policy: str,
) -> AcceptanceDecision:
    """Write the proof pointer, then decide acceptance with the close withheld from an incident.

    The pointer is not written for a merge the incident chain does not bind as
    its current carrier (a resumed earlier repair PR), nor once the repayment
    generation it graded is superseded: neither can stand in for final normal
    proof. The decision's close is withdrawn while the incident owes anything,
    so neither the completed nor the no-change-needed close can discharge it
    and the item parks instead.
    """
    scope = incident.scope
    refusal = (scope.refusal if scope is not None else None) or _refused_effect(
        config=incident.config, standing=incident.standing, effect="proof"
    )
    if refusal is not None:
        refused: dict[str, object] = {"stage": INCIDENT_POINTER_STAGE, "work_item_id": item.id}
        journal.append(record=refused | {"reason": refusal})
    else:
        write_proof_pointer(repo=repo, item=item, outcome=outcome, proof=proof, journal=journal)
    decision = acceptance_decision(policy=policy)
    if incident_holds(incident=incident, journal=journal, route="complete"):
        return replace(decision, to_done=False)
    return decision


def incident_holds(*, incident: IncidentAcceptance, journal: JournalFile, route: str) -> bool:
    """Whether a close must not discharge the incident now; a hold is journaled by route.

    It holds while the standing owes anything, and when the generation it
    observed is no longer the chain's head immediately before the close.
    """
    standing = incident.standing
    outstanding = (*standing.outstanding, *_marker_obligations(incident=incident))
    if not outstanding:
        refused = _refused_effect(config=incident.config, standing=standing, effect="closure")
        outstanding = () if refused is None else (refused,)
    if not outstanding:
        return False
    record = incident_hold_record(item_id=standing.item_id, route=route, outstanding=outstanding)
    journal.append(record=record)
    return True
