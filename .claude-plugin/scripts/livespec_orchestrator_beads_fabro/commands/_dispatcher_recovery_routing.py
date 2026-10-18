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

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandRunner,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_measurements import (
    MEASUREMENT_PRESERVED_WORK,
    unobservable_measurements,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_non_fallback import (
    non_fallback_refusals,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_preserved import (
    PreservedWorkUnobservable,
    verified_preserved_seed,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_records import (
    PRESERVED_WORK_ABSENT,
    PRESERVED_WORK_VERIFIED,
    RECOVERY_HELD_STAGE,
    recovery_held_record,
    recovery_held_report,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_release import (
    released_for_recovery,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import (
    ROUTE_FRESH,
    ROUTE_HELD,
    ROUTE_RESUME,
    ROUTE_SEEDED,
    RecoveryHold,
    RecoveryMeasurement,
    RecoveryResume,
    RecoveryRoute,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection_journal import (
    read_journal_records,
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

    def offered(self, *, candidates: list[WorkItem]) -> list[WorkItem]:
        """The candidates the admission valve is offered, which excludes every hold.

        "A `held` item MUST NOT be offered to the admission valve in that pass. It
        stays `ready`." Withholding it from the valve is the whole of that: the
        valve is the only thing that writes `ready -> active`, so an item it never
        sees keeps its status without anything having to put it back.
        """
        return [
            one for one in candidates if not _is_held(route=self.route_for(work_item_id=one.id))
        ]

    def held_report(self, *, work_item_id: str) -> str | None:
        """The refusal `dispatch --item` exits 3 with, or `None` for a live route.

        "Under `dispatch --item` it is a precondition error (exit `3`) naming the
        item and the measurement or the non-fallback refusals with their
        remedies, before any run exists." A METHOD rather than a test the
        targeted path performs on the route it fetched: the question that path
        asks is "may I proceed", and the answer a hold owes it is the whole
        message — so a call site cannot reach the first without rendering the
        second, which is how the drain's deferred outcome and this refusal stay
        two readings of one decision.

        Keyed on the HOLD rather than on the route name, which is the same
        question asked of the field that carries the answer: `_held_route` is
        the only constructor of a hold and it is also the only one that returns
        `ROUTE_HELD`, so a route carrying a hold IS a held route, and a second
        test of the name could only ever disagree with the payload it is about
        to render.
        """
        route = self.route_for(work_item_id=work_item_id)
        if route is None or route.hold is None:
            return None
        return recovery_held_report(work_item_id=work_item_id, hold=route.hold)

    def held_outcomes(self) -> list[DispatchOutcome]:
        """One deferred outcome per held item, for the drain's own report.

        "Under `loop` the hold is reported as a deferred outcome on the same terms
        as a capacity deferral." The STATUS is therefore the capacity one, which
        is what keeps the verdict and the post-verdict alarm treating it as a
        non-defect; the STAGE is this hold's own, which is what lets an operator
        tell the two apart. That pairing is the one `_dispatcher_rework_admission`
        already uses for its own deferral.
        """
        return [
            DispatchOutcome(
                work_item_id=one.work_item_id,
                status="capacity-deferred",
                stage=RECOVERY_HELD_STAGE,
                pr_number=None,
                merge_sha=None,
                detail=_held_detail(route=one),
            )
            for one in self.routes
            if _is_held(route=one)
        ]


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
                repo=repo,
                runner=runner,
                journal=journal,
            )
        )
    return RecoveryRouting(routes=tuple(routes))


def _is_held(*, route: RecoveryRoute | None) -> bool:
    """Whether this route is the hold; an absent route never is."""
    return route is not None and route.route == ROUTE_HELD


def _held_detail(*, route: RecoveryRoute) -> str:
    """Every reason one held item names, as one line for the deferred outcome."""
    hold = route.hold
    if hold is None:
        return "recovery held"
    named = (
        *(f"{one.name}: {one.detail}" for one in hold.measurements),
        *hold.refusals,
    )
    return "recovery held: " + "; ".join(named)


def _released_route(
    *,
    gather: ResumeGather,
    item: WorkItem,
    repo: Path,
    runner: CommandRunner,
    journal: JournalFile,
) -> RecoveryRoute:
    """The route one RELEASED candidate takes, from the resume's own measurement.

    THE UNOBSERVABLE MEASUREMENTS ARE GRADED FIRST, because "an unobservable or
    unreadable measurement at any step routes `held`" and the ladder below cannot
    express that: it renders a REFUSAL for such a read, and every refusal is then
    classified as fallback-permitting or not — so an unanswered question would be
    graded as an answer.

    THE NON-FALLBACK REFUSALS ARE GRADED SECOND, for the mirror reason. They too
    are invisible to the ladder below, which asks only whether ANY refusal
    applies: a live lock, a live earlier run and a merged pull request each
    answer that question exactly as a missing anchor does, so a ladder reached
    with one of them standing would perform the plain dispatch their remedies
    exist to forbid. They are graded AFTER the unobservable measurements because
    an unanswered read is not a refusal about anything.

    The refusal ladder is then the clause's own grading surface — "`resume`, when
    every published-PR resume precondition of the `resume --item` clause passes" —
    so a silent ladder IS the resume route and nothing here re-decides it. The anchor
    and the pull request number are narrowed as well, for the same fail-closed
    reason `run_resume_command` narrows them: without an anchor there is no head
    to check out and no record to attribute, so proceeding would launch a plain
    run while the journal recorded a resume.
    """
    measurements = unobservable_measurements(observation=gather.observation)
    if measurements:
        # An unobservable measurement at ANY step routes `held`, which is why this
        # precedes the ladder rather than riding it: every one of these reads also
        # produces a REFUSAL, and a refusal is graded as fallback-permitting or
        # not — so falling through would seed or dispatch around a question that
        # was never answered, and the record would read like a measured decision.
        return _held_route(item=item, journal=journal, hold=RecoveryHold(measurements=measurements))
    refusals = non_fallback_refusals(observation=gather.observation)
    if refusals:
        # "A non-fallback refusal takes precedence over every fallback-permitting
        # one, so a merged pull request is never treated as a missing anchor."
        # Hence BEFORE the ladder rather than inside it: the ladder's first test
        # is whether ANY refusal applies, and a non-fallback one answers that
        # test identically to a fallback-permitting one — so falling through
        # would carry out a remedy the refusal exists to forbid, and would do it
        # with the record reading like an ordinary measured fallback.
        return _held_route(item=item, journal=journal, hold=RecoveryHold(refusals=refusals))
    anchor = gather.anchor
    pull_request = gather.observation.pull_request
    if resume_refusals(observation=gather.observation) or anchor is None or pull_request is None:
        return _fallback_route(gather=gather, item=item, repo=repo, runner=runner, journal=journal)
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


def _fallback_route(
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
    preserved = verified_preserved_seed(
        runner=runner,
        repo=repo,
        work_item_id=item.id,
        earlier_run_ids=gather.earlier_run_ids,
        journal_records=read_journal_records(journal_path=journal.path),
    )
    if isinstance(preserved, PreservedWorkUnobservable):
        return _held_route(
            item=item,
            journal=journal,
            hold=RecoveryHold(
                measurements=(
                    RecoveryMeasurement(name=MEASUREMENT_PRESERVED_WORK, detail=preserved.detail),
                )
            ),
        )
    if preserved is None:
        # Confirmed absence: every source was asked and named nothing, which is
        # what permits the default branch. The LOSS is recorded by the launch's
        # own route row, for the reason that module's docstring gives.
        return RecoveryRoute(
            work_item_id=item.id, route=ROUTE_FRESH, preserved_work=PRESERVED_WORK_ABSENT
        )
    return RecoveryRoute(
        work_item_id=item.id,
        route=ROUTE_SEEDED,
        seed=preserved,
        preserved_work=PRESERVED_WORK_VERIFIED,
    )


def _held_route(*, item: WorkItem, journal: JournalFile, hold: RecoveryHold) -> RecoveryRoute:
    """Record one hold and return its route; the item is left exactly as it was."""
    journal.append(record=recovery_held_record(work_item_id=item.id, hold=hold))
    return RecoveryRoute(work_item_id=item.id, route=ROUTE_HELD, hold=hold)
