"""The fresh route a current fresh ruling assigns, past every preserved tree.

A fresh ruling still identifies the item's needs-human refs.  The route does not
take one, but its record must name each ref it deliberately passed over; an
unreadable listing is held rather than mistaken for no preserved trees.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human_refs import (
    NeedsHumanRefsUnobservable,
    NeedsHumanScope,
    carrying_needs_human_refs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_measurements import (
    MEASUREMENT_PRESERVED_WORK,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_preserved import (
    NEEDS_HUMAN_REF_PREFIX,
    SEED_REMOTE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_records import (
    PRESERVED_WORK_VERIFIED,
    recovery_held_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import (
    ROUTE_FRESH,
    ROUTE_HELD,
    ROUTE_SEEDED,
    RecoveryHold,
    RecoveryMeasurement,
    RecoveryRoute,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_ruled_seed import ruled_seed
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_run_age import (
    foreign_run_ids,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection_journal import (
    read_journal_records,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_observation import ResumeGather
from livespec_orchestrator_beads_fabro.commands._dispatcher_ruling_currency import FreshRuling
from livespec_orchestrator_beads_fabro.commands._dispatcher_seed_ruling import SeedRuling
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = ["current_fresh_ruling_route", "current_ruling_route"]

_GIT_TIMEOUT_SECONDS = 120.0


def fresh_ruling_route(
    *,
    runner: CommandRunner,
    repo: Path,
    work_item_id: str,
    earlier_run_ids: tuple[str, ...],
    journal_records: tuple[dict[str, object], ...],
    ruling: FreshRuling,
) -> RecoveryRoute | RecoveryHold:
    """Record the current ruling's instant and every needs-human ref it passes over."""
    carrying = carrying_needs_human_refs(
        runner=runner,
        repo=repo,
        scope=NeedsHumanScope(
            run_ids=earlier_run_ids,
            foreign_run_ids=foreign_run_ids(
                records=journal_records, work_item_id=work_item_id, own=earlier_run_ids
            ),
        ),
        ref_prefix=NEEDS_HUMAN_REF_PREFIX,
        remote=SEED_REMOTE,
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
    )
    if isinstance(carrying, NeedsHumanRefsUnobservable):
        return RecoveryHold(
            measurements=(
                RecoveryMeasurement(
                    name=MEASUREMENT_PRESERVED_WORK,
                    detail=(
                        f"{carrying.detail}, so the fresh ruling cannot establish every "
                        "needs-human ref it must pass over"
                    ),
                ),
            )
        )
    return RecoveryRoute(
        work_item_id=work_item_id,
        route=ROUTE_FRESH,
        fresh_ruling_instant=ruling.instant,
        passed_over_needs_human=tuple((one.ref, one.commit_sha) for one in carrying),
    )


def current_fresh_ruling_route(
    *,
    runner: CommandRunner,
    repo: Path,
    item: WorkItem,
    journal: JournalFile,
    gather: ResumeGather,
    ruling: FreshRuling,
) -> RecoveryRoute:
    """Take a fresh ruling's route after recording a hold when its listing cannot run."""
    fresh = fresh_ruling_route(
        runner=runner,
        repo=repo,
        work_item_id=item.id,
        earlier_run_ids=gather.earlier_run_ids,
        journal_records=read_journal_records(journal_path=journal.path),
        ruling=ruling,
    )
    if isinstance(fresh, RecoveryHold):
        journal.append(record=recovery_held_record(work_item_id=item.id, hold=fresh))
        return RecoveryRoute(work_item_id=item.id, route=ROUTE_HELD, hold=fresh)
    return fresh


def current_ruling_route(
    *,
    runner: CommandRunner,
    repo: Path,
    item: WorkItem,
    journal: JournalFile,
    gather: ResumeGather,
    ruling: SeedRuling | FreshRuling,
) -> RecoveryRoute:
    """Resolve the current ruling before the released item's resume fallback ladder."""
    if isinstance(ruling, FreshRuling):
        return current_fresh_ruling_route(
            runner=runner,
            repo=repo,
            item=item,
            journal=journal,
            gather=gather,
            ruling=ruling,
        )
    ruled = ruled_seed(
        runner=runner, repo=repo, ruling=ruling, earlier_run_ids=gather.earlier_run_ids
    )
    if isinstance(ruled, RecoveryHold):
        journal.append(record=recovery_held_record(work_item_id=item.id, hold=ruled))
        return RecoveryRoute(work_item_id=item.id, route=ROUTE_HELD, hold=ruled)
    return RecoveryRoute(
        work_item_id=item.id,
        route=ROUTE_SEEDED,
        seed=ruled,
        preserved_work=PRESERVED_WORK_VERIFIED,
    )
