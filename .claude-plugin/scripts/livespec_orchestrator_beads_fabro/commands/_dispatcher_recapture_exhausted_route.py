"""Route bounded proof-recapture exhaustion to its explicit recovery hold."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_recapture_exhausted_hold import (
    recapture_exhausted_hold,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_records import (
    recovery_held_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import (
    ROUTE_HELD,
    RecoveryRoute,
    RecoverySeed,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_observation import (
    ResumeGather,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "RecaptureSources",
    "recapture_exhausted_route",
    "route_recapture_exhausted",
]


@dataclass(frozen=True, kw_only=True)
class RecaptureSources:
    """The recovery-routing reads specific to a recapture-exhausted terminal."""

    gather_resume_fn: Callable[..., ResumeGather]
    journal_records: tuple[dict[str, object], ...]
    preserved_seed: Callable[..., object]


def route_recapture_exhausted(
    *,
    args: argparse.Namespace,
    repo: Path,
    item: WorkItem,
    journal: JournalFile,
    runner: CommandRunner,
    sources: RecaptureSources,
) -> RecoveryRoute:
    """Gather the terminal observation before building its held route."""
    return recapture_exhausted_route(
        gather=sources.gather_resume_fn(
            args=args,
            repo=repo,
            item=item,
            journal_path=journal.path,
            runner=runner,
        ),
        item=item,
        journal=journal,
        preserved_seed=lambda gather: sources.preserved_seed(
            runner=runner,
            repo=repo,
            work_item_id=item.id,
            earlier_run_ids=gather.earlier_run_ids,
            journal_records=sources.journal_records,
            publications=gather.publications,
        ),
    )


def recapture_exhausted_route(
    *,
    gather: ResumeGather,
    item: WorkItem,
    journal: JournalFile,
    preserved_seed: Callable[[ResumeGather], object],
) -> RecoveryRoute:
    """Hold a bounded proof attempt, preserving the route an operator may resume."""
    hold = recapture_exhausted_hold(
        work_item_id=item.id,
        pull_request=gather.observation.pull_request,
        head=gather.observation.pull_request_head,
        preserved=_terminal_preservation(
            gather=gather,
            preserved_seed=preserved_seed,
        ),
    )
    journal.append(record=recovery_held_record(work_item_id=item.id, hold=hold))
    return RecoveryRoute(work_item_id=item.id, route=ROUTE_HELD, hold=hold)


def _terminal_preservation(
    *,
    gather: ResumeGather,
    preserved_seed: Callable[[ResumeGather], object],
) -> tuple[str, str] | None:
    """Return the terminal ref only when an absent pull request needs naming."""
    if gather.observation.pull_request is not None:
        return None
    seed = preserved_seed(gather)
    if not isinstance(seed, RecoverySeed):
        return None
    return (seed.preservation_ref, seed.commit_sha)
