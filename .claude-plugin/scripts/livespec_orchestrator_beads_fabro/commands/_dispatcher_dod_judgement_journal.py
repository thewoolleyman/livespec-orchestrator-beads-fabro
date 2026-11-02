"""The dispatch-journal row every host Definition-of-Done taking appends.

The host takes the judgement at three positions: the pre-dispatch wall, the
`approve` valve and intake filing. A row written by only one of them leaves the
other takings uncountable, so the row's write is one function all three call.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_spec_identity import (
    spec_identity_journal_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_journal_file import JournalFile

if TYPE_CHECKING:
    from pathlib import Path

__all__: list[str] = [
    "journal_dod_taking",
    "journal_dod_taking_to_repo",
]


def journal_dod_taking(
    *, journal: object | None, work_item_id: str, stage: str, decision: object
) -> None:
    """Append the row for one taking that decided or ended at the input bound.

    A taking that reached neither a spec identity nor the input bound has no
    evidence to state, so it appends nothing.
    """
    append = getattr(journal, "append", None)
    if append is None:
        return
    identity = getattr(decision, "spec_identity", None)
    bound_ended = tuple(getattr(decision, "bound_ended_candidates", ()))
    if identity is None and not bound_ended:
        return
    append(
        record=spec_identity_journal_record(
            work_item_id=work_item_id,
            stage=stage,
            identity=identity,
            deciding_candidate=getattr(decision, "deciding_candidate", None),
            bound_ended_candidates=bound_ended,
            total_input_tokens=getattr(decision, "total_input_tokens", None),
        )
    )


def journal_dod_taking_to_repo(
    *, repo: Path, work_item_id: str, stage: str, decision: object
) -> None:
    """The same row, appended to the repository's own dispatch journal."""
    journal_dod_taking(
        journal=JournalFile(path=repo / "tmp" / "fabro-dispatch-journal.jsonl"),
        work_item_id=work_item_id,
        stage=stage,
        decision=decision,
    )
