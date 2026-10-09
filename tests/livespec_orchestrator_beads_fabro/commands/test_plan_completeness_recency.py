"""The pure scope decision behind the completeness leg's staleness refusal.

The mirror of `_plan_completeness_recency`. The archive-driven cases — which is
where the defect `bd-ib-0pf5` records actually lived — are in
`test_plan_archive_completeness_recency.py`; these are the decisions a
well-formed plan cannot reach from that end, plus the set algebra stated on its
own so a future reader can see which way each arm fails.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._plan_completeness_recency import (
    stale_evidence_report,
)

_EVIDENCE = "review-evidence-1"


def test_a_review_naming_the_current_set_is_not_stale() -> None:
    """Order and repetition are spellings of a set, not differences in scope.

    A reviewer that lists its scope in a different order, or names one child
    twice, reviewed the same children; a report keyed on the literal list would
    refuse that and read exactly like a genuine drift.
    """
    assert (
        stale_evidence_report(
            evidence_id=_EVIDENCE,
            reviewed_child_ids=("bd-ib-b", "bd-ib-a", "bd-ib-a"),
            current_child_ids=("bd-ib-a", "bd-ib-b"),
        )
        is None
    )


def test_an_empty_plan_reviewed_as_empty_is_not_stale() -> None:
    """A plan with no linked members is covered by a review that names none.

    This is the arm a naive "evidence must name something" rule would break: an
    epic whose requirements all live in its own description carries no children,
    and refusing its review would make such a plan unarchivable.
    """
    assert (
        stale_evidence_report(
            evidence_id=_EVIDENCE,
            reviewed_child_ids=(),
            current_child_ids=(),
        )
        is None
    )


def test_children_added_since_the_review_are_reported_as_added() -> None:
    """The measured shape of the defect: a review that predates later children.

    `bd-ib-l3nptz` grew seven children after its 2026-08-17 evidence was written,
    and that evidence still validated. Every one of them is work the reviewer
    never saw, so every one is named.
    """
    report = stale_evidence_report(
        evidence_id=_EVIDENCE,
        reviewed_child_ids=("bd-ib-a",),
        current_child_ids=("bd-ib-c", "bd-ib-a", "bd-ib-b"),
    )

    assert report is not None
    assert report.evidence_id == _EVIDENCE
    assert report.added_child_ids == ("bd-ib-b", "bd-ib-c")
    assert report.removed_child_ids == ()


def test_children_removed_since_the_review_are_reported_as_removed() -> None:
    """The mirror arm, which is a different omission rather than the same one.

    A child the review counted and the plan no longer has is a requirement carrier
    that was re-parented or retired after the attestation was made, so the
    attestation covers a plan that no longer exists. Reporting it as merely
    "stale" would leave a reader unable to tell it from work nobody reviewed.
    """
    report = stale_evidence_report(
        evidence_id=_EVIDENCE,
        reviewed_child_ids=("bd-ib-a", "bd-ib-gone"),
        current_child_ids=("bd-ib-a",),
    )

    assert report is not None
    assert report.added_child_ids == ()
    assert report.removed_child_ids == ("bd-ib-gone",)


def test_a_review_of_a_wholly_different_set_reports_both_halves() -> None:
    report = stale_evidence_report(
        evidence_id=_EVIDENCE,
        reviewed_child_ids=("bd-ib-old",),
        current_child_ids=("bd-ib-new",),
    )

    assert report is not None
    assert report.added_child_ids == ("bd-ib-new",)
    assert report.removed_child_ids == ("bd-ib-old",)
