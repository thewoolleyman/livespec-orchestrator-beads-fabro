"""The completeness-review evidence record: what the grade counts, and what it refuses.

Moved here with the record itself, which was split out of `_plan_archive_review`
by cohesion once the independence check gained a real comparand. The cases that
matter are the ones the old constant-comparand predicate could not have: evidence
authored by the archiving party, and evidence authored by anybody else, graded
against ONE archiving identity.
"""

from __future__ import annotations

from typing import cast

from livespec_orchestrator_beads_fabro._beads_client import (
    BeadsClient,
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands._plan_completeness_evidence import (
    completeness_review_evidence,
    record_completeness_review_evidence,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

_ARCHIVER = "archiving-session"


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _fake() -> FakeBeadsClient:
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    return client


def _epic() -> None:
    reset_fake_singleton()
    _ = _fake().create_issue(
        draft=IssueDraft(
            issue_id="bd-ib-epic",
            issue_type="epic",
            title="epic",
            description="plan epic",
            assignee=None,
            created_at="2026-10-08T00:00:00Z",
            parent_id=None,
            metadata={"rank": "a1"},
            labels=["origin:freeform"],
        )
    )


def _record(*, evidence_id: str, reviewer_identity: str, coverage: bool = True) -> None:
    record_completeness_review_evidence(
        config=_config(),
        epic_id="bd-ib-epic",
        evidence_id=evidence_id,
        reviewer_identity=reviewer_identity,
        separate_reviewer=True,
        attests_complete_requirement_coverage=coverage,
        body="All research requirements and deferrals have ledger carriers.",
        now="2026-10-08T02:00:00Z",
    )


def test_evidence_from_a_different_identity_is_accepted() -> None:
    """The noise cases are seeded alongside, because each must be SKIPPED not matched.

    An unrelated comment and an evidence comment with a malformed header both have
    to fall through to the real record rather than short-circuit the scan.
    """
    _epic()
    _fake().seed_comment(issue_id="bd-ib-epic", text="ordinary note")
    _fake().seed_comment(
        issue_id="bd-ib-epic",
        text="plan-completeness-review-evidence\nmalformed\n\nbody",
    )
    _record(evidence_id="review-evidence-1", reviewer_identity="reviewing-session")

    graded = completeness_review_evidence(
        client=_fake(),
        epic_id="bd-ib-epic",
        evidence_id="review-evidence-1",
        archive_identity=_ARCHIVER,
    )

    assert graded.accepted_id == "review-evidence-1"
    assert graded.self_review_identity is None


def test_evidence_from_the_archiving_identity_is_a_self_review() -> None:
    """The discriminating half: the SAME record, authored by the party archiving.

    It differs from the accepted case in nothing but its reviewer identity, which
    is what makes the pair evidence about the comparison rather than about the
    comment's shape.
    """
    _epic()
    _record(evidence_id="review-evidence-1", reviewer_identity=_ARCHIVER)

    graded = completeness_review_evidence(
        client=_fake(),
        epic_id="bd-ib-epic",
        evidence_id="review-evidence-1",
        archive_identity=_ARCHIVER,
    )

    assert graded.accepted_id is None
    assert graded.self_review_identity == _ARCHIVER


def test_a_self_review_does_not_hide_a_later_independent_comment_on_one_id() -> None:
    """A self-review is remembered, not returned on sight.

    Two comments can carry one evidence id — the archiving session's own
    attestation, then the review it eventually commissioned — and refusing on the
    first one read would refuse an archive the second one satisfies.
    """
    _epic()
    _record(evidence_id="review-evidence-1", reviewer_identity=_ARCHIVER)
    _record(evidence_id="review-evidence-1", reviewer_identity="reviewing-session")

    graded = completeness_review_evidence(
        client=_fake(),
        epic_id="bd-ib-epic",
        evidence_id="review-evidence-1",
        archive_identity=_ARCHIVER,
    )

    assert graded.accepted_id == "review-evidence-1"
    assert graded.self_review_identity is None


def test_withheld_coverage_and_an_unknown_id_are_neither_accepted_nor_a_self_review() -> None:
    """Both self-declared attestations gate the record, and neither is cross-checked.

    `separate-reviewer` and `attests-complete-requirement-coverage` are written by
    whoever authored the comment; the grade only establishes that they WERE
    claimed. A withheld claim therefore reads exactly like a missing record, which
    is correct: the remedy for both is the same recorded review.
    """
    _epic()
    _record(
        evidence_id="partial-review",
        reviewer_identity="reviewing-session",
        coverage=False,
    )

    for evidence_id in ("partial-review", "never-recorded"):
        graded = completeness_review_evidence(
            client=_fake(),
            epic_id="bd-ib-epic",
            evidence_id=evidence_id,
            archive_identity=_ARCHIVER,
        )

        assert graded.accepted_id is None
        assert graded.self_review_identity is None


class _NonStringCommentClient:
    def list_comments(self, *, issue_id: str) -> list[dict[str, object]]:
        return [{"issue_id": issue_id, "text": object()}]


def test_the_grade_ignores_non_string_comment_text() -> None:
    client = cast("BeadsClient", _NonStringCommentClient())

    graded = completeness_review_evidence(
        client=client,
        epic_id="bd-ib-epic",
        evidence_id="review-evidence-1",
        archive_identity=_ARCHIVER,
    )

    assert graded.accepted_id is None
    assert graded.self_review_identity is None
