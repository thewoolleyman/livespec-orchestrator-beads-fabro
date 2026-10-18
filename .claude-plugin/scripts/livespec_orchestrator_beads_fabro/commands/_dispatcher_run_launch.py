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
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop import dispatch_one
from livespec_orchestrator_beads_fabro.commands._dispatcher_pre_dispatch_wall import (
    post_admission_publish_branch_reclaim,
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
    )
    launching = [*admission.rework, *admission.admitted]
    # The stale publish-branch reclaim, for the item this path is about to
    # launch -- which is a HOST-cleared, admitted target and not merely the one
    # `--item` named, because the valve can still route it away or hold it. It
    # deletes `feat/<item>` on origin and closes any pull request open on it, so
    # it belongs past the admission decision rather than in the pre-dispatch
    # wall above (bd-ib-huoyk7), and before the launch, which is what keeps the
    # new run's `publish_draft` push a plain fast-forward.
    post_admission_publish_branch_reclaim(args=args, repo=repo, items=launching, journal=journal)
    dispatched = [
        dispatch_one(
            # Both per-dispatch ledger pins, as in the queue-draining loop:
            # the factory this dispatch goes to and the workflow variant it
            # runs are recorded on the item together.
            args=args_with_dispatch_workflow_name(
                args=args_with_dispatch_factory_target(args=args, repo=repo, work_item_id=item.id),
                repo=repo,
                work_item_id=item.id,
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
