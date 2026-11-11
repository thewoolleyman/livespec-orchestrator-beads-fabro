"""The preserved-descendant reading that protects a clean recovery resume."""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_preserved import (
    PreservedWorkAbsent,
    PreservedWorkUnobservable,
    verified_preserved_seed,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_records import (
    PRESERVED_WORK_VERIFIED,
    recovery_held_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import (
    ROUTE_HELD,
    ROUTE_SEEDED,
    RecoveryHold,
    RecoveryMeasurement,
    RecoveryRoute,
    RecoverySeed,
)
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
    descending_preservation_refusal,
    preserved_descendant,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "preserved_descendant_refusal",
    "protected_resume_seed",
    "resume_protection",
]


def protected_resume_seed(
    *, gather: ResumeGather, item: WorkItem, repo: Path, runner: CommandRunner, journal: JournalFile
) -> RecoverySeed | PreservedDescendantUnobservable | None:
    """Return a descendant seed, an unreadable comparison, or no protection."""
    if not gather.publications:
        return None
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
    if head in {preserved.preservation_tip_sha, preserved.commit_sha}:
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


def resume_protection(
    *, gather: ResumeGather, item: WorkItem, repo: Path, runner: CommandRunner, journal: JournalFile
) -> RecoveryRoute | None:
    """Divert a clean recovery resume when its preserved ref has newer work."""
    protected = protected_resume_seed(
        gather=gather, item=item, repo=repo, runner=runner, journal=journal
    )
    if isinstance(protected, PreservedDescendantUnobservable):
        hold = RecoveryHold(
            measurements=(
                RecoveryMeasurement(name="preserved-descendant", detail=protected.detail),
            )
        )
        journal.append(record=recovery_held_record(work_item_id=item.id, hold=hold))
        return RecoveryRoute(work_item_id=item.id, route=ROUTE_HELD, hold=hold)
    if protected is None:
        return None
    return RecoveryRoute(
        work_item_id=item.id,
        route=ROUTE_SEEDED,
        seed=protected,
        preserved_work=PRESERVED_WORK_VERIFIED,
    )


def preserved_descendant_refusal(
    *, gather: ResumeGather, item: WorkItem, repo: Path, journal: JournalFile
) -> tuple[str, ...]:
    """Return the direct-resume refusal that protects committed preserved work."""
    if not gather.publications or gather.observation.pull_request_head is None:
        return ()
    protected = protected_resume_seed(
        gather=gather,
        item=item,
        repo=repo,
        runner=ShellCommandRunner(),
        journal=journal,
    )
    if isinstance(protected, PreservedDescendantUnobservable):
        return (protected.detail,)
    if protected is None:
        return ()
    return (
        descending_preservation_refusal(
            preservation_ref=protected.preservation_ref,
            preservation_tip=protected.preservation_tip_sha or protected.commit_sha,
            published_head=gather.observation.pull_request_head,
        ),
    )
