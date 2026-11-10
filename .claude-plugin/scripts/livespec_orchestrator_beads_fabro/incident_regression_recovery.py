"""Regression recovery of an expedited incident on its one canonical item.

`SPECIFICATION/contracts.md` section "Expedited incident lifecycle" and the
scenarios "an attributable regression fences repayment and reopens the same
incident" and "a deferred-proof-only finding is repaired without reverting
healthy master". Each step is a generation of the item's incident authority
chain committed through the retained conditional-close writer, plus one
retained `livespec-incident-recovery-v1` record for inspection:

- `reopen_for_regression` reopens the same item (a merged attempt whose master
  run failed, a live repayment or a closed one) into `reverting` for a failure
  attributed to a landed incident commit, requests recovery, and takes the item
  back from the factory through its claim token with the incident holder's
  stamp, so the superseded run lands nothing.
- `require_repayment_current` is the gate a repayment merge, proof or closure
  takes immediately before its side effect; a superseded repayment is refused.
- `record_deferred_finding` owes a deferred-proof-only defect in the live
  repayment pull request instead, and never reverts master's merge.
- `record_revert_receipt` and `enter_corrected_attempt` carry a corrected
  expedited attempt that retains the original failures and needs fresh repair
  or measured resolution evidence; final normal repayment stays owed.
- `enter_unmerged_correction` opens the same kind of corrected attempt from a
  `repair` whose bound expedited PR closed unmerged after a retained fast check
  failed on its head, retaining that failed run with the item's failures.

First-failure recovery itself (the revert) belongs to the trusted controller;
this module records its request and receipt. Recovery attempts are counted
apart from ordinary acceptance rework and nonconvergence budgets.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from typing import TYPE_CHECKING, Any, Literal, cast

from livespec_orchestrator_beads_fabro._incident_authority_types import (
    AuthorityRefusal,
    IncidentAttempt,
    IncidentReading,
)
from livespec_orchestrator_beads_fabro._incident_entry import (
    GENERATION_STALE,
    incident_claim_decided,
    prior_claim,
    takeover_metadata,
)
from livespec_orchestrator_beads_fabro._incident_phases import REPAYMENT_PHASES
from livespec_orchestrator_beads_fabro._incident_recovery_correction import (
    Correction,
    RevertReceipt,
    plan_corrected_attempt,
    plan_revert_receipt,
)
from livespec_orchestrator_beads_fabro._incident_recovery_plan import (
    DEFERRED_PROOF,
    RECOVERY_MARKER,
    REGRESSION_SURFACES,
    Finding,
    FindingDisposition,
    RecoveryPlan,
    classify_finding,
    plan_deferred_finding,
    plan_reopen,
    recovery_comment,
)
from livespec_orchestrator_beads_fabro._incident_unmerged_correction import (
    UnmergedFailure,
    plan_unmerged_correction,
)
from livespec_orchestrator_beads_fabro._store_claim_tokens import change_claim
from livespec_orchestrator_beads_fabro.effects import parse_json
from livespec_orchestrator_beads_fabro.effects._incident_authority_reader import read_authority
from livespec_orchestrator_beads_fabro.effects._incident_authority_transition import (
    commit_transition,
)
from livespec_orchestrator_beads_fabro.effects._incident_entry_writer import (
    require_current_generation,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient

__all__: list[str] = [
    "DEFERRED_PROOF",
    "RECOVERY_WRITER",
    "REGRESSION_SURFACES",
    "Correction",
    "Finding",
    "FindingDisposition",
    "RecoveryEntry",
    "RevertReceipt",
    "UnmergedFailure",
    "classify_finding",
    "enter_corrected_attempt",
    "enter_unmerged_correction",
    "record_deferred_finding",
    "record_revert_receipt",
    "recovery_attempts",
    "reopen_for_regression",
    "require_repayment_current",
    "retained_failures",
]

RECOVERY_WRITER = "incident-regression-recovery"
_REOPEN_INTENT = "incident-regression-reopen"
_QUERY_FIELDS = ("attempt_id", "phase", "operation_id", "generation", "owner")
_FINDING_KEYS = frozenset(f.name for f in fields(Finding))
# Records whose `retained_failures` the item keeps to terminal evidence: a
# recovery request's attributed failure, and every corrected attempt's own.
_FAILURE_KINDS = ("recovery-request", "corrected-attempt")


@dataclass(frozen=True, kw_only=True)
class RecoveryEntry:
    """A recorded recovery generation and the lifecycle state it pairs with."""

    reading: IncidentReading
    operation_id: str
    lifecycle_state: str


def _refuse(*, code: str, detail: str) -> AuthorityRefusal:
    return AuthorityRefusal(code=code, detail=detail)


def _records(*, client: BeadsClient, item_id: str, kinds: tuple[str, ...]) -> list[dict[str, Any]]:
    """Distinct retained recovery records of the given kinds on this item, in append order."""
    seen: dict[str, dict[str, Any]] = {}
    for row in client.list_comments(issue_id=item_id):
        text = row.get("text")
        if not isinstance(text, str) or not text.startswith(RECOVERY_MARKER):
            continue
        record = parse_json(text=text[len(RECOVERY_MARKER) :])
        if isinstance(record, dict):
            body = cast("dict[str, Any]", record)
            if body.get("item_id") == item_id and body.get("kind") in kinds:
                _ = seen.setdefault(text, body)
    return list(seen.values())


def retained_failures(*, client: BeadsClient, item_id: str) -> tuple[Finding, ...]:
    """Every failure a recovery request or corrected attempt retained, kept to terminal evidence."""
    found: dict[Finding, None] = {}
    for record in _records(client=client, item_id=item_id, kinds=_FAILURE_KINDS):
        failures = record.get("retained_failures")
        for raw in cast("list[object]", failures) if isinstance(failures, list) else []:
            if isinstance(raw, dict) and frozenset(cast("dict[str, Any]", raw)) == _FINDING_KEYS:
                found.setdefault(Finding(**cast("dict[str, Any]", raw)), None)
    return tuple(found)


def recovery_attempts(*, client: BeadsClient, item_id: str) -> int:
    """Recovery requests recorded on the item: an account apart from rework budgets."""
    return len(_records(client=client, item_id=item_id, kinds=("recovery-request",)))


def _append(*, client: BeadsClient, item_id: str, record: dict[str, Any]) -> None:
    body = recovery_comment(record=record)
    if body not in {row.get("text") for row in client.list_comments(issue_id=item_id)}:
        client.add_comment(issue_id=item_id, body=body)


def _commit(
    *, client: BeadsClient, reading: IncidentReading, plan: RecoveryPlan | AuthorityRefusal
) -> RecoveryEntry | AuthorityRefusal:
    """Commit the planned generation (an exact retry recovers it) and retain its record."""
    if isinstance(plan, AuthorityRefusal):
        return plan
    committed = commit_transition(client=client, observed=reading, successor=plan.attempt)
    if isinstance(committed, AuthorityRefusal):
        return committed
    _append(client=client, item_id=plan.attempt.item_id, record=plan.record)
    return RecoveryEntry(
        reading=committed, operation_id=plan.operation_id, lifecycle_state=plan.lifecycle_state
    )


def _verified(
    *, client: BeadsClient, attempt: IncidentAttempt
) -> IncidentAttempt | AuthorityRefusal:
    """The attributed attempt exactly as the chain retained it; caller bytes are no authority."""
    found = read_authority(
        client=client,
        repository=attempt.repository,
        item_id=attempt.item_id,
        query={key: getattr(attempt, key) for key in _QUERY_FIELDS},
        historical=True,
    )
    if isinstance(found, AuthorityRefusal):
        return found
    if found.attempt != attempt:
        return _refuse(code="incident-reopen-attribution-mismatch", detail=attempt.attempt_id)
    return found.attempt


def _own_or_stale(
    *, client: BeadsClient, reading: IncidentReading, plan: RecoveryPlan | AuthorityRefusal
) -> RecoveryPlan | AuthorityRefusal:
    """A stale observation is refused unless the chain already retains this exact reopen.

    The reopen records its generation before it moves the claim, so a call
    interrupted between the two leaves its observation stale. The same
    identity plans the same successor; when the chain retains it byte for byte
    (same attempt, phase, operation, generation and owner), that generation is
    this reopen's own and the retry recovers it. Every other identity is stale.
    """
    if reading.is_current:
        return plan
    stale = _refuse(code="incident-reopen-stale-observation", detail=reading.attempt.item_id)
    if isinstance(plan, AuthorityRefusal):
        return stale
    own = _verified(client=client, attempt=plan.attempt)
    return stale if isinstance(own, AuthorityRefusal) else plan


def reopen_for_regression(
    *,
    client: BeadsClient,
    reading: IncidentReading,
    attributed: IncidentAttempt,
    finding: Finding,
    owner: str,
) -> RecoveryEntry | AuthorityRefusal:
    """Reopen the same item into a fenced `reverting` generation and request recovery.

    The generation is committed through the chain's conditional close, so a
    concurrent repayment step loses as a stale generation. The item then moves
    back to `active` under the incident owner through its claim token, the
    incident holder's stamp replacing the factory's so the superseded run's
    terminal, proof or cleanup write answers `claim-changed`. A repeated
    delivery recovers the recorded generation and record and writes nothing;
    one interrupted before its claim moved completes that move once, and of
    concurrent retries only one moves it while the rest return the recorded result.
    """
    verified = _verified(client=client, attempt=attributed)
    if isinstance(verified, AuthorityRefusal):
        return verified
    # Planned as if current: the same identity yields the successor it recorded.
    as_current = replace(reading, is_current=True)
    planned = plan_reopen(reading=as_current, attributed=verified, finding=finding, owner=owner)
    plan = _own_or_stale(client=client, reading=reading, plan=planned)
    entry = _commit(client=client, reading=reading, plan=plan)
    if isinstance(entry, AuthorityRefusal):
        return entry
    successor = entry.reading.attempt
    record = client.show_issue(issue_id=successor.item_id)
    held = incident_claim_decided(
        operation_id=successor.operation_id, generation=successor.generation, owner=owner
    )
    if held(record):
        return entry
    # The decision: this recovery is still the chain's current generation.
    current = require_current_generation(client=client, observed=entry.reading)
    if isinstance(current, AuthorityRefusal):
        return current
    result = change_claim(
        client=client,
        work_item_id=successor.item_id,
        writer=RECOVERY_WRITER,
        intent=_REOPEN_INTENT,
        claim_tokens=True,
        status=entry.lifecycle_state,
        assignee=owner,
        metadata=takeover_metadata(
            operation_id=successor.operation_id,
            generation=successor.generation,
            owner=owner,
            principal=owner,
            root_token_id=current.committed_token_id,
            prior=prior_claim(record=record),
        ),
        # Bound to the row this retry decided on: a rival that moved the claim first wins.
        still_as_decided=lambda row: prior_claim(record=row) == prior_claim(record=record),
    )
    if result.outcome == "applied" or held(client.show_issue(issue_id=successor.item_id)):
        return entry
    return _refuse(code="incident-reopen-lifecycle-refused", detail=result.outcome)


def require_repayment_current(
    *,
    client: BeadsClient,
    observed: IncidentReading,
    effect: Literal["merge", "proof", "closure"],
) -> IncidentReading | AuthorityRefusal:
    """The gate a repayment merge, proof or closure takes right before its side effect.

    A repayment generation the chain has moved past (a recovery reopened the
    item, or a later step superseded it) is refused by name, so stale cleanup
    cannot merge, prove or close against the corrected incident attempt.
    """
    current = require_current_generation(client=client, observed=observed)
    if not isinstance(current, AuthorityRefusal):
        return current
    if current.code != GENERATION_STALE or observed.attempt.phase not in REPAYMENT_PHASES:
        return current
    attempt = observed.attempt
    return _refuse(
        code="incident-repayment-superseded",
        detail=(
            f"{attempt.item_id}: {effect} refused; repayment {attempt.attempt_id} "
            f"generation {attempt.generation} is superseded"
        ),
    )


def record_deferred_finding(
    *, client: BeadsClient, reading: IncidentReading, finding: Finding
) -> RecoveryEntry | AuthorityRefusal:
    """Owe a deferred-proof-only defect in the live repayment pull request; master stays."""
    return _commit(
        client=client, reading=reading, plan=plan_deferred_finding(reading=reading, finding=finding)
    )


def record_revert_receipt(
    *, client: BeadsClient, reading: IncidentReading, receipt: RevertReceipt
) -> RecoveryEntry | AuthorityRefusal:
    """Reconcile the controller's revert receipt: `reverting` becomes `collecting-failures`."""
    return _commit(
        client=client, reading=reading, plan=plan_revert_receipt(reading=reading, receipt=receipt)
    )


def enter_corrected_attempt(
    *, client: BeadsClient, reading: IncidentReading, correction: Correction, target_ref: str
) -> RecoveryEntry | AuthorityRefusal:
    """Open a corrected `repair` attempt that keeps the original failures and owes repayment."""
    retained = retained_failures(client=client, item_id=reading.attempt.item_id)
    plan = plan_corrected_attempt(
        reading=reading, retained=retained, correction=correction, target_ref=target_ref
    )
    return _commit(client=client, reading=reading, plan=plan)


def enter_unmerged_correction(
    *,
    client: BeadsClient,
    reading: IncidentReading,
    observed: UnmergedFailure,
    correction: Correction,
    target_ref: str,
) -> RecoveryEntry | AuthorityRefusal:
    """Open a corrected `repair` after the bound PR closed unmerged on a failed fast check.

    `observed` is what the forge reported; the planner refuses by name unless it
    shows the bound PR closed unmerged at the carrier head and the named run
    failed on that head. The failed run joins the item's retained failures.
    """
    prior = retained_failures(client=client, item_id=reading.attempt.item_id)
    plan = plan_unmerged_correction(
        reading=reading,
        observed=observed,
        prior=prior,
        correction=correction,
        target_ref=target_ref,
    )
    return _commit(client=client, reading=reading, plan=plan)
