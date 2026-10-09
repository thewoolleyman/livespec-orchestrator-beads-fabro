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
structural rather than conventional: `plan_child_statuses` is read ONCE and feeds
both the brief a fresh reviewer is commissioned with and the grade a recorded
review is held to. Two independently-derived readings of "the plan's child set"
would let a reviewer name exactly what it was given and still be refused.

AND THE SCOPE LIST IS SELF-DECLARED, which is why the set test is not the whole
binding. It sits beside `separate-reviewer` and
`attests-complete-requirement-coverage` in the same comment, written by the same
party, so a record that simply names the right ids satisfies it. The second
measurement is the one its author does not control: each child's own STATUS
INSTANT, read off the ledger record, compared against the instant the review was
written at. A review that predates a child's latest status change did not read
the plan as it now stands, whatever its scope list claims.

WHICH INSTANT COUNTS AS A CHILD'S STATUS CHANGE. A `bd` record reports up to
three and the LATEST of them is taken: `created_at` is the transition into the
record's initial status and the one instant every record carries (measured
523/523 on the `livespec-dev-tooling` tenant), `closed_at` is the close
transition (298/523), and `updated_at` is the record's last mutation, which every
status write moves (523/523). Taking the latest OVER-reports rather than
under-reports, because `updated_at` also moves on a mutation that changed no
status — and over-reporting is the direction a terminal gate must fail in: a
stale report costs one fresh review, while a missed one archives a plan nobody
has reviewed and nothing re-examines a disposed thread.

A CHILD REPORTING NO READABLE INSTANT PLACES NO FLOOR, which is the one point
here that does not fail closed, so the reason is recorded rather than left to be
re-litigated. The usual argument applies everywhere else: a gauge that passes when
it cannot observe its input turns a refusal into a pass. It does not bite here
because the MEMBERSHIP leg reads no instant at all and binds every current child
unconditionally — so an unreadable instant can hide only a state change inside a
set that is already being compared, never a child appearing or disappearing. And
the alternative was measured: treating it as a finding named the undatable child
while one that demonstrably changed late sat beside it, and left a plan carrying
such a member unarchivable, because no review can postdate a change the ledger
declines to date.

THE COMPARISON IS LEXICOGRAPHIC, for the reason `_plan_close_proof` records about
the same class of value: ISO-8601 instants sort lexicographically, and parsing to
a datetime would add an unparseable-input failure mode whose only honest answer is
the one the raw comparison already gives. A review record carrying no readable
timestamp therefore compares as earlier than every instant, which is the
fail-closed direction — and note the asymmetry with the paragraph above: an
unreadable instant on the REVIEW side refuses, because the review's own record is
the thing being graded, while one on a CHILD side does not, because the set leg
already binds that child.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__: list[str] = [
    "OutdatedPlanChild",
    "PlanChildStatus",
    "StaleEvidenceReport",
    "latest_status_instant",
    "stale_evidence_detail",
    "stale_evidence_report",
]

_ADDED_CLAUSE = "children added since the review"
_REMOVED_CLAUSE = "children removed since the review"
# The record fields a status transition can be read from, latest wins.
_STATUS_INSTANT_FIELDS: tuple[str, ...] = ("created_at", "updated_at", "closed_at")


@dataclass(frozen=True, kw_only=True)
class PlanChildStatus:
    """One current plan member, with the latest status instant its record reports.

    `status_instant` is OPTIONAL because a record can report none, and an absent
    instant is not the same observation as an early one: it says the ledger cannot
    show when this child last moved. Such a child places no recency floor — see
    `_outdated_child` for why that is not the fail-open hole it looks like — but it
    is still a full member of the set the membership leg compares.
    """

    child_id: str
    status_instant: str | None


@dataclass(frozen=True, kw_only=True)
class OutdatedPlanChild:
    """A child whose latest status change postdates the review, and when it was.

    A PAIR rather than two optional fields on the report, so the id and the
    instant cannot be set apart: a report naming a child with no instant would
    render "last changed status at None", and one carrying an instant with no
    child would name nothing to go and re-read.
    """

    child_id: str
    status_instant: str


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
    outdated_child: OutdatedPlanChild | None


def latest_status_instant(*, record: Mapping[str, object]) -> str | None:
    """The latest status instant this record reports, or `None` when it reports none.

    `None` rather than an empty string, because the empty string compares as
    earlier than every real instant — so a record whose instants are unreadable
    would silently read as one that last moved before the beginning of time, which
    is the answer that makes the gate pass.
    """
    reported = tuple(
        instant
        for field in _STATUS_INSTANT_FIELDS
        if isinstance(value := record.get(field), str) and (instant := value.strip())
    )
    return max(reported) if reported else None


def stale_evidence_report(
    *,
    evidence_id: str,
    reviewed_child_ids: tuple[str, ...],
    reviewed_at: str,
    children: tuple[PlanChildStatus, ...],
) -> StaleEvidenceReport | None:
    """How this record fails to cover `children`, or `None` when it covers them.

    The membership is compared as SETS, so neither the order a reviewer lists its
    scope in nor a repeated id changes the verdict: the question is which children
    the review covered, and a list is only how that set is spelled on the timeline.
    """
    current = frozenset(child.child_id for child in children)
    reviewed = frozenset(reviewed_child_ids)
    added = tuple(sorted(current - reviewed))
    removed = tuple(sorted(reviewed - current))
    outdated = _outdated_child(reviewed_at=reviewed_at, children=children)
    if not added and not removed and outdated is None:
        return None
    return StaleEvidenceReport(
        evidence_id=evidence_id,
        added_child_ids=added,
        removed_child_ids=removed,
        outdated_child=outdated,
    )


def _outdated_child(
    *,
    reviewed_at: str,
    children: tuple[PlanChildStatus, ...],
) -> OutdatedPlanChild | None:
    """The current child whose latest status change postdates this review, if any.

    A child reporting NO readable instant is SKIPPED rather than treated as a
    finding, and that is the one place this leg deliberately does not fail closed.
    The usual argument would apply — a gauge that passes when it cannot observe
    its input turns a refusal into a pass — but it does not bite here, because the
    MEMBERSHIP leg beside this one reads no instant at all and binds every current
    child unconditionally. So an unreadable instant cannot hide a child appearing
    or disappearing; it can hide only a state change inside a membership set that
    is already being compared.

    What treating it as a finding DID cost is concrete: it named the undatable
    child while one that demonstrably changed late sat beside it, and it left a
    plan carrying such a member unarchivable, since no review can postdate a
    change the ledger declines to date.

    The LATEST qualifying child is reported rather than the first found, because
    one name is what the refusal carries and the most recent change is the one
    that makes every earlier one moot: a reviewer sent back to re-read the plan as
    of that instant has covered the earlier ones by construction.
    """
    postdating = tuple(
        OutdatedPlanChild(child_id=child.child_id, status_instant=instant)
        for child in children
        if (instant := child.status_instant) is not None and instant > reviewed_at.strip()
    )
    if not postdating:
        return None
    return max(postdating, key=lambda child: (child.status_instant, child.child_id))


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
    if (outdated := report.outdated_child) is not None:
        changed_at = f"last changed status at {outdated.status_instant}, after the review"
        clauses.append(f"child {outdated.child_id} {changed_at}")
    return f"completeness-review evidence {report.evidence_id} is stale: {'; '.join(clauses)}"
