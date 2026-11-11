"""The journal records a whole-run wall budget writes, cancelled or held.

`SPECIFICATION/contracts.md` section "Dispatcher progress watchdog" -> "The
whole-run wall budget" requires three records, and the set is why this module
exists rather than a single renderer:

* `run-wall-budget-exceeded`, on a cancel, carrying "every field the cancel
  record above requires, under the same rules for the stage and for the pull
  request and published head ... plus the elapsed slot-holding seconds, the
  budget, the layer that supplied the budget, and the preserve-by-reference
  pointer";
* `run-wall-budget-held`, when the export could not be read back, "naming the
  run, the elapsed seconds, the budget and the failed measurement";
* `run-wall-budget-hold-escalated`, once per run at its third consecutive held
  record when origin holds no verified preservation ref.

A cancel released by a verified preservation ref carries that ref and its commit
id "in place of the preserve-by-reference pointer and a statement that the
export could not be read back".

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

from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget import RunWallBudget
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_ceiling import RunWallCeiling
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_cancel_record import (
    watchdog_cancel_fields,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_progress import (
        RunWallProgress,
    )
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_run_reading import (
    StallPublication,
)

__all__: list[str] = [
    "RUN_WALL_BUDGET_CONTINUED_STAGE",
    "RUN_WALL_BUDGET_EXCEEDED_STAGE",
    "RUN_WALL_BUDGET_HELD_STAGE",
    "RUN_WALL_BUDGET_HOLD_ESCALATED_STAGE",
    "RunWallBudgetContinuation",
    "run_wall_budget_continued_record",
    "run_wall_budget_exceeded_record",
    "run_wall_budget_held_record",
    "run_wall_budget_hold_escalated_record",
]

# The journal stage a budget cancel appends. One literal, shared by this
# producer and every reader — the resume anchor, the budget disposition, and an
# operator's `grep`.
RUN_WALL_BUDGET_EXCEEDED_STAGE = "run-wall-budget-exceeded"
RUN_WALL_BUDGET_CONTINUED_STAGE = "run-wall-budget-continued"

# The journal stage a held cancel appends. Its own stage rather than a field on
# the row above, for the reason the stall disposition's held stage is: a reader
# asking "was this run cancelled on its budget" must not match the row that
# says it deliberately was not.
RUN_WALL_BUDGET_HELD_STAGE = "run-wall-budget-held"

# The journal stage the third consecutive held poll appends, once per run. Its
# own stage for the same reason: it says a person is now owed a decision, which
# neither the cancel row nor the per-poll held row says.
RUN_WALL_BUDGET_HOLD_ESCALATED_STAGE = "run-wall-budget-hold-escalated"


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
    ceiling: RunWallCeiling | None = None,
    bound_exceeded: str = "budget",
    preserved_pointer: str | None = None,
    preserved_ref: str | None = None,
    preserved_ref_commit: str | None = None,
    export_failed_measurement: str | None = None,
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

    EXACTLY ONE OF THE TWO PRESERVATION ROUTES IS GIVEN, the pointer or the ref
    with its commit id, which is the
    record's own half of the export-then-terminate precondition: this record is
    only ever written after the pointer was written AND read back, or after a
    remote ref listing of origin showed a ref holding the run's committed tree.
    There is no state in which a budget cancel names neither. A cancel released
    by a verified preservation ref names "that ref and its commit id in place of
    the preserve-by-reference pointer and a statement that the export could not
    be read back", so the record carries NO `preserved_pointer` key at all in
    that case -- an omitted pointer beside a named ref reads as the replacement
    the clause describes, where a null would read as a pointer nobody wrote --
    and `export_read_back` is the explicit false that statement is.
    """
    preservation: dict[str, object] = (
        {"preserved_pointer": preserved_pointer}
        if preserved_ref is None
        else {
            "preserved_ref": preserved_ref,
            "preserved_ref_commit": preserved_ref_commit,
            "export_read_back": False,
            "export_failed_measurement": export_failed_measurement,
        }
    )
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
        "bound_exceeded": bound_exceeded,
        "bound_seconds": (
            budget.seconds if bound_exceeded == "budget" or ceiling is None else ceiling.seconds
        ),
        "budget_start_source": start_source,
        **preservation,
    }


@dataclass(frozen=True, kw_only=True)
class RunWallBudgetContinuation:
    """The identity, bounds and evidence one continuation journal row names."""

    work_item_id: str
    dispatch_id: str | None
    run_id: str
    factory: str
    executing_stage: str | None
    elapsed_seconds: float
    budget: RunWallBudget
    ceiling: RunWallCeiling
    progress_window_seconds: float
    progress: RunWallProgress


def run_wall_budget_continued_record(
    *, continuation: RunWallBudgetContinuation
) -> dict[str, object]:
    """Record the evidence that permits this over-budget run to retain its slot."""
    evidence: dict[str, object] = (
        {
            "capture_ref": continuation.progress.capture.ref,
            "capture_commit": continuation.progress.capture.commit,
        }
        if continuation.progress.capture is not None
        else {
            "completed_node": continuation.progress.node,
            "completed_at": continuation.progress.completed_at,
        }
    )
    return {
        "stage": RUN_WALL_BUDGET_CONTINUED_STAGE,
        "work_item_id": continuation.work_item_id,
        "dispatch_id": continuation.dispatch_id,
        "run_id": continuation.run_id,
        "factory": continuation.factory,
        "executing_stage": continuation.executing_stage,
        "elapsed_seconds": continuation.elapsed_seconds,
        "budget_seconds": continuation.budget.seconds,
        "ceiling_seconds": continuation.ceiling.seconds,
        "progress_window_seconds": continuation.progress_window_seconds,
        **evidence,
    }


def run_wall_budget_held_record(
    *,
    work_item_id: str,
    run_id: str,
    elapsed_seconds: float,
    budget: RunWallBudget,
    failed_measurement: str,
) -> dict[str, object]:
    """Render the one record a HELD budget cancel writes.

    It names the run and not the whole identifying half, because the run has
    NOT been cancelled: its stage, its pull request and its published head are
    read from its own record at cancel time, and a held poll has not reached
    that reading. Rendering them would put a reading nobody took onto the one
    row that exists to say a measurement failed.

    `failed_measurement` is the export's own account of WHICH measurement
    stopped the cancel, carried verbatim rather than reduced to a code, because
    the remedies differ: a ledger this host cannot resolve is a configuration
    fault, a write that was refused is a tenant fault, and a write that did not
    read back may already have landed.

    The two measured figures ride it for the reason they ride the cancel
    record: the budget alone cannot be checked -- it says what the threshold
    was and never that anything reached it -- so an operator reading a run of
    held rows can see the elapsed figure climbing against a fixed bound.
    """
    return {
        "stage": RUN_WALL_BUDGET_HELD_STAGE,
        "work_item_id": work_item_id,
        "run_id": run_id,
        "elapsed_seconds": elapsed_seconds,
        "budget_seconds": budget.seconds,
        "budget_layer": budget.layer,
        "failed_measurement": failed_measurement,
    }


def run_wall_budget_hold_escalated_record(
    *,
    work_item_id: str,
    run_id: str,
    factory: str,
    elapsed_seconds: float,
    budget: RunWallBudget,
    failed_measurements: tuple[str, ...],
) -> dict[str, object]:
    """Render the one record the third consecutive held poll of a run writes.

    It names every distinct failed measurement of the held polls, in the order
    they first failed, because the remedies differ -- a ledger this host cannot
    resolve, a write that was refused and a ref listing that could not be taken
    are three different faults -- and an escalation naming only the last one
    would send a person after the wrong repair. The explicit
    `verified_preservation_ref: None` is the statement that none exists, and not
    an omitted key, for the reason the held record's measurement is explicit: an
    omission is what a record from a build predating the escalation looks like.
    """
    return {
        "stage": RUN_WALL_BUDGET_HOLD_ESCALATED_STAGE,
        "work_item_id": work_item_id,
        "run_id": run_id,
        "factory": factory,
        "elapsed_seconds": elapsed_seconds,
        "budget_seconds": budget.seconds,
        "budget_layer": budget.layer,
        "failed_measurements": list(failed_measurements),
        "verified_preservation_ref": None,
    }
