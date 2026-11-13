"""The record-or-reuse decision taken by repository preflight.

The shell preflight is a host transport concern: this module owns the judgement
decision itself so a fake comment store and a counting command runner can prove
that a prior repository-preflight verdict binds an unchanged later taking.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_gate import (
    DodJudgementDecision,
    judge_definition_of_done,
)
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading_judge import (
    GoverningHeadingReader,
)

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = ["RepositoryPreflightCommentStore", "repository_preflight_reading"]


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
        stage="repository-preflight",
        comments=store.comments(),
        append=store.append,
        runner=runner,
        payload_root=payload_root,
        governing_heading=governing_heading,
    )
