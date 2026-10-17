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
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import RecoveryRoute
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_entry import (
    RESUME_ENTRY_NODE_ARG,
    RESUME_HEAD_ARG,
)

__all__: list[str] = [
    "LaunchPins",
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
    return pins.workflow(args=pinned, repo=repo, work_item_id=work_item_id)
