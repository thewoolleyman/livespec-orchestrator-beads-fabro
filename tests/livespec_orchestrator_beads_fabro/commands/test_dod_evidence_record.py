"""Recorded governing-heading evidence reads back whole or not at all."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_clause_record import (
    evidence_from,
    evidence_line,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    JUDGEMENT_ADMITTED,
    DodJudgement,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_record import (
    STAGE_PRE_ADMISSION,
    GoverningHeadingReceipt,
    recorded_governing_heading,
    reusable_governing_heading,
    verdict_comment,
)
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading import (
    GoverningHeadingVerdict,
)
from livespec_runtime.spec_stated import ClauseEvidence


def test_evidence_round_trips_through_its_record_line() -> None:
    entry = ClauseEvidence(heading="## H", quote='A "quoted"\nmultiline clause.')
    line = evidence_line(key="k", entry=entry)

    assert evidence_from(values=(line.removeprefix("k: "),)) == (entry,)
    assert evidence_from(values=()) == ()


def test_any_malformed_evidence_value_yields_no_reading() -> None:
    assert evidence_from(values=("not json",)) is None
    assert evidence_from(values=('["a"]',)) is None
    assert evidence_from(values=('{"heading": "## H"}',)) is None
    assert evidence_from(values=('{"heading": 1, "quote": "q"}',)) is None


def test_a_receipt_with_malformed_evidence_is_neither_reused_nor_read_as_evidence() -> None:
    verdict = GoverningHeadingVerdict(
        kind="stated",
        stated_by=("## Named",),
        evidence=(ClauseEvidence(heading="## Named", quote="q"),),
    )
    body = verdict_comment(
        item_id="bd-ib-1",
        stage=STAGE_PRE_ADMISSION,
        digest="a" * 64,
        rubric_digest="c" * 64,
        judgement=DodJudgement(outcome=JUDGEMENT_ADMITTED),
        governing=GoverningHeadingReceipt(verdict=verdict, subject_digest="a" * 64),
    ).replace('{"heading": "## Named", "quote": "q"}', "not json")

    assert (
        reusable_governing_heading(
            comments=(body,),
            subject_digest="a" * 64,
            selected_clauses=(),
            named_clauses=(),
        )
        is None
    )
    recorded = recorded_governing_heading(comments=(body,))
    assert recorded is not None
    assert recorded.evidence == ()
