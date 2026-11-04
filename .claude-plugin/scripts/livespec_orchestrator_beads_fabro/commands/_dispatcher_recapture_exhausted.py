"""The `recapture cap` ending of the `non_converged` terminal, mapped to a needs-human rest.

Work-item `bd-ib-iy4cd4`. `recapture_route` sends its third recapture verdict to
the same `non_converged` terminal the janitor's exhausted fix loop reaches, and
that terminal printed one fixed line naming the janitor cap. The Dispatcher read
the line as a slice that would not converge and bounced the item to `backlog`
for re-grooming. Measured on run `01M5YH9P9REX` (`bd-ib-yzk2h2`, petri,
2026-10-27): the janitor had succeeded, and the real fault was a proof record
whose steps kept failing the record grammar, which a proof-capture rider repairs.

The terminal now prints `RECAPTURE_EXHAUSTED_MARKER` and the recurring
proof-record findings when the recapture cap fired. This module is the consumer:
it turns that line into the SAME `blocked` outcome the needs-human terminal
produces, so the shared post-run sequence rests the item at `blocked` /
`needs-human` and writes the durable cause comment, and nothing bounces it.

THE CAUSE IS CARRIED AS THE TERMINAL'S REASON AND THE ENDING IS A STAGE FAILURE.
`recapture_route` is the stage that stopped the run, and no agent asked anything,
so the cause comment's existing stage-failure wording — no answer is owed, triage
the fault, release with the valve — is the true one. The reason line rides on
`needs_human_reason`, which the comment renders as `terminal reason:`, so the
marker and the findings reach the ledger without a second writer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    RECAPTURE_EXHAUSTED_MARKER,
    DispatchPlan,
)
from livespec_orchestrator_beads_fabro.commands._fabro_causal_stage import STAGE_FAILURE
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroFailureDetail

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome

__all__: list[str] = [
    "RECAPTURE_ROUTE_NODE",
    "recapture_exhausted_outcome",
    "recapture_exhausted_reason",
]

RECAPTURE_ROUTE_NODE = "recapture_route"

_LINE_PREFIX = f"{RECAPTURE_EXHAUSTED_MARKER}:"
_UNKNOWN_RUN = "unknown-run"


def recapture_exhausted_reason(*, text: str) -> str | None:
    """The LAST recapture-cap line in `text`, or `None` when it names none.

    The last, because two lines can carry the marker: `recapture_route`'s own
    bound line, which says the cap was reached, and the terminal's, which follows
    it and adds the recurring findings. Run output is chronological, so the later
    line is the fuller account.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip().startswith(_LINE_PREFIX)]
    return lines[-1] if lines else None


def recapture_exhausted_outcome(
    *,
    outcome_type: type[DispatchOutcome],
    plan: DispatchPlan,
    run_id: str | None,
    failure: FabroFailureDetail | None,
    emitted: str,
    client_text: str,
) -> DispatchOutcome | None:
    """Map a recapture-cap ending onto the `blocked` outcome, or `None` for any other.

    `emitted` is the terminal stage's own recorded output and is read FIRST: on
    an engine whose client never echoes a terminal's output it is the only
    channel carrying the line, and on any engine it is the one that holds the
    terminal's fuller line rather than the route's shorter one. `client_text` is
    the fallback, exactly as the needs-human mapper treats its two channels.
    """
    reason = recapture_exhausted_reason(text=emitted) or recapture_exhausted_reason(
        text=client_text
    )
    if reason is None:
        return None
    return outcome_type(
        work_item_id=plan.work_item_id,
        status="blocked",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail=_detail(work_item_id=plan.work_item_id, run_id=run_id, reason=reason),
        needs_human_kind=STAGE_FAILURE,
        needs_human_stages=(RECAPTURE_ROUTE_NODE,),
        needs_human_reason=reason,
        fabro_run_id=run_id,
        fabro_failure_cause=None if failure is None else failure.cause,
        fabro_failure_category=None if failure is None else failure.category,
        fabro_failure_signature=None if failure is None else failure.signature,
    )


def _detail(*, work_item_id: str, run_id: str | None, reason: str) -> str:
    """The dispatch result's account, which names the repair and the valve."""
    run_label = _UNKNOWN_RUN if run_id is None else run_id
    return (
        f"run {run_label} ended at the non_converged terminal because the recapture cap "
        f"was reached; {reason}; no agent asked anything, so no answer is owed — repair "
        "the captured proof record (a proof-capture rider that answers the findings "
        f"above), then release the item with `resolve-blocked:{work_item_id}:ready` to "
        "re-dispatch, or leave it blocked"
    )
