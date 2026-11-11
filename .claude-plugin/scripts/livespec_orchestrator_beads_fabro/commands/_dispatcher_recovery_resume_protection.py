"""The preserved-descendant reading that protects a clean recovery resume."""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_preserved import (
    PreservedWorkAbsent,
    PreservedWorkUnobservable,
    verified_preserved_seed,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import RecoverySeed
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_run_age import (
    published_head_relation,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection_journal import (
    read_journal_records,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_observation import ResumeGather
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_preserved_descendant import (
    PreservedDescendant,
    PreservedDescendantUnobservable,
    preserved_descendant,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = ["protected_resume_seed"]


def protected_resume_seed(
    *, gather: ResumeGather, item: WorkItem, repo: Path, runner: CommandRunner, journal: JournalFile
) -> RecoverySeed | PreservedDescendantUnobservable | None:
    """Return a descendant seed, an unreadable comparison, or no protection."""
    journaled = read_journal_records(journal_path=journal.path)
    preserved = verified_preserved_seed(
        runner=runner,
        repo=repo,
        work_item_id=item.id,
        earlier_run_ids=gather.earlier_run_ids,
        journal_records=journaled,
        publications=gather.publications,
    )
    if isinstance(preserved, PreservedWorkAbsent | PreservedWorkUnobservable):
        return None
    head = gather.observation.pull_request_head
    if head is None:
        return None
    comparison = preserved_descendant(
        runner=runner,
        repo=repo,
        preservation=preserved,
        published_head=head,
        head_is_later=published_head_relation(
            records=journaled,
            preserved_run_id=preserved.source_run_id,
            published_head=head,
            publications=gather.publications,
        ),
    )
    return preserved if isinstance(comparison, PreservedDescendant) else comparison
