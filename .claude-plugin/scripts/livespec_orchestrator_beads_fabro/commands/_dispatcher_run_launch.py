"""`dispatch --item`'s admit-and-launch step, as its own cohesive unit.

The same seam `_dispatcher_loop_wave` is to `_dispatcher_loop_command`: the
command module owns the INVOCATION — the preamble, the store preparation, the
size and ledger preconditions, the selection, the shared pre-dispatch wall and
the post-verdict tail — while this module owns the one thing that happens
between them, which is admitting the chosen target and launching it.

WHY THE TWO PATHS STILL DO NOT SHARE ONE FUNCTION. The valve is invoked on
DIFFERENT terms: a targeted dispatch is an operator override and passes
`enforce_cap=False`, while the drain enforces the per-repo WIP cap — so the one
line that would have to be parameterized is the one the two paths exist to
differ on. Everything downstream of the valve is a call into a shared module
already, and stays one.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_admission import (
    admit_and_select,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_ledger import (
    args_with_dispatch_factory_target,
    explicit_dispatch_factory,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop import dispatch_one
from livespec_orchestrator_beads_fabro.commands._dispatcher_pre_dispatch_wall import (
    post_admission_publish_branch_reclaim,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_launch import (
    LaunchPins,
    journal_recovery_route,
    recovery_launch_args,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routing import (
    RecoveryRouting,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_rework_admission import (
    ReworkPass,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_workflow_ledger import (
    args_with_dispatch_workflow_name,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "admit_and_dispatch_target",
]


def admit_and_dispatch_target(  # noqa: PLR0913 — kw-only targeted dispatch; `marked` is the leg the target rides, decided at selection.
    *,
    args: argparse.Namespace,
    repo: Path,
    items: list[WorkItem],
    target: WorkItem,
    journal: JournalFile,
    janitor: tuple[str, ...] | None,
    marked: bool,
    routing: RecoveryRouting,
) -> DispatchOutcome:
    # The admission valve runs BEFORE the Fabro launch: a host-only item is
    # routed away, a manual / unresolvable-assignee item is held + surfaced,
    # and an admission-eligible item is admitted (ready -> active, assignee
    # set) and dispatched. A targeted dispatch is an operator override, so it
    # does NOT enforce the per-repo WIP cap (the queue-draining `loop` does) —
    # for a marked target on the same terms as a ready one, since the override
    # narrows WHICH item runs rather than granting rework its own bypass. A
    # marked target rides the rework leg alone: it is already `active`, so
    # offering it to the ready plan as well would re-admit and re-launch the
    # same row twice in one pass.
    admission = admit_and_select(
        repo=repo,
        items=items,
        candidates=[] if marked else [target],
        journal=journal,
        enforce_cap=False,
        rework=ReworkPass(scope_ids=frozenset({target.id})),
        # This invocation's `--factory`, which the valve cannot read for itself:
        # it is the top layer of the factory precedence the pending claim stamp
        # resolves under, and the one layer `LIVESPEC_FABRO_FACTORY` cannot
        # stand in for.
        explicit_factory=explicit_dispatch_factory(args=args),
        # The route recovery routing assigned each candidate before this valve,
        # which the pending claim stamp's own factory precedence reads: the
        # item's recorded factory is a resume-only pin, so a fresh dispatch must
        # be stamped with the default it will actually reach.
        resume_ids=routing.resume_ids(),
    )
    launching = [*admission.rework, *admission.admitted]
    # The stale publish-branch reclaim, for the item this path is about to
    # launch -- which is a HOST-cleared, admitted target and not merely the one
    # `--item` named, because the valve can still route it away or hold it. It
    # deletes `feat/<item>` on origin and closes any pull request open on it, so
    # it belongs past the admission decision rather than in the pre-dispatch
    # wall above (bd-ib-huoyk7), and before the launch, which is what keeps the
    # new run's `publish_draft` push a plain fast-forward.
    # A `resume`-routed item is deliberately NOT offered, exactly as in the
    # drain: the surviving publish branch is the branch its run resumes on, so
    # preserving that head to a ref and deleting the branch would destroy what
    # the resume exists to finish.
    post_admission_publish_branch_reclaim(
        args=args,
        repo=repo,
        items=[item for item in launching if routing.reclaims(work_item_id=item.id)],
        journal=journal,
    )
    # Each launching item's route, recorded now that the valve has decided it
    # will launch -- here rather than at the measurement, because a route is
    # valid only for the pass that measured it and an item the valve turned away
    # must carry nothing out of this one.
    for item in launching:
        journal_recovery_route(route=routing.route_for(work_item_id=item.id), journal=journal)
    dispatched = [
        dispatch_one(
            # BOTH per-dispatch ledger pins AND this item's recovery route, in
            # one per-item place, as in the queue-draining loop: the factory
            # this dispatch goes to, the workflow variant it runs and the tree
            # it starts from are decided together, on this item's OWN copy of
            # the arguments rather than on a namespace a wave could share.
            args=recovery_launch_args(
                args=args,
                repo=repo,
                work_item_id=item.id,
                route=routing.route_for(work_item_id=item.id),
                pins=LaunchPins(
                    factory=args_with_dispatch_factory_target,
                    workflow=args_with_dispatch_workflow_name,
                ),
            ),
            repo=repo,
            item=item,
            journal=journal,
            janitor=janitor,
            # The valve's own ACP evaluation, as the queue-draining loop passes
            # it: a targeted dispatch narrows WHICH item runs and never which
            # read of the availability evidence its candidates are selected by.
            verdict=admission.verdict,
        )
        for item in launching
    ]
    return (admission.refused + dispatched)[0]
