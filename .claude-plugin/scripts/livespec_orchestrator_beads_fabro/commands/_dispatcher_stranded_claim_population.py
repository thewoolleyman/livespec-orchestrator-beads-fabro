"""Which ledger rows the stranded-claim survey grades, and the stamp each one carries.

Split out of `_dispatcher_stranded_claim_survey` by cohesion. That module owns what
becomes of each surveyed claim; this owns WHO is surveyed. A row is a candidate
only when it is `active` or `ready` and still assigned `fabro`, and two markers
take a candidate out again.

A `merge-hold:` LABEL AND AN UNREADABLE HOLD READING TAKE A ROW OUT: surveying a
held item could release a deliberate operator window, and skipping it costs one
pass.

`rework:pending` TAKES A ROW OUT UNLESS IT IS A HANDED-OFF REWORK. A parked rework
(its rework dispatch has not started, or ended without journaling
`merge-wait-handed-off`) is a sanctioned `active` row with no live lock, which is
the exact shape the survey reads as stranded. A HANDED-OFF rework is different: its
run succeeded, its merge wait was handed off, and its disposition is still owed to
the survey, because nothing else performs it once the pull request merges. Which
one a row is comes from the journal alone, and a stamp or a journal that cannot be
read is a parked rework and never a handed-off one.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    ClaimStamp,
    claim_row_for,
    claim_stamps_for,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_current_merge_hold import (
    MergeHoldReader,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_handoff import (
    handed_off_rework_pull_request,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_observe import (
    journal_records_or_none,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    WorkItemNotFoundError,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "ClaimStampReader",
    "claim_stamp",
    "prefetched_claim_stamps",
    "surveyable",
]

_ACTIVE_STATUS = "active"
_READY_STATUS = "ready"
_FABRO_ASSIGNEE = "fabro"
_MERGE_HOLD_UNHELD = "unheld"

_LEDGER_READ_ERRORS: tuple[type[Exception], ...] = (
    WorkItemNotFoundError,
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
)


class ClaimStampReader(Protocol):
    """One item's claim stamp, read from the survey's batch where the batch named it."""

    def __call__(self, *, work_item_id: str) -> ClaimStamp | None:
        """The stamp, or `None` when it could not be read or the row carries none."""
        ...


def prefetched_claim_stamps(*, repo: Path, items: Iterable[WorkItem]) -> ClaimStampReader:
    """A reader that takes the claim candidates' stamps in one `bd show` on first use.

    The candidates are the rows the survey can grade at all: `active` or `ready` and
    assigned `fabro`. A claim the batch could not name, or a batch that could not be
    read, falls back to the single-row read, so a ledger fault is still reported as
    the unreadable stamp it always was. The batch is taken once, ahead of the pass's
    own work, which is safe because no recovery write is decided on it: each one
    re-reads its own row and is fenced on that read.
    """
    candidate_ids = [
        item.id
        for item in items
        if item.status in (_ACTIVE_STATUS, _READY_STATUS) and item.assignee == _FABRO_ASSIGNEE
    ]
    batches: list[dict[str, ClaimStamp | None]] = []

    def stamp_of(*, work_item_id: str) -> ClaimStamp | None:
        if not batches:
            read = attempt(
                action=lambda: claim_stamps_for(
                    path=store_config(repo=repo), work_item_ids=candidate_ids
                ),
                exceptions=_LEDGER_READ_ERRORS,
            )
            batches.append({} if isinstance(read, AttemptFailure) else read)
        if work_item_id in batches[0]:
            return batches[0][work_item_id]
        return claim_stamp(repo=repo, work_item_id=work_item_id)

    return stamp_of


def surveyable(
    *,
    journal_path: Path,
    item: WorkItem,
    merge_hold: MergeHoldReader,
    stamp_of: ClaimStampReader,
) -> bool:
    """Whether the survey grades this row's claim.

    `merge_hold` is the survey's one reader, so the whole-ledger hold reading is
    taken once for the pass and not once for every claim it asks about.
    """
    if item.status not in (_ACTIVE_STATUS, _READY_STATUS) or item.assignee != _FABRO_ASSIGNEE:
        return False
    if item.rework_pending and not _handed_off_rework(
        journal_path=journal_path, item=item, stamp_of=stamp_of
    ):
        return False
    return merge_hold(work_item_id=item.id) == _MERGE_HOLD_UNHELD


def _handed_off_rework(*, journal_path: Path, item: WorkItem, stamp_of: ClaimStampReader) -> bool:
    """Whether this marked row is a rework dispatch that handed its merge wait off.

    Anything this cannot establish is a parked rework and stays unsurveyed: no
    readable stamp names no run to match, and an unreadable journal is an
    unobservable measurement, which is neither answer.
    """
    stamp = stamp_of(work_item_id=item.id)
    if stamp is None or stamp.run_id is None:
        return False
    return (
        handed_off_rework_pull_request(
            records=journal_records_or_none(journal_path=journal_path),
            work_item_id=item.id,
            run_id=stamp.run_id,
        )
        is not None
    )


def claim_stamp(*, repo: Path, work_item_id: str) -> ClaimStamp | None:
    """One item's claim stamp, with every read failure reported as none.

    An unreadable row is reason 1's own wording — "the item carries no READABLE
    run stamp" — so collapsing a ledger fault onto `None` reports the condition
    the clause names rather than inventing a fifteenth.
    """
    row = attempt(
        action=lambda: claim_row_for(path=store_config(repo=repo), work_item_id=work_item_id),
        exceptions=_LEDGER_READ_ERRORS,
    )
    return None if isinstance(row, AttemptFailure) else row.stamp
