"""Exact immutable evidence for an expedited incident carrier.

An incident receipt is trustworthy only after the incident-authority reader has
returned it from the retained ledger token chain.  This pure module deliberately
does not parse labels, environment variables, commit trailers, or sandbox
markers: those inputs may locate a candidate receipt, but cannot authorize it.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__: list[str] = ["IncidentReceipt", "matches_receipt"]


@dataclass(frozen=True, slots=True, kw_only=True)
class IncidentReceipt:
    """The immutable carrier identities needed by provenance consumers."""

    repository: str
    item_id: str
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
