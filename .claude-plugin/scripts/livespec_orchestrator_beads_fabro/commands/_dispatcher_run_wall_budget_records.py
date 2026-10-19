"""The journal records a whole-run wall budget writes, cancelled or held.

`SPECIFICATION/contracts.md` section "Dispatcher progress watchdog" -> "The
whole-run wall budget" requires exactly two records, and the pair is why this
module exists rather than a single renderer:

* `run-wall-budget-exceeded`, on a cancel, carrying "every field the cancel
  record above requires, under the same rules for the stage and for the pull
  request and published head ... plus the elapsed slot-holding seconds, the
  budget, the layer that supplied the budget, and the preserve-by-reference
  pointer";
* `run-wall-budget-held`, when the export could not be read back, "naming the
  run, the elapsed seconds, the budget and the failed measurement".

PURE, so every field is assertable without a factory and without a journal.

THE IDENTIFYING HALF IS NOT RE-RENDERED HERE. `watchdog_cancel_fields` is the
one renderer of the work-item, dispatch id, run id, factory, stage, pull
request and published head, shared with `watchdog-stall-cancel`, because the
clause binds the two records to ONE field set. A second renderer would drift
and the drift would be invisible: both records would stay well-formed while a
reader joining them reported one cancel class as carrying less than the other.

THE STAGES ARE SEPARATE LITERALS, not a field on one row, for the reason the
stall disposition keeps its own: these are opposite outcomes, so a reader
asking "was this run cancelled" must not match the row that says it
deliberately was not -- and neither must match the stall row, which is a
different cancel class with a different disposition.

THE HELD RECORD DELIBERATELY CARRIES LESS. It names the run rather than the
whole identifying half, because the clause names what it must carry and because
the run has NOT been cancelled: the stage, the pull request and the published
head are read from the run's own record at cancel time, and a held poll has not
reached that reading. Rendering them would put a reading nobody took onto a row
that exists to say a measurement failed.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget import RunWallBudget
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_cancel_record import (
    watchdog_cancel_fields,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_run_reading import (
    StallPublication,
)

__all__: list[str] = [
    "RUN_WALL_BUDGET_EXCEEDED_STAGE",
    "run_wall_budget_exceeded_record",
]

# The journal stage a budget cancel appends. One literal, shared by this
# producer and every reader — the resume anchor, the budget disposition, and an
# operator's `grep`.
RUN_WALL_BUDGET_EXCEEDED_STAGE = "run-wall-budget-exceeded"


def run_wall_budget_exceeded_record(  # noqa: PLR0913 — kw-only record renderer; the run's identity, its publication and the budget decision are independent inputs.
    *,
    work_item_id: str,
    dispatch_id: str | None,
    run_id: str,
    factory: str,
    executing_stage: str | None,
    publication: StallPublication | None,
    elapsed_seconds: float,
    budget: RunWallBudget,
    start_source: str,
    preserved_pointer: str,
) -> dict[str, object]:
    """Render the one record a budget cancel writes.

    FOUR figures ride it beside the identifying half, and each answers a
    question the others cannot. `elapsed_seconds` is what was MEASURED and
    `budget_seconds` is what it was measured against: the budget alone cannot
    be checked, because it says what the threshold was and never that anything
    reached it. `budget_layer` is the first question asked of any cancellation
    — 21600 seconds is the fleet default on one target and a deliberate
    override on another, and only the layer says whether raising the key would
    have saved this run or whether it had already been raised. And
    `budget_start_source` says which route dated the clock, because a recorded
    running instant is the factory's own account of when the slot was taken
    while a first-poll instant is this host's observation, late by up to one
    poll interval.

    `preserved_pointer` is REQUIRED rather than optional, which is the record's
    own half of the export-then-terminate precondition: this record is only
    ever written after the pointer was written AND read back, so there is no
    state in which a budget cancel has no pointer to name. A nullable field
    here would make a cancel that skipped the export indistinguishable from one
    whose pointer the renderer was never handed.
    """
    return {
        "stage": RUN_WALL_BUDGET_EXCEEDED_STAGE,
        **watchdog_cancel_fields(
            work_item_id=work_item_id,
            dispatch_id=dispatch_id,
            run_id=run_id,
            factory=factory,
            executing_stage=executing_stage,
            publication=publication,
        ),
        "elapsed_seconds": elapsed_seconds,
        "budget_seconds": budget.seconds,
        "budget_layer": budget.layer,
        "budget_start_source": start_source,
        "preserved_pointer": preserved_pointer,
    }
