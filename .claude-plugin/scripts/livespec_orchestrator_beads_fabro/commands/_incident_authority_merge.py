"""The `record-merge` action: record that the expedited repair carrier merged, as the forge says.

`SPECIFICATION/contracts.md` section "Expedited incident lifecycle" pairs the
phase `master-observation` with "the exact expedited repair carrier merged".
This is that phase's named writer. It trusts no caller-typed result: the chain
names the pull request, `gh pr view` says it merged and from which head, and the
landed commits and trees come from git over the merge commit's first-parent
history. The successor keeps the attempt, the head and the carrier it merged
under, so a regression attributed to this merge can still name them.

It is safe to run late. It reads the merge commit, never the tip of master, so a
revert that landed first changes nothing, and the observer's first-failure
recovery never waits for it. An exact retry recovers the recorded generation.
"""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-dzbwaq
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro._incident_authority_types import AuthorityRefusal
from livespec_orchestrator_beads_fabro._incident_carrier import PrBound
from livespec_orchestrator_beads_fabro._incident_phases import MERGED_PHASE, lifecycle_state_for
from livespec_orchestrator_beads_fabro.commands._incident_authority_binding import (
    MergedRepayment,
    observe_merged_repayment,
)
from livespec_orchestrator_beads_fabro.incident_authority import commit_incident_transition
from livespec_orchestrator_beads_fabro.incident_normal_repayment import RepaymentEntry

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient
    from livespec_orchestrator_beads_fabro._incident_authority_types import IncidentReading
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import CommandRunner

__all__: list[str] = ["CARRIER_MISMATCH", "PHASE_ORDER", "record_merge"]

CARRIER_MISMATCH = "incident-merge-carrier-mismatch"
PHASE_ORDER = "incident-merge-phase-order"
_STATE_MISMATCH = "incident-phase-state-mismatch"
_REPAIR = "repair"
_REFS_HEADS = "refs/heads/"


def _refuse(*, code: str, detail: str) -> AuthorityRefusal:
    return AuthorityRefusal(code=code, detail=detail)


def _precondition(*, client: BeadsClient, reading: IncidentReading) -> AuthorityRefusal | None:
    """Why the named attempt cannot record its merge, before the forge is read."""
    attempt = reading.attempt
    if attempt.phase != _REPAIR or not isinstance(attempt.carrier, PrBound):
        return _refuse(
            code=PHASE_ORDER, detail=f"{attempt.item_id}: {attempt.phase} is no PR-bound repair"
        )
    state = lifecycle_state_for(phase=MERGED_PHASE)
    status = client.show_issue(issue_id=attempt.item_id).get("status")
    if reading.is_current and status != state:
        return _refuse(
            code=_STATE_MISMATCH,
            detail=f"{MERGED_PHASE} pairs with {state}, item rests at {status}",
        )
    return None


def _exact(*, merged: MergedRepayment, reading: IncidentReading, carrier: PrBound) -> bool:
    return (
        _REFS_HEADS + merged.head_ref == carrier.target_ref
        and merged.head == carrier.remote_head == reading.attempt.head
    )


def record_merge(
    *,
    client: BeadsClient,
    reading: IncidentReading,
    runner: CommandRunner,
    repo: Path,
    repository: str,
) -> RepaymentEntry | AuthorityRefusal:
    """Record `master-observation` with the landed identities the forge and git report."""
    refusal = _precondition(client=client, reading=reading)
    if refusal is not None:
        return refusal
    attempt = reading.attempt
    carrier = cast("PrBound", attempt.carrier)
    merged = observe_merged_repayment(
        runner=runner, repo=repo, repository=repository, pr_number=attempt.pr_number
    )
    if isinstance(merged, AuthorityRefusal):
        return replace(merged, code=merged.code.replace("incident-repayment-", "incident-merge-"))
    if not _exact(merged=merged, reading=reading, carrier=carrier):
        detail = f"PR #{attempt.pr_number} merged {merged.head_ref} at {merged.head}"
        return _refuse(code=CARRIER_MISMATCH, detail=f"{detail}, not {carrier.remote_head}")
    successor = replace(
        attempt,
        phase=MERGED_PHASE,
        operation_id=f"{attempt.attempt_id}#{MERGED_PHASE}",
        generation=attempt.generation + 1,
        landed_commits=merged.landed_commits,
        landed_trees=merged.landed_trees,
    )
    committed = commit_incident_transition(client=client, observed=reading, successor=successor)
    if isinstance(committed, AuthorityRefusal):
        return committed
    return RepaymentEntry(
        reading=committed,
        operation_id=attempt.attempt_id,
        lifecycle_state=lifecycle_state_for(phase=MERGED_PHASE) or "",
        recovered=not reading.is_current,
    )
