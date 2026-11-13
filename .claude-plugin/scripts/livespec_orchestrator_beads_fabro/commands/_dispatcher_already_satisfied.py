"""The already-satisfied ending, as the Dispatcher reads it and rests the item on it.

The workflow's `already_satisfied` node is the sandbox half: a `red` turn that found the
Definition of Done already holding on the dispatch base ends there, and the node prints
one `LIVESPEC_ALREADY_SATISFIED:` line naming the dispatch base once it has proved the
tree unchanged against it. This module is the Dispatcher half. A run that ends this way
is a correct no-op rather than a dead implementer, so it takes its own outcome and its
own journal row, never the generic truncation record. The ledger half, which rests the
item, lives in `_dispatcher_already_satisfied_rest` because it imports the lifecycle seam
and this module is imported by the engine.

THE PATTERN REQUIRES A FULL DISPATCH-BASE SHA after `base=`. The node's script source
carries the same sentinel followed by a shell substitution, so any listing of the
workflow text can never be read as the ending.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
    from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan

__all__: list[str] = [
    "ALREADY_SATISFIED_SENTINEL",
    "ALREADY_SATISFIED_STAGE",
    "already_satisfied_base_from_text",
    "already_satisfied_outcome",
    "already_satisfied_route",
]

ALREADY_SATISFIED_SENTINEL = "LIVESPEC_ALREADY_SATISFIED"
ALREADY_SATISFIED_STAGE = "already-satisfied"

_EVENT_PATTERN = re.compile(
    re.escape(ALREADY_SATISFIED_SENTINEL) + r": base=(?P<base>[0-9a-f]{40}) "
)


def already_satisfied_base_from_text(*, text: str) -> str | None:
    """The dispatch base the last ending line names, or None when a run printed none."""
    matches = list(_EVENT_PATTERN.finditer(text))
    return matches[-1].group("base") if matches else None


def already_satisfied_route(*, work_item_id: str) -> str:
    return (
        f"to obtain its Proof of Done, run reconcile-merged for {work_item_id} when a merged "
        "pull request for the item exists, and otherwise start a proof-only run against the "
        "dispatch base"
    )


def already_satisfied_outcome(
    *,
    outcome_type: type[DispatchOutcome],
    plan: DispatchPlan,
    run_id: str | None,
    terminal: DispatchOutcome | None,
    text: str,
) -> DispatchOutcome | None:
    """The outcome of a run that ended as already satisfied, or None for any other run.

    A run the engine ended non-green keeps its own terminal outcome whatever its output
    quoted, so the ending is only ever read off a run that succeeded.
    """
    base = already_satisfied_base_from_text(text=text) if terminal is None else None
    if base is None:
        return None
    return outcome_type(
        work_item_id=plan.work_item_id,
        status="green",
        stage=ALREADY_SATISFIED_STAGE,
        pr_number=None,
        merge_sha=None,
        detail=(
            f"already satisfied: the Definition of Done of {plan.work_item_id} already holds on "
            f"dispatch base {base}, so no Red test was written and no pull request was opened; "
            f"{already_satisfied_route(work_item_id=plan.work_item_id)}"
        ),
        fabro_run_id=run_id,
        already_satisfied_base=base,
    )
