"""Exact immutable evidence for an expedited incident carrier.

An incident receipt is trustworthy only after the canonical incident-authority
reader has returned it from the retained ledger token chain.  This pure module
deliberately does not parse labels, environment variables, commit trailers, or
sandbox markers: those inputs may locate a candidate item, but cannot authorize
it.  A receipt admits exactly one carrier — the repository, pull request, head
and complete landed commit set it recorded — and only while it is a repair,
its recorded merge or an emergency revert whose verification was honestly
deferred.  A carrier
the chain records in a repayment phase is normal factory work: it earns no
exception here, and the consumers refuse it the ordinary declared route too.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._incident_authority_types import (
        IncidentAttempt,
        IncidentReading,
    )

__all__: list[str] = [
    "EXCEPTION_PHASES",
    "IncidentReceipt",
    "matches_receipt",
    "matching_incident_receipt",
    "matching_repayment_carrier",
    "permits_incident_exception",
    "receipt_from_authority_reading",
    "receipts_from_history",
]

# The host-owned phases whose carrier may merge on a receipt instead of factory
# authorship: the expedited repair, the generation that records its merge (the
# first one a real chain's landed commits appear on) and the emergency revert.
EXCEPTION_PHASES = frozenset({"repair", "master-observation", "reverting"})
_REPAYMENT_PREFIX = "repayment"
_CLOSED_PHASE = "closed"
_DRILL_CLOSED_PHASE = "drill-closed"


@dataclass(frozen=True, slots=True, kw_only=True)
class IncidentReceipt:
    """The immutable carrier identities needed by provenance consumers.

    `repayment_required` is what the attempt itself recorded: its verification
    was deferred.  `repayment_outstanding` is what the whole retained chain
    says today: the incident has not reached its closed phase, so the normal
    factory repayment the receipt defers to is still owed.
    """

    repository: str
    item_id: str
    phase: str
    pr_number: int
    head_sha: str
    landed_commits: tuple[str, ...]
    repayment_required: bool
    repayment_outstanding: bool = True


def matches_receipt(
    *,
    receipt: IncidentReceipt,
    repository: str,
    pr_number: int,
    head_sha: str,
    landed_commits: tuple[str, ...],
) -> bool:
    """Whether a trusted receipt names exactly this carrier, and no other."""
    return (
        receipt.repayment_required
        and receipt.repository == repository
        and receipt.pr_number == pr_number
        and receipt.head_sha == head_sha
        and receipt.landed_commits == landed_commits
    )


def permits_incident_exception(
    *,
    receipt: IncidentReceipt,
    repository: str,
    pr_number: int,
    head_sha: str,
    landed_commits: tuple[str, ...],
) -> bool:
    """Permit only exact expedited repair/revert carriers, never repayment work."""
    return receipt.phase in EXCEPTION_PHASES and matches_receipt(
        receipt=receipt,
        repository=repository,
        pr_number=pr_number,
        head_sha=head_sha,
        landed_commits=landed_commits,
    )


def _exact(
    *,
    receipts: tuple[IncidentReceipt, ...],
    repository: str,
    pr_number: int,
    head_sha: str,
    landed_commits: tuple[str, ...],
) -> tuple[IncidentReceipt, ...]:
    """The receipts bound to exactly this repository, PR, head and landed set."""
    return tuple(
        receipt
        for receipt in receipts
        if receipt.repository == repository
        and receipt.pr_number == pr_number
        and receipt.head_sha == head_sha
        and receipt.landed_commits == landed_commits
    )


def matching_incident_receipt(
    *,
    receipts: tuple[IncidentReceipt, ...],
    repository: str,
    pr_number: int,
    head_sha: str,
    landed_commits: tuple[str, ...],
) -> IncidentReceipt | None:
    """The one repair or revert receipt that admits this exact carrier, if any."""
    return next(
        (
            receipt
            for receipt in _exact(
                receipts=receipts,
                repository=repository,
                pr_number=pr_number,
                head_sha=head_sha,
                landed_commits=landed_commits,
            )
            if receipt.phase in EXCEPTION_PHASES and receipt.repayment_required
        ),
        None,
    )


def matching_repayment_carrier(
    *,
    receipts: tuple[IncidentReceipt, ...],
    repository: str,
    pr_number: int,
    head_sha: str,
    landed_commits: tuple[str, ...],
) -> IncidentReceipt | None:
    """The retained normal-repayment carrier this exact pull request is, if the chain names one."""
    return next(
        (
            receipt
            for receipt in _exact(
                receipts=receipts,
                repository=repository,
                pr_number=pr_number,
                head_sha=head_sha,
                landed_commits=landed_commits,
            )
            if receipt.phase.startswith(_REPAYMENT_PREFIX)
        ),
        None,
    )


def _receipt(*, attempt: IncidentAttempt, repayment_outstanding: bool) -> IncidentReceipt | None:
    """A PR-bound attempt's receipt; an attempt with no PR or no landing binds nothing."""
    if attempt.pr_number <= 0 or not attempt.landed_commits:
        return None
    return IncidentReceipt(
        repository=attempt.repository,
        item_id=attempt.item_id,
        phase=attempt.phase,
        pr_number=attempt.pr_number,
        head_sha=attempt.head,
        landed_commits=attempt.landed_commits,
        repayment_required=attempt.repayment_required,
        repayment_outstanding=repayment_outstanding,
    )


def receipts_from_history(*, history: tuple[IncidentAttempt, ...]) -> tuple[IncidentReceipt, ...]:
    """Every PR-bound attempt of one retained chain, owing repayment until the chain closes."""
    outstanding = bool(history) and history[-1].phase not in (_CLOSED_PHASE, _DRILL_CLOSED_PHASE)
    receipts: list[IncidentReceipt] = []
    for attempt in history:
        receipt = _receipt(attempt=attempt, repayment_outstanding=outstanding)
        if receipt is not None:
            receipts.append(receipt)
    return tuple(receipts)


def receipt_from_authority_reading(*, reading: IncidentReading) -> IncidentReceipt | None:
    """Reduce one retained authority reading to an exact, repayable exception."""
    attempt = reading.attempt
    if attempt.phase not in EXCEPTION_PHASES or not attempt.repayment_required:
        return None
    return _receipt(attempt=attempt, repayment_outstanding=True)
