"""The routes a refused resume falls back to, and the hold every route can end in.

Split out of `_dispatcher_recovery_routing`, which keeps the ORDER of the grading,
by cohesion: these two functions are the preserved-work reading's consumer and the
hold's one constructor, and each is reached from more than one arm of that order.
The functions moved verbatim, docstrings included.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_preserved import (
    PreservedWorkAbsent,
    PreservedWorkUnobservable,
    verified_preserved_seed,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_records import (
    PRESERVED_WORK_ABSENT,
    PRESERVED_WORK_VERIFIED,
    recovery_held_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import (
    ROUTE_FRESH,
    ROUTE_HELD,
    ROUTE_SEEDED,
    RecoveryHold,
    RecoveryLoss,
    RecoveryMeasurement,
    RecoveryRoute,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection_journal import (
    read_journal_records,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_observation import ResumeGather
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "fallback_route",
    "held_route",
]


def fallback_route(
    *,
    gather: ResumeGather,
    item: WorkItem,
    repo: Path,
    runner: CommandRunner,
    journal: JournalFile,
) -> RecoveryRoute:
    """The route a refused resume falls back to: `seeded`, `fresh`, or `held`.

    "`seeded`, when every applicable resume refusal is fallback-permitting and
    preserved work is verified; `fresh`, when every applicable resume refusal is
    fallback-permitting and preserved work is confirmed absent; `held`, when...
    any measurement routing needs cannot be taken."

    The preserved-work read is taken HERE rather than beside the gather, because
    it is the one measurement only this arm needs: a resume that passes never asks
    it, and asking it anyway would spend an origin round trip per released
    candidate to answer a question the route had already settled.
    """
    journaled = read_journal_records(journal_path=journal.path)
    preserved = verified_preserved_seed(
        runner=runner,
        repo=repo,
        work_item_id=item.id,
        earlier_run_ids=gather.earlier_run_ids,
        journal_records=journaled,
        publications=gather.publications,
    )
    if isinstance(preserved, PreservedWorkUnobservable):
        return held_route(
            item=item,
            journal=journal,
            hold=RecoveryHold(
                measurements=(
                    RecoveryMeasurement(name=preserved.measurement, detail=preserved.detail),
                )
            ),
        )
    if isinstance(preserved, PreservedWorkAbsent):
        # Confirmed absence: every source that could be asked was asked and named
        # nothing, which is what permits the default branch. The LOSS is recorded
        # by the launch's own route row, for the reason that module's docstring
        # gives — and it carries the run being written off plus the sources the
        # READING asked, never a re-derivation of them here.
        return RecoveryRoute(
            work_item_id=item.id,
            route=ROUTE_FRESH,
            loss=RecoveryLoss(
                source_run_id=preserved.source_run_id, sources_asked=preserved.sources_asked
            ),
            preserved_work=PRESERVED_WORK_ABSENT,
        )
    return RecoveryRoute(
        work_item_id=item.id,
        route=ROUTE_SEEDED,
        seed=preserved,
        preserved_work=PRESERVED_WORK_VERIFIED,
    )


def held_route(*, item: WorkItem, journal: JournalFile, hold: RecoveryHold) -> RecoveryRoute:
    """Record one hold and return its route; the item is left exactly as it was."""
    journal.append(record=recovery_held_record(work_item_id=item.id, hold=hold))
    return RecoveryRoute(work_item_id=item.id, route=ROUTE_HELD, hold=hold)
