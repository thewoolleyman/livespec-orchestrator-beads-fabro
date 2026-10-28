"""Tests for the ledger record of one Definition-of-Done judgement.

"Judged again before dispatch" states two caps, and both are claims about a
WRITE that must NOT happen: the Dispatcher "MUST NOT run the judgement again or
append another comment for a reused verdict", and "the did-not-run record MUST
likewise be written at most once per distinct cause until the judgement next
runs". A record that cannot be read back is a cap that cannot hold, so these
tests assert the render and the parse as one round trip.

THE RESET CASE IS THE LOAD-BEARING ONE. The did-not-run cap runs "until the
judgement next runs", so a cause recorded BEFORE a verdict was taken must not
suppress the same cause recorded after it. A reader that simply scanned every
comment would suppress forever — the item would fall silent about a judgement
that has stopped working — and the suppression reads exactly like a judgement
that is running fine.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    JUDGEMENT_ADMITTED,
    JUDGEMENT_HELD,
    JUDGEMENT_UNAVAILABLE,
    DodJudgement,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_candidates import (
    CAUSE_INPUT_LIMIT,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_record import (
    STAGE_PRE_ADMISSION,
    STAGE_PRE_DISPATCH,
    GoverningHeadingReceipt,
    did_not_run_comment,
    recorded_did_not_run_causes,
    recorded_governing_heading,
    reusable_governing_heading,
    reusable_verdict,
    verdict_comment,
)
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading import (
    GoverningHeadingVerdict,
)
from livespec_orchestrator_beads_fabro.commands._spec_tree_condensation import CondensedClause

_DIGEST = "a" * 64
_OTHER_DIGEST = "b" * 64
_RUBRIC = "c" * 64
_OTHER_RUBRIC = "d" * 64
_FINDINGS = (
    "bd-ib-1: the References line omits the governing scenario; add that heading.",
    "bd-ib-1: assertion 2 asserts a test exists; restate it as the behaviour.",
)
_SELECTED = (CondensedClause(heading="## Selected", body="The selected body."),)
_NAMED = (CondensedClause(heading="## Named", body="The cited body."),)
_GOVERNING = GoverningHeadingVerdict(
    kind="stated",
    stated_by=("## Named",),
    selected_clauses=_SELECTED,
    named_clauses=_NAMED,
)


def _held_comment(*, digest: str = _DIGEST, rubric: str = _RUBRIC) -> str:
    return verdict_comment(
        item_id="bd-ib-1",
        stage=STAGE_PRE_ADMISSION,
        digest=digest,
        rubric_digest=rubric,
        judgement=DodJudgement(outcome=JUDGEMENT_HELD, findings=_FINDINGS),
    )


def test_a_held_verdict_comment_carries_every_finding_and_its_first_remedy() -> None:
    body = _held_comment()

    assert "livespec-dod-judgement" in body
    assert STAGE_PRE_ADMISSION in body
    for finding in _FINDINGS:
        assert finding in body
    # The hygiene listing names the verdict's first remedy, so the record has to
    # carry it rather than leave every reader to re-derive it.
    assert "add that heading." in body


def test_a_held_verdict_round_trips_back_through_the_reuse_read() -> None:
    reused = reusable_verdict(comments=(_held_comment(),), digest=_DIGEST, rubric_digest=_RUBRIC)

    assert reused is not None
    assert reused.outcome == JUDGEMENT_HELD
    assert reused.findings == _FINDINGS
    assert reused.first_remedy == "add that heading."


def test_an_admitted_verdict_round_trips_and_carries_no_finding() -> None:
    body = verdict_comment(
        item_id="bd-ib-1",
        stage=STAGE_PRE_DISPATCH,
        digest=_DIGEST,
        rubric_digest=_RUBRIC,
        judgement=DodJudgement(outcome=JUDGEMENT_ADMITTED),
    )

    reused = reusable_verdict(comments=(body,), digest=_DIGEST, rubric_digest=_RUBRIC)

    assert reused is not None
    assert reused.outcome == JUDGEMENT_ADMITTED
    assert reused.findings == ()
    assert reused.first_remedy is None


def test_a_verdict_comment_names_the_deciding_candidates_reported_input_usage() -> None:
    unreported = verdict_comment(
        item_id="bd-ib-1",
        stage=STAGE_PRE_DISPATCH,
        digest=_DIGEST,
        rubric_digest=_RUBRIC,
        judgement=DodJudgement(outcome=JUDGEMENT_ADMITTED),
    )
    reported = verdict_comment(
        item_id="bd-ib-1",
        stage=STAGE_PRE_DISPATCH,
        digest=_DIGEST,
        rubric_digest=_RUBRIC,
        judgement=DodJudgement(
            outcome=JUDGEMENT_ADMITTED,
            deciding_candidate="claude-acp:claude-opus-5",
            input_tokens=99_999,
            input_usage="complete",
        ),
    )

    assert "deciding-candidate-input-usage: unreported" in unreported
    assert "deciding-candidate: claude-acp:claude-opus-5" in reported
    assert "deciding-candidate-input-tokens: 99999" in reported
    assert "deciding-candidate-input-usage: complete" in reported


def test_a_chainless_verdict_comment_lists_every_bound_ended_candidate() -> None:
    """A taking the bound exhausted names no decider and lists each ended candidate.

    Both halves are one claim and neither is evidence alone: the absence says
    nobody's verdict was accepted, and the list says which candidates spent an
    allowance reaching that state. A record carrying only the absence reads
    exactly like a taking that never ran a candidate at all, which sends an
    operator looking for an outage rather than at the input the bound measured.
    """
    comment = verdict_comment(
        item_id="bd-ib-1",
        stage=STAGE_PRE_DISPATCH,
        digest=_DIGEST,
        rubric_digest=_RUBRIC,
        judgement=DodJudgement(
            outcome=JUDGEMENT_UNAVAILABLE,
            cause=CAUSE_INPUT_LIMIT,
            bound_ended_candidates=(
                "claude-acp:claude-opus-5",
                "codex-acp:gpt-5.6-terra",
            ),
        ),
    )

    assert "bound-ended-candidate: claude-acp:claude-opus-5" in comment
    assert "bound-ended-candidate: codex-acp:gpt-5.6-terra" in comment
    # No candidate decided it, so the record must claim none.
    assert "deciding-candidate: " not in comment
    assert "deciding-candidate-input-tokens: " not in comment


def test_a_verdict_taken_against_different_bytes_is_not_reused() -> None:
    assert (
        reusable_verdict(comments=(_held_comment(),), digest=_OTHER_DIGEST, rubric_digest=_RUBRIC)
        is None
    )


def test_the_newest_verdict_wins_and_an_unavailable_record_is_not_a_verdict() -> None:
    comments = (
        _held_comment(digest=_OTHER_DIGEST),
        _held_comment(),
        did_not_run_comment(
            item_id="bd-ib-1",
            stage=STAGE_PRE_DISPATCH,
            digest=_DIGEST,
            rubric_digest=_RUBRIC,
            cause="no-eligible-model",
        ),
    )

    reused = reusable_verdict(comments=comments, digest=_DIGEST, rubric_digest=_RUBRIC)

    assert reused is not None
    assert reused.outcome == JUDGEMENT_HELD


def test_an_item_with_no_judgement_record_at_all_reuses_nothing() -> None:
    assert reusable_verdict(comments=(), digest=_DIGEST, rubric_digest=_RUBRIC) is None
    assert (
        reusable_verdict(
            comments=("an ordinary operator rider",), digest=_DIGEST, rubric_digest=_RUBRIC
        )
        is None
    )


def _governing_comment(*, subject_digest: str = _DIGEST) -> str:
    return verdict_comment(
        item_id="bd-ib-1",
        stage=STAGE_PRE_ADMISSION,
        digest=_DIGEST,
        rubric_digest=_RUBRIC,
        judgement=DodJudgement(outcome=JUDGEMENT_ADMITTED),
        governing=GoverningHeadingReceipt(
            verdict=_GOVERNING,
            subject_digest=subject_digest,
        ),
    )


def test_a_complete_governing_receipt_reuses_the_bodies_the_prompt_carried() -> None:
    reused = reusable_governing_heading(
        comments=(_governing_comment(),),
        subject_digest=_DIGEST,
        selected_clauses=_SELECTED,
        named_clauses=_NAMED,
    )

    assert reused == _GOVERNING


def test_a_governing_receipt_reuses_nothing_after_its_subject_or_clause_changes() -> None:
    subject_changed = reusable_governing_heading(
        comments=(_governing_comment(),),
        subject_digest=_OTHER_DIGEST,
        selected_clauses=_SELECTED,
        named_clauses=_NAMED,
    )
    selected_changed = reusable_governing_heading(
        comments=(_governing_comment(),),
        subject_digest=_DIGEST,
        selected_clauses=(CondensedClause(heading="## Selected", body="Changed."),),
        named_clauses=_NAMED,
    )

    assert subject_changed is None
    assert selected_changed is None


def test_a_governing_receipt_is_not_reused_when_clause_multiplicity_changes() -> None:
    """A duplicate body changes the prompt even when its text does not."""
    duplicate_selected = _SELECTED + _SELECTED

    reused = reusable_governing_heading(
        comments=(_governing_comment(),),
        subject_digest=_DIGEST,
        selected_clauses=duplicate_selected,
        named_clauses=_NAMED,
    )

    assert reused is None


def test_an_incomplete_or_malformed_governing_receipt_is_never_reused() -> None:
    body = _governing_comment()
    malformed = (
        body.replace('"body": "The selected body."', '"body":'),
        body.replace(
            '{"body": "The selected body.", "heading": "## Selected"}',
            "[]",
        ),
        body.replace('"body": "The selected body."', '"body": 1'),
        body.replace("governing-heading-kind: stated\n", ""),
    )

    for record in malformed:
        assert (
            reusable_governing_heading(
                comments=(record,),
                subject_digest=_DIGEST,
                selected_clauses=_SELECTED,
                named_clauses=_NAMED,
            )
            is None
        )
    # A record naming no digest cannot be compared against one, so it is not a
    # reusable verdict however recent it is. The same holds for a record naming
    # no RUBRIC digest, which is what every verdict written before the rubric
    # digest existed looks like.
    assert (
        reusable_verdict(
            comments=("livespec-dod-judgement\n\noutcome: admitted",),
            digest=_DIGEST,
            rubric_digest=_RUBRIC,
        )
        is None
    )
    assert (
        reusable_verdict(
            comments=(f"livespec-dod-judgement\n\noutcome: admitted\nsubject-digest: {_DIGEST}",),
            digest=_DIGEST,
            rubric_digest=_RUBRIC,
        )
        is None
    )


def test_the_did_not_run_causes_are_those_recorded_since_the_last_real_verdict() -> None:
    stale = did_not_run_comment(
        item_id="bd-ib-1",
        stage=STAGE_PRE_ADMISSION,
        digest=_DIGEST,
        rubric_digest=_RUBRIC,
        cause="no-eligible-model",
    )
    fresh = did_not_run_comment(
        item_id="bd-ib-1",
        stage=STAGE_PRE_DISPATCH,
        digest=_DIGEST,
        rubric_digest=_RUBRIC,
        cause="unparseable-verdict",
    )

    assert recorded_did_not_run_causes(comments=(stale, fresh)) == frozenset(
        {"no-eligible-model", "unparseable-verdict"}
    )
    # The judgement ran in between, so the cause recorded before it no longer
    # suppresses the same cause recorded afterwards.
    assert recorded_did_not_run_causes(comments=(stale, _held_comment(), fresh)) == frozenset(
        {"unparseable-verdict"}
    )
    assert recorded_did_not_run_causes(comments=()) == frozenset()


def test_a_did_not_run_comment_names_the_cause_and_the_stage() -> None:
    body = did_not_run_comment(
        item_id="bd-ib-1",
        stage=STAGE_PRE_DISPATCH,
        digest=_DIGEST,
        rubric_digest=_RUBRIC,
        cause="no-eligible-model",
    )

    assert "livespec-dod-judgement-unavailable" in body
    assert "no-eligible-model" in body
    assert STAGE_PRE_DISPATCH in body
    assert "did not run" in body


def test_a_verdict_taken_under_a_different_rubric_is_not_reused() -> None:
    # The other half of the reuse condition. Without it a verdict survives the
    # very rubric change that retires it, and the surviving verdict reads as a
    # judgement of the new rules while having been taken under the old.
    assert (
        reusable_verdict(comments=(_held_comment(),), digest=_DIGEST, rubric_digest=_OTHER_RUBRIC)
        is None
    )


def test_a_partial_receipt_keeps_its_generalization_target_and_names_it() -> None:
    """The target is recorded, read back for reuse, and counted as a named heading."""
    partial = GoverningHeadingVerdict(
        kind="partial",
        generalization_target="## Broader",
        selected_clauses=_SELECTED,
        named_clauses=(CondensedClause(heading="## Broader", body="The broader body."),),
    )
    body = verdict_comment(
        item_id="bd-ib-1",
        stage=STAGE_PRE_ADMISSION,
        digest=_DIGEST,
        rubric_digest=_RUBRIC,
        judgement=DodJudgement(outcome=JUDGEMENT_ADMITTED),
        governing=GoverningHeadingReceipt(verdict=partial, subject_digest=_DIGEST),
    )

    reused = reusable_governing_heading(
        comments=(body,),
        subject_digest=_DIGEST,
        selected_clauses=_SELECTED,
        named_clauses=partial.named_clauses,
    )

    assert reused == partial
    recorded = recorded_governing_heading(comments=(body,))
    assert recorded is not None
    assert recorded.generalization_target == "## Broader"
