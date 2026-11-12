"""Route bounded proof-recapture exhaustion to its explicit recovery hold."""

from __future__ import annotations

import argparse
from collections.abc import Callable
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
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_observation import (
    ResumeGather,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = ["recapture_exhausted_route", "route_recapture_exhausted"]


def route_recapture_exhausted(
    *,
    args: argparse.Namespace,
    repo: Path,
    item: WorkItem,
    journal: JournalFile,
    runner: CommandRunner,
    gather_resume_fn: Callable[..., ResumeGather],
) -> RecoveryRoute:
    """Gather the terminal observation before building its held route."""
    return recapture_exhausted_route(
        gather=gather_resume_fn(
            args=args,
            repo=repo,
            item=item,
            journal_path=journal.path,
            runner=runner,
        ),
        item=item,
        journal=journal,
    )


def recapture_exhausted_route(
    *,
    gather: ResumeGather,
    item: WorkItem,
    journal: JournalFile,
) -> RecoveryRoute:
    """Hold a bounded proof attempt, preserving the route an operator may resume."""
    hold = recapture_exhausted_hold(
        work_item_id=item.id,
        pull_request=gather.observation.pull_request,
        head=gather.observation.pull_request_head,
        preserved=None,
    )
    journal.append(record=recovery_held_record(work_item_id=item.id, hold=hold))
    return RecoveryRoute(work_item_id=item.id, route=ROUTE_HELD, hold=hold)
