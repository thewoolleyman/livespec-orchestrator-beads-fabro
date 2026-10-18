"""Executing one item's recovery route, on that item's own copy of the arguments.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback priority"
→ "Recovery from the failed run's preserved work" puts this step exactly where the
per-dispatch pins already are: "After admission, each launch path MUST execute
every admitted item's route on that item's own copy of the dispatch arguments, in
the same per-item step that applies the item's factory and workflow pins.
Route-specific state MUST NOT be written to arguments shared by the wave."

SO THIS MODULE OWNS THE ORDER, AND THE CALL SITES OWN THE PINS. The two pins are
handed in as `LaunchPins` rather than imported here, and that is not ceremony: a
launch path is the party that knows which repository and which item it is pinning
for, and the pins are the seam every existing test of those paths substitutes. A
module that reached for them itself would move that seam out from under both
launch paths at once.

WHY A `resume` ROUTE SKIPS THE WORKFLOW PIN ENTIRELY. `resolve_dispatch_workflow_
name` PERSISTS what it resolves — it calls `record_dispatch_workflow` — and the
resume clause forbids exactly that: "a resume MUST NOT write or clear the item's
`dispatch_workflow` metadata, so the next plain dispatch of the item re-runs the
recorded workflow from `start`". The route carries the name the EARLIER dispatch
record already named, so there is nothing for the pin to resolve and a write would
only be able to disagree with it.

WHY THE RESUME ATTRIBUTES ARE SET THROUGH THE SHARED CONSTANTS. `resume_checkout_
for` and `prepare_workflow_payload` read `resume_head` and `resume_entry_node`
DEFENSIVELY, because no other command sets them — so a typo at either end is
invisible: the attribute simply resolves absent, the dispatch proceeds as a plain
one, and the run re-implements from `start` while the journal records a resume.
Naming them through `_dispatcher_resume_entry`'s own constants is what makes the
two ends impossible to spell differently.

AND THIS MODULE OWNS THE TWO ROUTE RECORDS, FOR THE SAME POSITIONAL REASON. The
`resume` record is journaled "before the run exists", which is here and NOT at the
measurement, because "a route is valid only for the pass that measured it: an item
the valve defers for capacity carries no route into the next pass". That record is
the attribution link the acceptance pass reads, so one written for a dispatch the
valve then deferred makes the earlier run's proof grade whatever merges next — and
it counts against the two-resume chain bound, leaving the next attempt silently
one closer to refusal with the journal reading as though a resume had happened.
The route row rides with it for the mirror reason: a deferred item that recorded
the route it did not take is a record of nothing.

The HOLD record is the deliberate exception and stays at the measurement, because
a held item is never offered to the valve at all — there is no later position for
it to be written from, and the clause requires the row whether or not anything
launched.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_records import (
    recovery_route_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import RecoveryRoute
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_entry import (
    RESUME_ENTRY_NODE_ARG,
    RESUME_FETCH_REF_ARG,
    RESUME_HEAD_ARG,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_journal import (
    resume_journal_record,
)

__all__: list[str] = [
    "LaunchPins",
    "journal_recovery_route",
    "recovery_launch_args",
]


@dataclass(frozen=True, kw_only=True)
class LaunchPins:
    """The two per-item argument pins, supplied by the launch path that owns them.

    Constructed at the CALL SITE and at call time, which is what keeps every
    existing substitution of those two names effective: a launch path's tests
    replace the names in that path's own module, and a value built there resolves
    them then.
    """

    factory: Callable[..., argparse.Namespace]
    workflow: Callable[..., argparse.Namespace]


def recovery_launch_args(
    *,
    args: argparse.Namespace,
    repo: Path,
    work_item_id: str,
    route: RecoveryRoute | None,
    pins: LaunchPins,
) -> argparse.Namespace:
    """One item's own argument copy, pinned and carrying its route's state.

    The FACTORY pin is applied for every route, because every route launches a run
    somewhere and the clause gives a resume no exemption from it — "resolve its
    factory as `dispatch --item` does". The WORKFLOW pin is applied for every
    route BUT `resume`, for the persistence reason the module docstring gives.

    A `seeded` route sets the head and the REF THAT CARRIES IT and deliberately
    sets NO entry node: a seed is a plain dispatch that starts at `start`, on a
    different tree. Setting an entry node there would skip every node the seeded
    run has to run precisely because its work is unfinished.
    """
    pinned = pins.factory(args=args, repo=repo, work_item_id=work_item_id)
    resume = None if route is None else route.resume
    if resume is not None:
        cloned = argparse.Namespace(**vars(pinned))
        setattr(cloned, RESUME_ENTRY_NODE_ARG, resume.entry_node)
        setattr(cloned, RESUME_HEAD_ARG, resume.head)
        # The earlier run's recorded name WINS over an explicit `--workflow-name`,
        # because the clause makes it the requirement rather than a default. An
        # absent name leaves the ordinary variant precedence to resolve the item's
        # own recorded pin, which is the same graph.
        cloned.workflow_name = resume.workflow_name or getattr(args, "workflow_name", None)
        return cloned
    named = pins.workflow(args=pinned, repo=repo, work_item_id=work_item_id)
    seed = None if route is None else route.seed
    if seed is None:
        return named
    seeded = argparse.Namespace(**vars(named))
    setattr(seeded, RESUME_HEAD_ARG, seed.commit_sha)
    setattr(seeded, RESUME_FETCH_REF_ARG, seed.preservation_ref)
    return seeded


def journal_recovery_route(*, route: RecoveryRoute | None, journal: JournalFile) -> None:
    """Record this item's route, now that the valve has decided it will launch.

    An item routing never measured writes NOTHING, because there is no route to
    record — a marked rework row the valve re-admits is the case, and a row
    claiming it was routed `fresh` would be reporting a decision nobody took.

    The `resume` record goes FIRST, because it is the one a later reader joins on:
    the route row says which route this pass took, while the resume record is the
    attribution link, and an interrupted write that landed only the route row
    would leave a resumed run looking plain rather than looking unattributed.
    """
    if route is None:
        return
    resume = route.resume
    if resume is not None:
        journal.append(
            record=resume_journal_record(
                work_item_id=route.work_item_id,
                earlier_run_ids=resume.earlier_run_ids,
                pull_request=resume.pull_request,
                head=resume.head,
                resumed_at=resume.entry_node,
                source=resume.source,
            )
        )
    journal.append(
        record=recovery_route_record(
            work_item_id=route.work_item_id,
            route=route.route,
            seed=route.seed,
            preserved_work=route.preserved_work,
        )
    )
