"""Journal the non-reused host Definition-of-Done judgement takings.

The admission and dispatch surfaces each take the same judgement, but reach the
dispatch journal through different entrypoints.  Keeping the row rendering and
the host-file append here makes their input-size accounting identical.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_candidate_attempt import (
    BoundEndedCandidate,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_journal_file import JournalFile

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_decision import (
        DodJudgementDecision,
    )

__all__: list[str] = ["journal_taken_judgement", "judgement_journal_record"]

_JOURNAL_RELATIVE_PATH = ("tmp", "fabro-dispatch-journal.jsonl")


def journal_taken_judgement(
    *, repo: Path | object, item_id: str, judgement_stage: str, decision: object
) -> None:
    """Append the one countable row a fresh host judgement owes."""
    if getattr(decision, "reused", False):
        return
    JournalFile(path=cast("Path", repo).joinpath(*_JOURNAL_RELATIVE_PATH)).append(
        record=judgement_journal_record(
            item_id=item_id,
            judgement_stage=judgement_stage,
            decision=cast("DodJudgementDecision", decision),
        )
    )


def judgement_journal_record(
    *, item_id: str, judgement_stage: str, decision: DodJudgementDecision
) -> dict[str, object]:
    """Render a judgement row, falling back to its last bound-ended candidate."""
    candidate = getattr(decision, "deciding_candidate", None)
    input_tokens = getattr(decision, "input_tokens", None)
    bound_ended = [
        {
            "candidate": ended.candidate,
            "total_input_tokens": ended.input_tokens,
        }
        for ended in getattr(decision, "bound_ended_candidates", ())
        if isinstance(ended, BoundEndedCandidate)
    ]
    if candidate is None and bound_ended:
        candidate = str(bound_ended[-1]["candidate"])
        input_tokens = int(bound_ended[-1]["total_input_tokens"])
    record: dict[str, object] = {
        "stage": "dod-judgement",
        "work_item_id": item_id,
        "judgement_stage": judgement_stage,
        "candidate": candidate,
        "total_input_tokens": input_tokens,
    }
    if bound_ended:
        record["bound_ended_candidates"] = bound_ended
    return record
