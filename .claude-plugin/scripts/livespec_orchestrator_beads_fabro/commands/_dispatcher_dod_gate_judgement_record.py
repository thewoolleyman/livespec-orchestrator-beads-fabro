"""Project a recorded `dod_gate` verdict into item and journal receipts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_disagreement import (
    DodJudgementDisagreement,
    disagreement_record,
    disagreements,
    verdict_record,
)

__all__: list[str] = [
    "DodGateJudgementInput",
    "DodGateJudgementRecord",
    "record_dod_gate_judgement",
    "verdict_record",
]

_DISAGREEMENT_STAGE = "dod-judgement-disagreement"


@dataclass(frozen=True, kw_only=True)
class DodGateJudgementRecord:
    """The append-only projections one completed node outcome requires."""

    comment: str | None
    disagreement_comments: tuple[str, ...]
    journal_records: tuple[dict[str, str], ...]


@dataclass(frozen=True, kw_only=True)
class DodGateJudgementInput:
    """The independent facts the engine recorded for one `dod_gate` visit."""

    comments: tuple[str, ...]
    run_id: str
    subject_digest: str
    rubric_digest: str
    outcome: str
    findings: tuple[str, ...]
    timestamp: str


def record_dod_gate_judgement(**fields: object) -> DodGateJudgementRecord:
    """Render one unseen node judgement and every disagreement it completes.

    The caller appends the returned item comments before its rows. Supplying the
    complete post-append comment sequence to a later call returns no projections,
    so an inspect replay is idempotent rather than a second judgement.
    """
    judgement = DodGateJudgementInput(
        comments=_texts(value=fields.get("comments")),
        run_id=_text(value=fields.get("run_id")),
        subject_digest=_text(value=fields.get("subject_digest")),
        rubric_digest=_text(value=fields.get("rubric_digest")),
        outcome=_text(value=fields.get("outcome")),
        findings=_texts(value=fields.get("findings")),
        timestamp=_text(value=fields.get("timestamp")),
    )
    node_comment = verdict_record(
        taking="dod-gate",
        run_id=judgement.run_id,
        outcome=judgement.outcome,
        subject_digest=judgement.subject_digest,
        rubric_digest=judgement.rubric_digest,
        findings=judgement.findings,
        timestamp=judgement.timestamp,
    )
    if node_comment in judgement.comments:
        return DodGateJudgementRecord(comment=None, disagreement_comments=(), journal_records=())
    all_comments = (*judgement.comments, node_comment)
    found = disagreements(comments=all_comments)
    return DodGateJudgementRecord(
        comment=node_comment,
        disagreement_comments=tuple(disagreement_record(disagreement=item) for item in found),
        journal_records=tuple(_journal_record(disagreement=item) for item in found),
    )


def _journal_record(*, disagreement: DodJudgementDisagreement) -> dict[str, str]:
    """The journal counterpart of one item disagreement receipt."""
    return {
        "stage": _DISAGREEMENT_STAGE,
        "subject_digest": disagreement.subject_digest,
        "rubric_digest": disagreement.rubric_digest,
        "first_taking": disagreement.takings[0],
        "second_taking": disagreement.takings[1],
        "first_taken_at": disagreement.timestamps[0],
        "second_taken_at": disagreement.timestamps[1],
    }


def _text(*, value: object) -> str:
    """Require one scalar receipt field to be text."""
    if not isinstance(value, str):
        raise TypeError
    return value


def _texts(*, value: object) -> tuple[str, ...]:
    """Require one repeated receipt field to be an all-text tuple."""
    if not isinstance(value, tuple):
        raise TypeError
    items = cast("tuple[object, ...]", value)
    if not all(isinstance(item, str) for item in items):
        raise TypeError
    return tuple(item for item in items if isinstance(item, str))
