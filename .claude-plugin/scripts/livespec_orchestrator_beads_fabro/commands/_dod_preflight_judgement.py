"""The record-or-reuse decision taken by repository preflight.

The shell preflight is a host transport concern: this module owns the judgement
decision itself so a fake comment store and a counting command runner can prove
that a prior repository-preflight verdict binds an unchanged later taking.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_governing_record import (
    GoverningHeadingReceipt,
    governing_record_lines,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_governing_reuse import (
    governing_heading_subject_digest,
    reusable_governing_heading_verdict,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_gate import (
    DodJudgementDecision,
    judge_definition_of_done,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_markers import (
    JUDGEMENT_COMMENT_MARKER,
)
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading_judge import (
    GoverningHeadingReader,
)
from livespec_orchestrator_beads_fabro.commands._dod_preflight_governing_reading import (
    PreflightGoverningReading,
    preflight_governing_heading_reading,
)

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "RepositoryPreflightCommentStore",
    "repository_preflight_governing_reading",
    "repository_preflight_reading",
]

_STAGE = "repository-preflight"


class RepositoryPreflightCommentStore(Protocol):
    """The append-only item comment sidecar the repository preflight receives."""

    def comments(self) -> tuple[str, ...]:
        """Return the item's comment bodies in their ledger order."""
        ...

    def append(self, *, body: str) -> None:
        """Append one durable preflight receipt to the item."""
        ...


def repository_preflight_reading(
    *,
    item: WorkItem,
    repo: Path,
    store: RepositoryPreflightCommentStore,
    runner: CommandRunner,
    payload_root: Path,
    governing_heading: GoverningHeadingReader | None = None,
) -> DodJudgementDecision:
    """Reuse or take one repository-preflight Definition-of-Done judgement."""
    return judge_definition_of_done(
        item=item,
        repo=repo,
        stage=_STAGE,
        comments=store.comments(),
        append=store.append,
        runner=runner,
        payload_root=payload_root,
        governing_heading=governing_heading,
    )


def repository_preflight_governing_reading(
    *,
    item: WorkItem,
    repo: Path,
    store: RepositoryPreflightCommentStore,
    runner: CommandRunner,
) -> PreflightGoverningReading:
    """Take the governing-heading reading, recording a verdict this taking had to take.

    A verdict the component's reuse rule already allows decides and is not recorded
    again. A fresh one is appended BEFORE the rubric judgement runs, because that
    judgement reads the item's comments to reuse the verdict, and it appends its own
    record only when the rubric ran: without this record an outage of the rubric
    judge leaves the governing-heading taking unrecorded and the next launch re-takes
    it, which can flip the verdict on identical bytes.
    """
    comments = store.comments()
    reusable = reusable_governing_heading_verdict(item=item, repo=repo, comments=comments)
    reading = preflight_governing_heading_reading(
        item=item, repo=repo, comments=comments, runner=runner
    )
    if reusable is None and reading.verdict is not None:
        lines = [
            JUDGEMENT_COMMENT_MARKER,
            "",
            f"work-item: {item.id}",
            f"stage: {_STAGE}",
            *governing_record_lines(
                governing=GoverningHeadingReceipt(
                    verdict=reading.verdict,
                    subject_digest=governing_heading_subject_digest(item=item, comments=comments),
                )
            ),
        ]
        store.append(body="\n".join(lines))
    return reading
