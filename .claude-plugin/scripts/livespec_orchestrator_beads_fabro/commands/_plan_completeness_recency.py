"""Whether a recorded completeness review still covers the plan it attested to.

Work-item `bd-ib-0pf5`. The completeness leg used to field-match an evidence
comment's id, its reviewer identity and its two self-declared booleans, and
nothing else — so a comment of ANY age satisfied the archive gate forever.
Measured on plan epic `bd-ib-l3nptz` on 2026-08-22 by execution against the live
store: evidence recorded 2026-08-17 still validated five days later, after seven
further children had landed across four repositories, none of which its reviewer
ever saw. The archive that would have passed on it was averted by a session
recognising the trap, not by the gate.

This module is the SCOPE BINDING. It is PURE: the ledger read lives in
`_plan_archive_review`, which owns plan membership, and the grade that calls this
one lives in `_plan_completeness_evidence`, which owns the record.

WHAT BINDS THE EVIDENCE TO ITS SCOPE. A review names the child work-item ids it
covered, and the gate compares that named set against the epic's CURRENT one.
That comparison is the one thing an evidence record cannot talk its way past: the
two attestations it carries are self-declared and cross-checked against nothing,
and the ratified clause requires the reviewer to compare every requirement
against the COMPLETE child set — which an evidence record can only attest for the
child set it actually saw.

THE SET THE REVIEWER IS HANDED IS THE SET THE GATE COMPARES AGAINST, and that is
structural rather than conventional: `archive_thread` passes the very
`ArchiveCompletenessReviewRequest.child_ids` it commissioned the review with into
this grade. Two independently-derived readings of "the plan's child set" would
let a reviewer name exactly what it was given and still be refused.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__: list[str] = [
    "StaleEvidenceReport",
    "stale_evidence_detail",
    "stale_evidence_report",
]

_ADDED_CLAUSE = "children added since the review"
_REMOVED_CLAUSE = "children removed since the review"


@dataclass(frozen=True, kw_only=True)
class StaleEvidenceReport:
    """Why one otherwise-valid evidence record no longer covers this plan.

    The two id sets ride separately rather than as one "differs" flag because
    they describe different omissions: a child ADDED since the review is work
    nobody reviewed, while a child REMOVED is a carrier the review counted that
    the plan no longer has. Both make the attestation untrue of the plan being
    archived, and a reader told only that the evidence is stale cannot tell which
    one happened, nor which children to look at.
    """

    evidence_id: str
    added_child_ids: tuple[str, ...]
    removed_child_ids: tuple[str, ...]


def stale_evidence_report(
    *,
    evidence_id: str,
    reviewed_child_ids: tuple[str, ...],
    current_child_ids: tuple[str, ...],
) -> StaleEvidenceReport | None:
    """How this record fails to cover `current_child_ids`, or `None` when it covers them.

    Compared as SETS, so neither the order a reviewer lists its scope in nor a
    repeated id changes the verdict: the question is which children the review
    covered, and a list is only how that set is spelled on the timeline.
    """
    current = frozenset(current_child_ids)
    reviewed = frozenset(reviewed_child_ids)
    added = tuple(sorted(current - reviewed))
    removed = tuple(sorted(reviewed - current))
    if not added and not removed:
        return None
    return StaleEvidenceReport(
        evidence_id=evidence_id,
        added_child_ids=added,
        removed_child_ids=removed,
    )


def stale_evidence_detail(*, report: StaleEvidenceReport) -> str:
    """One clause per way this record no longer covers the plan, naming every id.

    Only the ids that CHANGED are named. Listing the whole current child set would
    read as though the review had covered none of it, which points a reviewer at a
    far larger re-read than the refusal actually calls for; and the two clauses are
    labelled separately because an added child and a removed one prescribe
    different reading.
    """
    clauses = [
        f"{clause} {', '.join(child_ids)}"
        for clause, child_ids in (
            (_ADDED_CLAUSE, report.added_child_ids),
            (_REMOVED_CLAUSE, report.removed_child_ids),
        )
        if child_ids
    ]
    return f"completeness-review evidence {report.evidence_id} is stale: {'; '.join(clauses)}"
