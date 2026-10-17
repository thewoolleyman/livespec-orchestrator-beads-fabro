"""Recovery routing: one route per released candidate, decided before admission.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback priority"
→ "Recovery from the failed run's preserved work" fixes this step's POSITION, and
the position is the whole of what it adds: "Routing comes after the pre-dispatch
wall and BEFORE the admission valve, while the item is still `ready`, and assigns
the item exactly one route."

WHY IT CANNOT SIT WHERE THE PUBLISH-BRANCH RECLAIM SITS. The reclaim moved PAST
admission under `bd-ib-huoyk7`, because it deletes a remote ref and the wall
cannot yet know whether the selection will get a slot. A resume performs its own
admission — `ready -> active` — and refuses an item that is not `ready`; invoked
from the reclaim's position the item is ALREADY `active`, so the resume refuses on
its own status arm. That is why this is a step of the dispatch sequence rather
than another row in the pre-dispatch wall, whose stated invariant is that nothing
in it mutates.

WHY A WAVE HANDS OVER PER ITEM RATHER THAN RETURNING AN EXIT CODE. A drain hands
a WAVE to the valve, so "this item resumes instead" is a per-item hand-over inside
that wave and not something a refusing wall could express: there is no exit code
that means "item three of five takes a different launch". The hand-over is
therefore a VALUE — `RecoveryRouting`, keyed by work-item id — which each launch
path consults per item while it applies that item's factory and workflow pins.

WHY AN UNRELEASED ITEM COSTS NOTHING. "An item not released for recovery is routed
`fresh` without any remote measurement." Every dispatch of every repository
reaches this step, and the overwhelming majority of them are ordinary work; a
step that asked the forge and the factory about each of them would put two round
trips per candidate on the critical path of every drain, to answer a question
whose subject — an earlier dispatch that released the item — does not exist.

THIS STEP MUTATES NOTHING BUT THE JOURNAL. "Routing MUST NOT mutate the ledger,
origin, or any factory." The reads it takes are the resume's own gather, which is
a forge listing, a forge comment read and a factory board read; none of them
writes. The `resume` record it journals is the one the clause requires "before the
run exists", and the journal is not the ledger.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_release import (
    released_for_recovery,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import (
    ROUTE_FRESH,
    ROUTE_RESUME,
    RecoveryResume,
    RecoveryRoute,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection_journal import (
    read_journal_records,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_journal import (
    resume_journal_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_observation import (
    ResumeGather,
    gather_resume,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_refusals import resume_refusals
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "RecoveryRouting",
    "route_recovery",
]


@dataclass(frozen=True, kw_only=True)
class RecoveryRouting:
    """Every route this pass measured, keyed by the item it belongs to.

    A VALUE handed from the routing step to the launch, rather than a mutation of
    the arguments the wave shares: see the module docstring for why the clause
    forbids the second shape.
    """

    routes: tuple[RecoveryRoute, ...]

    def route_for(self, *, work_item_id: str) -> RecoveryRoute | None:
        """This item's route, or `None` for an item this pass never measured.

        `None` rather than a synthesized `fresh` route, because the two are
        different facts: an item routing never saw — a marked rework row the
        valve re-admits, say — has no route to execute, while a `fresh` route is
        a decision that was taken. Every consumer treats both as an ordinary
        dispatch, which is why the distinction costs nothing here and is worth
        keeping for a reader of the record.
        """
        return next((one for one in self.routes if one.work_item_id == work_item_id), None)

    def reclaims(self, *, work_item_id: str) -> bool:
        """Whether the stale publish-branch reclaim runs for this item.

        "The stale publish-branch reclaim runs for `fresh` and `seeded` items
        only... and it MUST NOT run for a `resume` item." The two routes are
        exclusive per dispatch: one FINISHES the dead run's publication and the
        other CLEARS it, and running both would preserve the head to a ref and
        then delete the very branch the resumed run was about to check out.
        """
        route = self.route_for(work_item_id=work_item_id)
        return route is None or route.route != ROUTE_RESUME


def route_recovery(
    *,
    args: argparse.Namespace,
    repo: Path,
    candidates: list[WorkItem],
    journal: JournalFile,
) -> RecoveryRouting:
    """Assign one route to every candidate, measuring only the released ones."""
    journaled = read_journal_records(journal_path=journal.path)
    runner = ShellCommandRunner()
    routes: list[RecoveryRoute] = []
    for item in candidates:
        if not released_for_recovery(records=journaled, work_item_id=item.id):
            routes.append(RecoveryRoute(work_item_id=item.id, route=ROUTE_FRESH))
            continue
        routes.append(
            _released_route(
                gather=gather_resume(
                    args=args,
                    repo=repo,
                    item=item,
                    journal_path=journal.path,
                    runner=runner,
                ),
                item=item,
                journal=journal,
            )
        )
    return RecoveryRouting(routes=tuple(routes))


def _released_route(*, gather: ResumeGather, item: WorkItem, journal: JournalFile) -> RecoveryRoute:
    """The route one RELEASED candidate takes, from the resume's own measurement.

    The refusal ladder is the clause's own grading surface — "`resume`, when every
    published-PR resume precondition of the `resume --item` clause passes" — so a
    silent ladder IS the resume route and nothing here re-decides it. The anchor
    and the pull request number are narrowed as well, for the same fail-closed
    reason `run_resume_command` narrows them: without an anchor there is no head
    to check out and no record to attribute, so proceeding would launch a plain
    run while the journal recorded a resume.
    """
    anchor = gather.anchor
    pull_request = gather.observation.pull_request
    if resume_refusals(observation=gather.observation) or anchor is None or pull_request is None:
        return RecoveryRoute(work_item_id=item.id, route=ROUTE_FRESH)
    journal.append(
        record=resume_journal_record(
            work_item_id=item.id,
            earlier_run_ids=gather.earlier_run_ids,
            pull_request=pull_request,
            head=anchor.head,
            resumed_at=anchor.resumed_at,
            source=anchor.source,
        )
    )
    return RecoveryRoute(
        work_item_id=item.id,
        route=ROUTE_RESUME,
        resume=RecoveryResume(
            entry_node=anchor.resumed_at,
            head=anchor.head,
            pull_request=pull_request,
            earlier_run_ids=gather.earlier_run_ids,
            source=anchor.source,
            workflow_name=gather.workflow_name,
        ),
    )
