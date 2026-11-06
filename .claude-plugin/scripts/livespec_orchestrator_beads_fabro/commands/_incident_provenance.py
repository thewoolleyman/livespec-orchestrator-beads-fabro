"""Exact immutable evidence for an expedited incident carrier.

An incident receipt is trustworthy only after the incident-authority reader has
returned it from the retained ledger token chain.  This pure module deliberately
does not parse labels, environment variables, commit trailers, or sandbox
markers: those inputs may locate a candidate receipt, but cannot authorize it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._incident_authority_types import IncidentReading

__all__: list[str] = [
    "IncidentReceipt",
    "matches_receipt",
    "matching_incident_receipt",
    "permits_incident_exception",
    "receipt_from_authority_reading",
]


@dataclass(frozen=True, slots=True, kw_only=True)
class IncidentReceipt:
    """The immutable carrier identities needed by provenance consumers."""

    repository: str
    item_id: str
    phase: str
    pr_number: int
    head_sha: str
    landed_commits: tuple[str, ...]
    repayment_required: bool


def matches_receipt(
    *,
    receipt: IncidentReceipt,
    repository: str,
    pr_number: int,
    head_sha: str,
    landed_commits: tuple[str, ...],
) -> bool:
    """Whether a trusted receipt authorizes exactly this carrier, and no other."""
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
    return receipt.phase in {"repair", "reverting"} and matches_receipt(
        receipt=receipt,
        repository=repository,
        pr_number=pr_number,
        head_sha=head_sha,
        landed_commits=landed_commits,
    )


def matching_incident_receipt(
    *,
    receipts: tuple[IncidentReceipt, ...],
    repository: str | None,
    pr_number: int,
    head_sha: str,
    landed_commits: tuple[str, ...],
) -> IncidentReceipt | None:
    """Return the one receipt that permits this exact carrier, if any."""
    return next(
        (
            receipt
            for receipt in receipts
            if receipt.phase in {"repair", "reverting"}
            and receipt.repayment_required
            and (repository is None or receipt.repository == repository)
            and receipt.pr_number == pr_number
            and receipt.head_sha == head_sha
            and receipt.landed_commits == landed_commits
        ),
        None,
    )


def receipt_from_authority_reading(*, reading: IncidentReading) -> IncidentReceipt | None:
    """Reduce a retained authority reading to an exact, repayable exception."""
    attempt = reading.attempt
    if (
        attempt.phase not in {"repair", "reverting"}
        or attempt.pr_number <= 0
        or not attempt.landed_commits
        or not attempt.repayment_required
    ):
        return None
    return IncidentReceipt(
        repository=attempt.repository,
        item_id=attempt.item_id,
        phase=attempt.phase,
        pr_number=attempt.pr_number,
        head_sha=attempt.head,
        landed_commits=attempt.landed_commits,
        repayment_required=attempt.repayment_required,
    )
