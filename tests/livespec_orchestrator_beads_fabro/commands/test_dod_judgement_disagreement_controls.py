"""Controls for Definition-of-Done disagreement receipt reconciliation."""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_disagreement import (
    disagreements,
    verdict_record,
)

_SUBJECT = "a" * 64
_RUBRIC = "b" * 64


def _record(*, taking: str, outcome: str) -> str:
    return verdict_record(
        taking=taking,
        outcome=outcome,
        subject_digest=_SUBJECT,
        rubric_digest=_RUBRIC,
        timestamp="2026-10-24T19:00:00Z",
    )


def test_only_opposite_completed_verdicts_on_one_pair_are_disagreements() -> None:
    """A matching pass, foreign digest, and malformed receipt cannot journal a conflict."""
    comments = (
        _record(taking="preflight", outcome="admitted"),
        _record(taking="pre-admission", outcome="admitted"),
        verdict_record(
            taking="pre-dispatch",
            outcome="rests-at-needs-human",
            subject_digest="c" * 64,
            rubric_digest=_RUBRIC,
            timestamp="2026-10-24T19:01:00Z",
        ),
        "livespec-dod-judgement-dod-judgement-disagreement\n\nsubject-digest: broken\n",
        "livespec-dod-judgement\n\noutcome: admitted\n",
        "ordinary operator rider",
    )

    assert disagreements(comments=comments) == ()


def test_record_renderer_rejects_non_text_inputs() -> None:
    """A malformed writer input cannot produce a receipt that looks complete."""
    with pytest.raises(TypeError):
        _ = verdict_record(
            taking=object(),
            outcome="admitted",
            subject_digest=_SUBJECT,
            rubric_digest=_RUBRIC,
            timestamp="2026-10-24T19:00:00Z",
        )
    with pytest.raises(TypeError):
        _ = verdict_record(
            taking="preflight",
            outcome="admitted",
            subject_digest=_SUBJECT,
            rubric_digest=_RUBRIC,
            timestamp="2026-10-24T19:00:00Z",
            run_id=object(),
        )
    with pytest.raises(TypeError):
        _ = verdict_record(
            taking="preflight",
            outcome="admitted",
            subject_digest=_SUBJECT,
            rubric_digest=_RUBRIC,
            timestamp="2026-10-24T19:00:00Z",
            findings=("valid", object()),
        )
