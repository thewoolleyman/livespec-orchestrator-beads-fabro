"""The pure scope-and-recency decisions behind the completeness leg's refusal.

The mirror of `_plan_completeness_recency`. The archive-driven cases — which is
where the defect `bd-ib-0pf5` records actually lived — are in
`test_plan_archive_completeness_recency.py`; these are the readings a well-formed
plan cannot reach from that end, plus the set algebra and the instant choice
stated on their own so a future reader can see which way each arm fails.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._plan_completeness_recency import (
    PlanChildStatus,
    StaleEvidenceReport,
    latest_status_instant,
    stale_evidence_detail,
    stale_evidence_report,
)

_EVIDENCE = "review-evidence-1"
_REVIEWED_AT = "2026-10-08T02:00:00Z"


def _child(*, child_id: str, instant: str | None) -> PlanChildStatus:
    return PlanChildStatus(child_id=child_id, status_instant=instant)


def _report(
    *,
    reviewed_child_ids: tuple[str, ...],
    children: tuple[PlanChildStatus, ...],
    reviewed_at: str = _REVIEWED_AT,
) -> StaleEvidenceReport | None:
    return stale_evidence_report(
        evidence_id=_EVIDENCE,
        reviewed_child_ids=reviewed_child_ids,
        reviewed_at=reviewed_at,
        children=children,
    )


def _detail(
    *,
    added: tuple[str, ...] = (),
    removed: tuple[str, ...] = (),
    outdated_child_id: str | None = None,
    outdated_child_instant: str | None = None,
) -> str:
    return stale_evidence_detail(
        report=StaleEvidenceReport(
            evidence_id=_EVIDENCE,
            added_child_ids=added,
            removed_child_ids=removed,
            outdated_child_id=outdated_child_id,
            outdated_child_instant=outdated_child_instant,
        )
    )


def test_the_latest_of_the_reported_instants_is_the_childs_status_instant() -> None:
    """Three fields, latest wins — and the latest is not always the close.

    `updated_at` moves on the record's last mutation, so a child re-touched after
    its close reports a later instant there than in `closed_at`. Taking the latest
    OVER-reports staleness, which is the direction a terminal gate must fail in:
    a stale report costs one fresh review, a missed one archives a plan nobody
    reviewed and nothing re-examines a disposed thread.
    """
    assert (
        latest_status_instant(
            record={
                "created_at": "2026-10-08T00:00:00Z",
                "closed_at": "2026-10-08T01:00:00Z",
                "updated_at": "2026-10-08T03:00:00Z",
            }
        )
        == "2026-10-08T03:00:00Z"
    )
    assert latest_status_instant(record={"closed_at": "2026-10-08T01:00:00Z"}) == (
        "2026-10-08T01:00:00Z"
    )


def test_an_unreported_instant_reads_as_absent_rather_than_as_the_beginning_of_time() -> None:
    """`None`, never the empty string, and never a non-string field's value.

    The empty string compares as earlier than every real instant, so a record
    whose instants are unreadable would silently read as one that last moved
    before the beginning of time — the answer that makes the gate pass. A `bd`
    record is `omitempty`-sparse, so an absent field is the ordinary shape of a
    value nobody wrote, and a blank or non-string one is the shape of a value
    written badly; neither can date a status change.
    """
    assert latest_status_instant(record={}) is None
    assert latest_status_instant(record={"created_at": None, "updated_at": 17}) is None
    assert latest_status_instant(record={"created_at": "   "}) is None


def test_a_review_naming_the_current_set_and_postdating_it_is_not_stale() -> None:
    """Order and repetition are spellings of a set, not differences in scope.

    A reviewer that lists its scope in a different order, or names one child
    twice, reviewed the same children; a report keyed on the literal list would
    refuse that and read exactly like a genuine drift.
    """
    assert (
        _report(
            reviewed_child_ids=("bd-ib-b", "bd-ib-a", "bd-ib-a"),
            children=(
                _child(child_id="bd-ib-a", instant="2026-10-08T00:00:00Z"),
                _child(child_id="bd-ib-b", instant="2026-10-08T01:00:00Z"),
            ),
        )
        is None
    )


def test_an_empty_plan_reviewed_as_empty_is_not_stale() -> None:
    """A plan with no linked members is covered by a review that names none.

    This is the arm a naive "evidence must name something" rule would break: an
    epic whose requirements all live in its own description carries no children,
    and refusing its review would make such a plan unarchivable.
    """
    assert _report(reviewed_child_ids=(), children=()) is None


def test_children_added_since_the_review_are_reported_as_added() -> None:
    """The measured shape of the defect: a review that predates later children.

    `bd-ib-l3nptz` grew seven children after its 2026-08-17 evidence was written,
    and that evidence still validated. Every one of them is work the reviewer
    never saw, so every one is named.
    """
    report = _report(
        reviewed_child_ids=("bd-ib-a",),
        children=(
            _child(child_id="bd-ib-c", instant="2026-10-08T00:00:00Z"),
            _child(child_id="bd-ib-a", instant="2026-10-08T00:00:00Z"),
            _child(child_id="bd-ib-b", instant="2026-10-08T00:00:00Z"),
        ),
    )

    assert report is not None
    assert report.evidence_id == _EVIDENCE
    assert report.added_child_ids == ("bd-ib-b", "bd-ib-c")
    assert report.removed_child_ids == ()
    assert report.outdated_child_id is None


def test_children_removed_since_the_review_are_reported_as_removed() -> None:
    """The mirror arm, which is a different omission rather than the same one.

    A child the review counted and the plan no longer has is a requirement carrier
    that was re-parented or retired after the attestation was made, so the
    attestation covers a plan that no longer exists. Reporting it as merely
    "stale" would leave a reader unable to tell it from work nobody reviewed.
    """
    report = _report(
        reviewed_child_ids=("bd-ib-a", "bd-ib-gone"),
        children=(_child(child_id="bd-ib-a", instant="2026-10-08T00:00:00Z"),),
    )

    assert report is not None
    assert report.added_child_ids == ()
    assert report.removed_child_ids == ("bd-ib-gone",)


def test_the_most_recent_postdating_child_is_the_one_reported() -> None:
    """One name is what the refusal carries, so it is the one that matters most.

    The most recent change makes every earlier one moot: a reviewer sent back to
    re-read the plan as of the latest instant has covered the earlier ones by
    construction, while being pointed at the earliest would understate how far
    the record has drifted.
    """
    report = _report(
        reviewed_child_ids=("bd-ib-a", "bd-ib-b"),
        children=(
            _child(child_id="bd-ib-a", instant="2026-10-08T03:00:00Z"),
            _child(child_id="bd-ib-b", instant="2026-10-08T09:00:00Z"),
        ),
    )

    assert report is not None
    assert report.added_child_ids == ()
    assert report.removed_child_ids == ()
    assert report.outdated_child_id == "bd-ib-b"
    assert report.outdated_child_instant == "2026-10-08T09:00:00Z"


def test_an_unreported_instant_outranks_a_merely_late_one() -> None:
    """The observation a reviewer most needs to see wins the single slot.

    A child whose record cannot date its latest status change is a stronger
    finding than one that changed late: the late one tells the reviewer exactly
    what to re-read, while the undated one says the ledger cannot answer the
    question at all. Ties among undated children resolve by id so the refusal is
    deterministic.
    """
    report = _report(
        reviewed_child_ids=("bd-ib-a", "bd-ib-b", "bd-ib-c"),
        children=(
            _child(child_id="bd-ib-a", instant="2026-10-08T09:00:00Z"),
            _child(child_id="bd-ib-b", instant=None),
            _child(child_id="bd-ib-c", instant=None),
        ),
    )

    assert report is not None
    assert report.outdated_child_id == "bd-ib-c"
    assert report.outdated_child_instant is None


def test_the_detail_renders_only_the_clauses_that_apply() -> None:
    """A clause is present only when its own finding is, and never empty-handed.

    An "added" clause with nothing after it reads as a rendering bug at exactly
    the moment an operator is trying to work out what to re-review, and the
    single-finding cases are the common ones: a plan usually grows children after
    a review rather than losing them or having one move underneath it.
    """
    added_only = _detail(added=("bd-ib-new",))
    removed_only = _detail(removed=("bd-ib-gone",))

    assert added_only == (
        f"completeness-review evidence {_EVIDENCE} is stale:"
        " children added since the review bd-ib-new"
    )
    assert "removed" not in added_only
    assert "added" not in removed_only
    assert "bd-ib-gone" in removed_only


def test_the_detail_distinguishes_a_late_change_from_an_undatable_one() -> None:
    """The remedy is one fresh review either way; the CAUSE is not the same.

    A measured instant is quoted, because the reviewer can see at a glance what
    it missed. An unreported one says so outright rather than quoting nothing: a
    clause implying a measured instant would send an operator looking for a
    change that may never have happened.
    """
    late = _detail(outdated_child_id="bd-ib-late", outdated_child_instant="2026-10-08T09:00:00Z")
    undatable = _detail(outdated_child_id="bd-ib-undated")
    with_drift = _detail(
        added=("bd-ib-new",),
        removed=("bd-ib-gone",),
        outdated_child_id="bd-ib-late",
        outdated_child_instant="2026-10-08T09:00:00Z",
    )

    assert late.endswith(
        "child bd-ib-late last changed status at 2026-10-08T09:00:00Z, after the review"
    )
    assert undatable.endswith(
        "child bd-ib-undated reports no readable status instant,"
        " so the review cannot be shown to postdate its latest status change"
    )
    # All three findings ride one detail, in the order the clauses are built, so a
    # record that drifted in every way reports every way it drifted.
    assert with_drift.count(";") == 2
