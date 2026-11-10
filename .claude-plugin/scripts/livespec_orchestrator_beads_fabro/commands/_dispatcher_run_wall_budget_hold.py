"""A held whole-run wall budget cancel, counted and escalated once.

`SPECIFICATION/contracts.md` section "Dispatcher progress watchdog" -> "The
whole-run wall budget": when no verified preservation ref exists the Dispatcher
"MUST NOT cancel the run, because the cancel would destroy the only copy of its
work. Instead, at the third consecutive `run-wall-budget-held` record for the
same run, it MUST journal one `run-wall-budget-hold-escalated` record and add one
ledger comment to the item naming the run id, the factory, the elapsed seconds,
the budget, each failed measurement, the statement that no verified preservation
ref exists, and the remedy: a person preserves or abandons the run's work and
then cancels the run. The escalation is a needs-human cause recorded once per
run; it MUST NOT change the item's status while the run is live, and the
Dispatcher MUST keep re-attempting the export and the ref listing on every later
poll and MUST cancel as soon as either release condition holds."

WHY THE RUN IS HELD AT ALL, AND WHY THE HOLD MUST BE HEARD. The hold exists so a
run whose export failed is never destroyed with its only copy. Measured on
bd-ib-uq2ocd run 01M6PAS50BAVMD32HFBV8P89YR (2026-11-05), an unbounded silent hold
journaled 30 held rows over two and a half hours past a 21600 second wall while
nobody was told, and the run ended only when a person relayed a cancel. The
escalation is how the hold stops being silent; the release by a verified
preservation ref (`_dispatcher_run_wall_budget_refs`) is how it stops being
unbounded where the work is in fact safe.

THE COUNT LIVES IN THE WATCH, NOT IN THE FUNCTION. A held poll leaves the run
alive, so the next poll of the same loop measures the same exceeded budget and
holds again; the count is therefore state the per-run watch carries between
polls, exactly as it carries the budget clock. A caller that supplies no state
gets a fresh one per call and so can never reach a third consecutive hold, which
is the safe direction: a missing count must never escalate.

THE ESCALATION IS ONCE PER RUN, ACROSS A RESTART TOO. The in-memory flag stops a
second escalation inside one watch, and the ledger comment is the durable fact
that stops one after the Dispatcher restarted mid-run and a fresh watch counted
three holds again: the comment carries a marker and the run id, and a comment
naming both is a run already escalated. A ledger that cannot be read for that
check is read as "not escalated yet", because an unreadable ledger cannot show
one, and the worst case is a second comment rather than a silent run.

THE STATUS IS NEVER WRITTEN HERE. The seam this module is handed is the narrow
comment surface the export writes through, so it cannot express a status write.
That is how "MUST NOT change the item's status while the run is live" holds
structurally rather than carefully.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import JournalWriter
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_export import (
    LedgerComments,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_comment import (
    RUN_WALL_BUDGET_HOLD_ESCALATION_MARKER,
    run_wall_budget_hold_escalation_comment,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_records import (
    run_wall_budget_held_record,
    run_wall_budget_hold_escalated_record,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    ConnectionPrefixMissingError,
    WorkItemNotFoundError,
)

__all__: list[str] = [
    "HOLDS_BEFORE_ESCALATION",
    "RunWallHoldState",
    "hold_run",
]

# The third consecutive held record is the one that escalates.
HOLDS_BEFORE_ESCALATION = 3

_COMMENT_TEXT_KEY = "text"
_LEDGER_ERRORS = (
    WorkItemNotFoundError,
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    ConnectionPrefixMissingError,
)


@dataclass(kw_only=True)
class RunWallHoldState:
    """One run's held polls so far, and whether they were already escalated.

    MUTABLE for the reason `RunWallBudgetWatch` is: the count is the one thing
    that moves between polls, and a count re-derived per poll could not reach
    three. `failed_measurements` keeps each DISTINCT failure once, in the order
    it first failed, so the escalation names each measurement and not each poll.
    """

    consecutive_holds: int = 0
    failed_measurements: list[str] = field(default_factory=list)
    escalated: bool = False


def hold_run(  # noqa: PLR0913 — kw-only per-poll hold; the count, the dispatch, the two seams and the measured figures are independent inputs.
    *,
    state: RunWallHoldState,
    plan: DispatchPlan,
    journal: JournalWriter,
    ledger: LedgerComments | None,
    run_id: str,
    elapsed_seconds: float,
    failed_measurement: str,
) -> None:
    """Journal one held poll, and escalate the run at its third consecutive one."""
    journal.append(
        record=run_wall_budget_held_record(
            work_item_id=plan.work_item_id,
            run_id=run_id,
            elapsed_seconds=elapsed_seconds,
            budget=plan.run_wall_budget,
            failed_measurement=failed_measurement,
        )
    )
    state.consecutive_holds += 1
    if failed_measurement not in state.failed_measurements:
        state.failed_measurements.append(failed_measurement)
    if state.consecutive_holds < HOLDS_BEFORE_ESCALATION or state.escalated:
        return
    state.escalated = True
    if _already_escalated(
        comments=_prior_comments(ledger=ledger, item_id=plan.work_item_id), run_id=run_id
    ):
        return
    measurements = tuple(state.failed_measurements)
    journal.append(
        record=run_wall_budget_hold_escalated_record(
            work_item_id=plan.work_item_id,
            run_id=run_id,
            factory=plan.fabro_factory_name,
            elapsed_seconds=elapsed_seconds,
            budget=plan.run_wall_budget,
            failed_measurements=measurements,
        )
    )
    if ledger is None:
        return
    body = run_wall_budget_hold_escalation_comment(
        item_id=plan.work_item_id,
        run_id=run_id,
        factory=plan.fabro_factory_name,
        elapsed_seconds=elapsed_seconds,
        budget_seconds=plan.run_wall_budget.seconds,
        failed_measurements=measurements,
    )
    _ = attempt(
        action=lambda: ledger.add_comment(issue_id=plan.work_item_id, body=body),
        exceptions=_LEDGER_ERRORS,
    )


def _prior_comments(*, ledger: LedgerComments | None, item_id: str) -> list[dict[str, Any]]:
    """The item's comments, or none when the ledger is absent or cannot be read."""
    if ledger is None:
        return []
    listed = attempt(
        action=lambda: ledger.list_comments(issue_id=item_id), exceptions=_LEDGER_ERRORS
    )
    return [] if isinstance(listed, AttemptFailure) else listed


def _already_escalated(*, comments: list[dict[str, Any]], run_id: str) -> bool:
    """Whether one comment carries the escalation marker AND names this run."""
    for comment in comments:
        text: object = comment.get(_COMMENT_TEXT_KEY)
        if (
            isinstance(text, str)
            and RUN_WALL_BUDGET_HOLD_ESCALATION_MARKER in text
            and f"run id: {run_id}" in text
        ):
            return True
    return False
