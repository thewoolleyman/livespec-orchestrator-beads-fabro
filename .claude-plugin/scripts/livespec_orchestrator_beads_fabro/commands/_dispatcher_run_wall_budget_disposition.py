"""Where a whole-run wall-budget cancel leaves its work-item.

`SPECIFICATION/contracts.md` section "Dispatcher progress watchdog" -> "The
whole-run wall budget": "After a budget cancel the Dispatcher MUST rest the item
at `blocked` with `blocked_reason` `needs-human`. Its ledger comment MUST name
the run id, the factory, the stage, the elapsed seconds, the budget, the
preserve-by-reference pointer and, when the record names them, the pull request
and the published head, and MUST name the remedy `resolve-blocked:<id>:ready`."

IT IS THE PEER OF `dispose_stall_cancel`, and deliberately shaped like it: a
no-op for every status but its own, keyed off the terminal alone, fail-soft on
every ledger write, and journaling its own stage. There is ONE structural
difference and it is the whole point -- a budget cancel has NO release arm.

WHY NO RELEASE ARM. A stall says nothing about the slice, so a first stall
cancel returns the item to `ready` and the ordinary admission valve picks it up.
A run that held a factory slot for its whole budget and still had not finished
is a different object: re-dispatching it unattended would spend another full
budget to learn the same thing, and the measurement that motivated the budget
found such runs costing two to four times a successful run's slot time each. So
the item rests for a person and nothing automatic leaves that state.

THE FACTS ARE READ BACK OFF THE JOURNAL RATHER THAN RE-DERIVED, for the reason
the stall disposition records: the cancel site read the run's own record while
the run still existed, which is the one moment it was readable, and by the time
this runs the run has been `fabro rm -f`-ed -- so re-probing would answer about
nothing and would still succeed.

THE NEWEST ROW IS THE ONE REPORTED. A re-dispatched item can carry an earlier
budget cancel's row, and a comment naming that run would send a person to
triage a run this cancellation has nothing to do with.

THE COMMENT IS WRITTEN BEFORE THE LEDGER WRITE, which is the order
`dispose_stall_cancel` takes and for the same reason: the comment is what
SURVIVES. A rest whose comment failed leaves a person a blocked item with
nothing naming the run; a comment whose rest failed leaves an `active` item an
operator can see and move by hand, with the account already on the ledger.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from livespec_orchestrator_beads_fabro._store_blocked_mutations import (
    update_work_item_blocked_state,
)
from livespec_orchestrator_beads_fabro._store_comments import append_work_item_comment
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_journal_rows import (
    journal_records,
    names_stage,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_comment import (
    run_wall_budget_comment,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_records import (
    RUN_WALL_BUDGET_EXCEEDED_STAGE,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    WorkItemNotFoundError,
)
from livespec_orchestrator_beads_fabro.io import write_stderr
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "RUN_WALL_BUDGET_NEEDS_HUMAN_STAGE",
    "dispose_run_wall_budget_cancel",
    "latest_run_wall_budget_row",
]

# The journal stage a budget-rested item appends. Its own stage rather than a
# field on the cancel row, because the two answer different questions: one says
# the run was cancelled, the other says the ITEM was parked, and a dispatch
# interrupted between them wrote only the first.
RUN_WALL_BUDGET_NEEDS_HUMAN_STAGE = "run-wall-budget-needs-human"

_LEDGER_WRITE_ERRORS = (
    WorkItemNotFoundError,
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
)


def latest_run_wall_budget_row(
    *, journal: JournalFile, item_id: str
) -> Mapping[str, object] | None:
    """This item's NEWEST budget-cancel row, or None when the journal has none.

    None is read as "no row was found", which the comment states as such rather
    than leaving the run unnamed -- an interrupted dispatch can end between the
    cancel and this disposition, and those are exactly the dispatches most
    likely to have left a slot-holding run behind.
    """
    rows = [
        record
        for record in journal_records(journal=journal)
        if names_stage(record=record, item_id=item_id, stage=RUN_WALL_BUDGET_EXCEEDED_STAGE)
    ]
    return rows[-1] if rows else None


def dispose_run_wall_budget_cancel(
    *,
    repo: Path,
    item: WorkItem,
    outcome: DispatchOutcome,
    journal: JournalFile,
) -> None:
    """Rest one budget-cancelled item at `blocked` / `needs-human`.

    A no-op for every outcome that is not a budget cancel. The status is the
    whole discriminator and no journal correlation is needed to identify one:
    the watch seam writes that status only after the run's pointer was read back
    and the run was `fabro rm -f`-ed.

    `admission_policy="manual"` rides the same write for the reason
    `escalate_needs_human_block` carries it: `blocked` alone is a status the
    drain could still be configured to admit, and the point of this terminal is
    that no further dispatch happens without a human.
    """
    if outcome.status != RUN_WALL_BUDGET_EXCEEDED_STAGE:
        return
    row = latest_run_wall_budget_row(journal=journal, item_id=item.id)
    _ = attempt(
        action=lambda: append_work_item_comment(
            path=store_config(repo=repo),
            work_item_id=item.id,
            body=run_wall_budget_comment(item_id=item.id, row=row),
        ),
        exceptions=_LEDGER_WRITE_ERRORS,
    )
    rested = attempt(
        action=lambda: update_work_item_blocked_state(
            path=store_config(repo=repo),
            item_id=item.id,
            status="blocked",
            blocked_reason="needs-human",
            admission_policy="manual",
        ),
        exceptions=_LEDGER_WRITE_ERRORS,
    )
    if isinstance(rested, AttemptFailure):
        journal.append(
            record={
                "stage": f"{RUN_WALL_BUDGET_NEEDS_HUMAN_STAGE}-error",
                "work_item_id": item.id,
                "reason": f"{type(rested.error).__name__}",
            }
        )
        return
    _journal_rest(journal=journal, item=item, row=row)


def _journal_rest(
    *,
    journal: JournalFile,
    item: WorkItem,
    row: Mapping[str, object] | None,
) -> None:
    """Record the rest, and surface it on stderr for the invoking operator."""
    journal.append(
        record={
            "stage": RUN_WALL_BUDGET_NEEDS_HUMAN_STAGE,
            "work_item_id": item.id,
            "status": "blocked",
            "blocked_reason": "needs-human",
            "run_id": None if row is None else row.get("run_id"),
            "elapsed_seconds": None if row is None else row.get("elapsed_seconds"),
            "budget_seconds": None if row is None else row.get("budget_seconds"),
            "preserved_pointer": None if row is None else row.get("preserved_pointer"),
        }
    )
    _ = write_stderr(
        text=(
            f"SURFACE: work-item {item.id} held a factory slot past its whole-run wall "
            f"budget; its run was exported and cancelled, it rests at blocked / "
            f"needs-human, and no further dispatch or resume is invoked automatically. "
            f"The cancellation is NOT non-convergence and the slice was not bounced to "
            f"backlog.\n"
        )
    )
