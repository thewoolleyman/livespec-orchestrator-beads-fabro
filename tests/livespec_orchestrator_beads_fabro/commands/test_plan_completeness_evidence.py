"""The completeness-review evidence record: what it carries, and what the grade refuses.

Moved here with the record itself, which was split out of `_plan_archive_review`
by cohesion once the independence check gained a real comparand. The cases that
matter are the ones the old constant-comparand predicate could not have: evidence
authored by the archiving party, and evidence authored by anybody else, graded
against ONE archiving identity.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    BeadsClient,
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._plan_archive_gates import (
    PlanArchiveRefusedError,
)
from livespec_orchestrator_beads_fabro.commands._plan_completeness_evidence import (
    CompletenessReviewEvidenceFields,
    completeness_review_evidence,
    record_completeness_review_evidence,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

_ARCHIVER = "archiving-session"
_SESSION_VAR = "CLAUDE_CODE_SESSION_ID"


@dataclass(frozen=True, kw_only=True)
class _UnavailableForge:
    """A `CommandRunner` whose forge-login read never resolves a login."""

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        del argv, cwd, timeout_seconds, env, stdin
        return CommandResult(exit_code=1, stdout="", stderr="gh: command not found")


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


def _record(
    *,
    evidence_id: str,
    reviewer: str,
    coverage: bool = True,
    reviewed_child_ids: tuple[str, ...] = (),
) -> None:
    """Record evidence as the session whose own id is `reviewer`.

    The identity reaches the record through the reviewing session's ENVIRONMENT,
    which is the only route there is: the primitive takes no field a caller could
    put a name in. The reviewed child set, by contrast, IS a caller field — only
    the reviewer knows what it read — and it defaults to the empty set here
    because this epic carries no children, which is the scope these records cover.
    """
    record_completeness_review_evidence(
        config=_config(),
        epic_id="bd-ib-epic",
        env={_SESSION_VAR: reviewer},
        evidence_id=evidence_id,
        reviewed_child_ids=reviewed_child_ids,
        separate_reviewer=True,
        attests_complete_requirement_coverage=coverage,
        body="All research requirements and deferrals have ledger carriers.",
        now="2026-10-08T02:00:00Z",
    )


def test_the_record_carries_the_reviewers_own_computed_identity() -> None:
    """The reviewer identity is COMPUTED from the reviewing session, never named.

    The payload-grammar assertion is the load-bearing half. An identity a caller
    could NAME is one a caller could RENAME, so a self-review would be one keyword
    away from passing and the independence refusal would be theatre — which is
    exactly why the proof-record surfaces accept no identity parameter either.
    Removing the field is what makes the refusal real, not merely stricter.
    """
    assert "reviewer_identity" not in CompletenessReviewEvidenceFields.__annotations__
    _epic()

    _record(evidence_id="review-evidence-1", reviewer="reviewing-session")

    [comment] = _fake().list_comments(issue_id="bd-ib-epic")
    assert "reviewer-identity: reviewing-session\n" in comment["text"]
    assert "separate-reviewer: true\n" in comment["text"]


def test_an_unresolved_reviewer_identity_records_nothing_at_all() -> None:
    """Fail-closed BEFORE the append, because a record comment cannot be edited later.

    An evidence comment naming no reviewer would sit on the timeline permanently,
    where the archive gate would read it, decline to count it, and report a
    refusal whose cause the reviewer could not see from its own successful write.
    """
    _epic()

    with pytest.raises(PlanArchiveRefusedError) as refused:
        record_completeness_review_evidence(
            config=_config(),
            epic_id="bd-ib-epic",
            project_root=Path("/repo"),
            env={},
            runner=_UnavailableForge(),
            evidence_id="review-evidence-1",
            reviewed_child_ids=(),
            separate_reviewer=True,
            attests_complete_requirement_coverage=True,
            body="All research requirements and deferrals have ledger carriers.",
            now="2026-10-08T02:00:00Z",
        )

    assert "reviewing party" in str(refused.value)
    assert _fake().list_comments(issue_id="bd-ib-epic") == []


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
    _record(evidence_id="review-evidence-1", reviewer="reviewing-session")

    graded = completeness_review_evidence(
        client=_fake(),
        epic_id="bd-ib-epic",
        evidence_id="review-evidence-1",
        archive_identity=_ARCHIVER,
        current_child_ids=(),
    )

    assert graded.accepted_id == "review-evidence-1"
    assert graded.self_review_identity is None


def test_evidence_from_the_archiving_identity_is_a_self_review() -> None:
    """The discriminating half: the SAME record, authored by the party archiving.

    It differs from the accepted case in nothing but the reviewing session's own
    id, which is what makes the pair evidence about the comparison rather than
    about the comment's shape.
    """
    _epic()
    _record(evidence_id="review-evidence-1", reviewer=_ARCHIVER)

    graded = completeness_review_evidence(
        client=_fake(),
        epic_id="bd-ib-epic",
        evidence_id="review-evidence-1",
        archive_identity=_ARCHIVER,
        current_child_ids=(),
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
    _record(evidence_id="review-evidence-1", reviewer=_ARCHIVER)
    _record(evidence_id="review-evidence-1", reviewer="reviewing-session")

    graded = completeness_review_evidence(
        client=_fake(),
        epic_id="bd-ib-epic",
        evidence_id="review-evidence-1",
        archive_identity=_ARCHIVER,
        current_child_ids=(),
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
    _record(evidence_id="partial-review", reviewer="reviewing-session", coverage=False)

    for evidence_id in ("partial-review", "never-recorded"):
        graded = completeness_review_evidence(
            client=_fake(),
            epic_id="bd-ib-epic",
            evidence_id=evidence_id,
            archive_identity=_ARCHIVER,
            current_child_ids=(),
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
        current_child_ids=(),
    )

    assert graded.accepted_id is None
    assert graded.self_review_identity is None
