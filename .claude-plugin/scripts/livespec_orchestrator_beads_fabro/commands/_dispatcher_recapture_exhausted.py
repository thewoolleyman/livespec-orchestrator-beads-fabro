"""Recognise a run that ended on the recapture cap and map it to a needs-human rest.

The `recapture_route` node counts review's recapture verdicts and, on the third,
leaves a trace that the `non_converged` terminal reads. A run that ends with that
trace prints `LIVESPEC_RECAPTURE_EXHAUSTED` and deliberately NOT the
`LIVESPEC_NON_CONVERGED` sentinel, because the two caps have opposite remedies:
a janitor fix loop that will not converge means the slice is too big and goes
back to `backlog` for re-grooming, while a proof record that keeps failing review
is repaired by a proof-capture rider and must not spend the maintainer's groom
valve. This module is the Dispatcher side of that split: it reads the terminal's
cause line and produces the `blocked` outcome the existing needs-human pass
already rests at `blocked` / `needs-human` and records durably.

The marker is shared with the workflow graph as a literal, exactly as
`NEEDS_HUMAN_MARKER` is, so a respelling on either side stops the match.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._fabro_causal_stage import STAGE_FAILURE

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome

__all__: list[str] = [
    "RECAPTURE_EXHAUSTED_MARKER",
    "recapture_exhausted_outcome",
    "recapture_exhausted_reason",
]

RECAPTURE_EXHAUSTED_MARKER = "LIVESPEC_RECAPTURE_EXHAUSTED"

_ROUTE_NODE = "recapture_route"
_UNKNOWN_RUN = "unknown-run"


def recapture_exhausted_reason(*, text: str) -> str | None:
    """The cause line of a recapture-cap ending, or `None` for any other ending.

    The LAST line carrying the marker is read, because the route node and the
    terminal both print it and only the terminal's names the recurring findings.
    """
    lines = [line for line in text.splitlines() if RECAPTURE_EXHAUSTED_MARKER in line]
    if not lines:
        return None
    _, marker, rest = lines[-1].partition(RECAPTURE_EXHAUSTED_MARKER)
    return (marker + rest).rstrip()


def recapture_exhausted_outcome(
    *,
    outcome_type: type[DispatchOutcome],
    plan: DispatchPlan,
    run_id: str | None,
    text: str,
) -> DispatchOutcome | None:
    """Map a recapture-cap ending onto the `blocked` outcome, or `None` for no match.

    The cause rides as the outcome's innermost cause, so the durable needs-human
    comment names the marker and the recurring findings, and the stage is the
    route node that spent the bound.
    """
    reason = recapture_exhausted_reason(text=text)
    if reason is None:
        return None
    run_label = _UNKNOWN_RUN if run_id is None else run_id
    detail = (
        f"run {run_label} ended on the recapture cap, not the janitor fix-loop cap; "
        f"{reason}; the item rests at blocked / needs-human for proof-record repair "
        f"and is released with `resolve-blocked:{plan.work_item_id}:ready`"
    )
    return outcome_type(
        work_item_id=plan.work_item_id,
        status="blocked",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail=detail,
        needs_human_kind=STAGE_FAILURE,
        needs_human_stages=(_ROUTE_NODE,),
        fabro_run_id=run_id,
        fabro_failure_cause=reason,
    )
