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
    DodJudgement,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_record import (
    STAGE_PRE_ADMISSION,
    STAGE_PRE_DISPATCH,
    did_not_run_comment,
    recorded_did_not_run_causes,
    reusable_verdict,
    verdict_comment,
)

_DIGEST = "a" * 64
_OTHER_DIGEST = "b" * 64
_FINDINGS = (
    "bd-ib-1: the References line omits the governing scenario; add that heading.",
    "bd-ib-1: assertion 2 asserts a test exists; restate it as the behaviour.",
)


def _held_comment(*, digest: str = _DIGEST) -> str:
    return verdict_comment(
        item_id="bd-ib-1",
        stage=STAGE_PRE_ADMISSION,
        digest=digest,
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
    reused = reusable_verdict(comments=(_held_comment(),), digest=_DIGEST)

    assert reused is not None
    assert reused.outcome == JUDGEMENT_HELD
    assert reused.findings == _FINDINGS
    assert reused.first_remedy == "add that heading."


def test_an_admitted_verdict_round_trips_and_carries_no_finding() -> None:
    body = verdict_comment(
        item_id="bd-ib-1",
        stage=STAGE_PRE_DISPATCH,
        digest=_DIGEST,
        judgement=DodJudgement(outcome=JUDGEMENT_ADMITTED),
    )

    reused = reusable_verdict(comments=(body,), digest=_DIGEST)

    assert reused is not None
    assert reused.outcome == JUDGEMENT_ADMITTED
    assert reused.findings == ()
    assert reused.first_remedy is None


def test_a_verdict_taken_against_different_bytes_is_not_reused() -> None:
    assert reusable_verdict(comments=(_held_comment(),), digest=_OTHER_DIGEST) is None


def test_the_newest_verdict_wins_and_an_unavailable_record_is_not_a_verdict() -> None:
    comments = (
        _held_comment(digest=_OTHER_DIGEST),
        _held_comment(),
        did_not_run_comment(
            item_id="bd-ib-1",
            stage=STAGE_PRE_DISPATCH,
            digest=_DIGEST,
            cause="no-eligible-model",
        ),
    )

    reused = reusable_verdict(comments=comments, digest=_DIGEST)

    assert reused is not None
    assert reused.outcome == JUDGEMENT_HELD


def test_an_item_with_no_judgement_record_at_all_reuses_nothing() -> None:
    assert reusable_verdict(comments=(), digest=_DIGEST) is None
    assert reusable_verdict(comments=("an ordinary operator rider",), digest=_DIGEST) is None
    # A record naming no digest cannot be compared against one, so it is not a
    # reusable verdict however recent it is.
    assert (
        reusable_verdict(comments=("livespec-dod-judgement\n\noutcome: admitted",), digest=_DIGEST)
        is None
    )


def test_the_did_not_run_causes_are_those_recorded_since_the_last_real_verdict() -> None:
    stale = did_not_run_comment(
        item_id="bd-ib-1", stage=STAGE_PRE_ADMISSION, digest=_DIGEST, cause="no-eligible-model"
    )
    fresh = did_not_run_comment(
        item_id="bd-ib-1", stage=STAGE_PRE_DISPATCH, digest=_DIGEST, cause="unparseable-verdict"
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
        item_id="bd-ib-1", stage=STAGE_PRE_DISPATCH, digest=_DIGEST, cause="no-eligible-model"
    )

    assert "livespec-dod-judgement-unavailable" in body
    assert "no-eligible-model" in body
    assert STAGE_PRE_DISPATCH in body
    assert "did not run" in body
