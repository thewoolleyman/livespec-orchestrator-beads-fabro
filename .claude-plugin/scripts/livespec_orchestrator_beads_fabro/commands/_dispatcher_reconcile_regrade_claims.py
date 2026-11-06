"""The re-grade arm's claim-changing writes, under the claim-token cutover.

Split from `_dispatcher_reconcile_regrade`, which is at its size ceiling. That
module decides WHAT a passing re-grade does to its item: park it in
`acceptance`, or close it. This one is how each of those ledger writes is made
once `dispatcher.claim_tokens` is true, and what the arm reports when the
claim-token protocol refuses one.

`reconcile-merged --regrade` is an attributed operator act that changes an
item's status, so `SPECIFICATION/contracts.md` ("Claim tokens") makes it a
claim-changing write by a human valve. It is routed like every other one,
through `_intake_valve_claim_writes`.

WHAT THE ARM DECIDED ON. Its preflight admits only an item that carries
`rework:pending`, and it then grades for as long as an acceptance pass takes.
The write it makes afterwards states every fact that decision rested on: the
item still rests at the status the arm read, still carries the marker, is
still assigned as the arm read it, and its claim row is still the one
`regrade_claim` read before the grading began. An item another writer has
moved, unmarked, reassigned or re-stamped in the meantime is not the item the
arm graded, and the write is refused as `claim-changed` without contesting the
token.

WHY THE MARKER AND THE STATUS ARE NOT ENOUGH. A rework re-dispatch
(`_dispatcher_rework_admission.admit_rework`) re-occupies an `active` row that
already holds its slot: it writes no status and no assignee and leaves the
marker in place. A rework run admitted while the arm was grading therefore
leaves status and marker exactly as the arm read them, and an arm that bound
only those two would close or park the item under a live run. What that run
does change is the claim stamp, when it learns its run id. So the arm binds
the whole claim row: status, assignee, and the stamp's dispatch, host, run and
factory.

THE RESIDUAL. Between a rework admission and the moment its dispatch stamps
the run it learned, the ledger row is unchanged: the admission's only record
is a dispatch lock on the admitting host. No predicate over the ledger record
can see that window.

THE ROW IS READ ONLY WHILE THE KEY IS TRUE. Before the cutover the arm makes
no ledger read it did not make before. An arm whose key was not readable as
`true` before it graded has no row to state, so a guarded write it reaches
anyway (the key changed while it graded) is refused as `claim-changed`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from livespec_orchestrator_beads_fabro._beads_client import BeadsRecord
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    ClaimRow,
    claim_row_for,
    claim_row_from_record,
)
from livespec_orchestrator_beads_fabro._store_rework_mutations import LABEL_REWORK_PENDING
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_guard import held
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_writes import (
    claim_tokens_setting,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_lifecycle_writes import (
    write_work_item_status_and_reconcile,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._intake_valve_claim_writes import (
    WRITER_HUMAN_VALVE,
    ClaimWrite,
    resting_at,
)
from livespec_orchestrator_beads_fabro.io import write_stderr
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = ["RegradeClaim", "refused_regrade_outcome", "regrade_claim"]

_FAILED_STATUS = "failed"
_ACCEPTANCE_STATUS = "acceptance"
_PARK_INTENT = "regrade:park"
_CLOSE_INTENT = "regrade:close"


@dataclass(frozen=True, kw_only=True)
class RegradeClaim:
    """The item the arm graded, as it stood before the grading, and the arm's two writes.

    `row` is the item's claim row as `regrade_claim` read it, or `None` when
    the key was not readable as `true` then. The arm's journal rides along, so
    a refused write is journaled once as `claim-write-refused`.
    """

    repo: Path
    item: WorkItem
    journal: JournalFile
    row: ClaimRow | None

    def park(self) -> str | None:
        """Park the item in `acceptance`; `None` when the write landed."""
        return self._disposition(intent=_PARK_INTENT).write_status(
            status=_ACCEPTANCE_STATUS,
            reconcile=True,
            unguarded=lambda: write_work_item_status_and_reconcile(
                path=store_config(repo=self.repo), item_id=self.item.id, status=_ACCEPTANCE_STATUS
            ),
        )

    def hold(self) -> str | None:
        """Win the item's token ahead of the close; `None` when the close may go ahead."""
        return self._disposition(intent=_CLOSE_INTENT).hold()

    def _disposition(self, *, intent: str) -> ClaimWrite:
        return ClaimWrite(
            repo=self.repo,
            path=store_config(repo=self.repo),
            item_id=self.item.id,
            writer=WRITER_HUMAN_VALVE,
            intent=intent,
            still_as_decided=_still_the_graded_item(item=self.item, row=self.row),
            journal=self.journal,
        )


def regrade_claim(*, repo: Path, item: WorkItem, journal: JournalFile) -> RegradeClaim:
    """Read what the arm decides on, before it grades.

    The claim row is read only while `dispatcher.claim_tokens` is `true`:
    before the cutover the arm reads nothing here.
    """
    row = None
    if claim_tokens_setting(repo=repo) is True:
        row = claim_row_for(path=store_config(repo=repo), work_item_id=item.id)
    return RegradeClaim(repo=repo, item=item, journal=journal, row=row)


def _still_the_graded_item(
    *, item: WorkItem, row: ClaimRow | None
) -> Callable[[BeadsRecord], bool]:
    """The predicate "still the marked item the arm read, under the same claim"."""
    marked = resting_at(status=item.status, labels=(LABEL_REWORK_PENDING,))
    assigned = held(status=item.status, assignee=item.assignee)
    return lambda record: (
        row is not None
        and marked(record)
        and assigned(record)
        and claim_row_from_record(record=record) == row
    )


def refused_regrade_outcome(
    *, item: WorkItem, outcome: DispatchOutcome, refusal: str
) -> DispatchOutcome:
    """Report a PASS whose disposition the claim-token protocol refused.

    Nothing was written: the item rests where the arm found it, marker and
    all, so the operator can re-run `--regrade` once the other writer is done.
    The result is the arm's own outcome marked failed, so it keeps the stage
    and the merge facts the arm verified.
    """
    detail = (
        "re-graded PASS, but the claim-token protocol refused the ledger write "
        f"({refusal}); nothing was written"
    )
    _ = write_stderr(
        text=(
            f"SURFACE: work-item {item.id} {detail} against merged PR "
            f"#{outcome.pr_number}. Re-run --regrade.\n"
        )
    )
    return replace(outcome, status=_FAILED_STATUS, detail=detail)
