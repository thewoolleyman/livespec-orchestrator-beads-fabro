"""The Dispatcher projects one recorded `dod_gate` outcome into durable receipts."""

from __future__ import annotations

import importlib
from pathlib import Path

_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/"
    "_dispatcher_dod_gate_judgement_record.py"
)
_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_dod_gate_judgement_record"


def test_a_node_refusal_names_the_run_and_yields_one_disagreement_journal_row() -> None:
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE)
    host = module.verdict_record(
        taking="pre-dispatch",
        outcome="admitted",
        subject_digest="a" * 64,
        rubric_digest="b" * 64,
        timestamp="2026-11-12T17:00:00Z",
    )

    result = module.record_dod_gate_judgement(
        judgement=module.DodGateJudgementInput(
            comments=(host,),
            run_id="01RUN",
            subject_digest="a" * 64,
            rubric_digest="b" * 64,
            outcome="rests-at-needs-human",
            findings=("the assertion needs a reference",),
            timestamp="2026-11-12T17:01:00Z",
        )
    )

    assert result.comment.startswith("livespec-dod-judgement\n")
    assert "taking: dod-gate run-01RUN" in result.comment
    assert len(result.disagreement_comments) == 1
    assert result.journal_records == (
        {
            "stage": "dod-judgement-disagreement",
            "subject_digest": "a" * 64,
            "rubric_digest": "b" * 64,
            "first_taking": "pre-dispatch",
            "second_taking": "dod-gate run-01RUN",
            "first_taken_at": "2026-11-12T17:00:00Z",
            "second_taken_at": "2026-11-12T17:01:00Z",
        },
    )


def test_a_replayed_node_outcome_appends_no_second_receipt_or_row() -> None:
    module = importlib.import_module(_MODULE)
    first = module.record_dod_gate_judgement(
        judgement=module.DodGateJudgementInput(
            comments=(),
            run_id="01RUN",
            subject_digest="a" * 64,
            rubric_digest="b" * 64,
            outcome="admitted",
            findings=(),
            timestamp="2026-11-12T17:01:00Z",
        )
    )

    replay = module.record_dod_gate_judgement(
        judgement=module.DodGateJudgementInput(
            comments=(first.comment,),
            run_id="01RUN",
            subject_digest="a" * 64,
            rubric_digest="b" * 64,
            outcome="admitted",
            findings=(),
            timestamp="2026-11-12T17:01:00Z",
        )
    )

    assert replay.comment is None
    assert replay.disagreement_comments == ()
    assert replay.journal_records == ()
