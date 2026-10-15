"""Where a stall-watchdog cancel leaves its work-item.

`SPECIFICATION/scenarios.md` "Scenario 172 — A stall-watchdog cancel is never
non-convergence" and the `contracts.md` section "Dispatcher progress watchdog"
paragraph "A first stall cancel is released and recovered" govern this module.
It is the REPLACEMENT disposition for the `backlog` bounce that
`is_non_convergence_outcome` used to drive, and it has to exist for the same
reason that removal was correct: a cancellation is not a verdict about the
slice, so the slice goes back to the queue rather than back to intake.

WITHOUT THIS THE REMOVAL IS A REGRESSION, WHICH IS WHY THE TWO BELONG TOGETHER.
`release_pre_run_claim_if_needed` releases only a pre-run failure — it requires
`fabro_run_id is None`, and a cancelled run has one — and
`escalate_needs_human_block` fires only on a `blocked` terminal, which a
`stalled-no-progress` status is not. So with the bounce gone and nothing in its
place, a cancelled item rests `active` with `fabro` still assigned and no run
behind it: invisible to admission, invisible to `next`, and indistinguishable
at a glance from work that is genuinely in flight. That is a worse end state
than the wrong `backlog` bounce it replaces, because a bounced item is at least
selectable.

THE COMMENT EACH ROUTE WRITES LIVES IN `_dispatcher_stall_cancel_comments`,
which is the PURE half of this pair and carries why the comment is the durable
record and why an unreadable fact is stated rather than omitted.

THE THREE FACTS ARE READ BACK OFF THE JOURNAL RATHER THAN RE-DERIVED. The
cancel site already read them from the run's own record while the run still
existed, which is the one moment they are readable; by the time the disposition
runs the run has been `fabro rm -f`-ed, so re-probing would answer about
nothing and would still succeed. Reading the row the cancel wrote is therefore
not a shortcut — it is the only honest source, and it also keeps the comment
and the journal from describing the same cancellation two ways.

THE SECOND CANCEL IS A DIFFERENT DISPOSITION, AND THE DISCRIMINATOR IS THE
ITEM'S PRECEDING DISPATCH — NOT HOW MANY TIMES IT HAS EVER BEEN CANCELLED. One
cancellation says nothing about the slice, so it is released. An item whose
FRESH run stalls again is either genuinely unrunnable or is being killed by
something a re-dispatch will meet again, and releasing it a second time is an
unbounded loop with no operator in it — so the second rests at `blocked` /
`needs-human` and nothing automatic leaves that state.

A LIFETIME COUNT ANSWERS A DIFFERENT QUESTION, AND THE TWO DIVERGE ON A SEQUENCE
THIS VERY ITEM DEMONSTRATES. Scenario 172 gives the release arm "the item's
preceding dispatch did not end stalled-no-progress" and the needs-human arm "an
item whose preceding dispatch ended stalled-no-progress", and the two contract
paragraphs above say IMMEDIATELY preceding. So a stall, a release to `ready`, a
re-dispatch that ends needs-human on a provider session limit, a human
`resolve-blocked:<id>:ready`, and then a stall leaves TWO cancel rows standing
while the clause calls for a release: a lifetime count parks the item and
`_dispatcher_stall_cancel_comments` writes the durable claim that it "stalled
twice in a row", which is false on that path and which `bd` offers no way to
edit or delete afterwards.

THE RESET IS READ OFF THE TERMINAL ROWS THE JOURNAL ALREADY CARRIES, so the
reading needs no counter and no second data source: `post_run_dispositions`
appends an `outcome` row for EVERY terminal before calling this, so the
cancellations belonging to the item's current unbroken run of non-progress are
exactly the cancel rows following its last terminal that did not stall. Those
rows ARE the across-dispatch record — the cancel site appends exactly one per
cancellation — which is why no per-item counter is stored beside them. Note what
that does NOT claim to be. `contracts.md`'s "progress high-water mark" paragraph
defines a CONSECUTIVE NON-PROGRESS COUNT with a committed
`dispatcher.redispatch_no_progress_limit` refusing the next dispatch, and nothing
in this repository implements that mechanism yet — so this routing does not
increment it, does not reset it, and must not be read as having implemented it.
A local counter no admission gate consults would be a field written and never
read, which is the constant-reported-as-a-measurement failure
`_dispatcher_non_convergence_cap`'s own docstring warns about.

THE LEDGER WRITE IS FAIL-SOFT and the comment is written BEFORE it, which is the
opposite order from `_dispatcher_loop_selection`'s needs-human pair and is
deliberate. There the escalation owns the lifecycle write and the comment owns
only the account, so a comment written first would explain a block that never
landed. Here the comment is what SURVIVES: a release whose ledger write failed
leaves the item `active`, which an operator can see and move by hand, while a
lost comment leaves nobody able to name the run — so the record that outlives
the dispatch is taken first.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro._store_blocked_mutations import (
    update_work_item_blocked_state,
)
from livespec_orchestrator_beads_fabro._store_comments import append_work_item_comment
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_cancel_comments import (
    cancel_row_field,
    needs_human_comment,
    release_comment,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_cancel_record import (
    STALL_CANCEL_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_telemetry import STALL_STATUS
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    WorkItemNotFoundError,
)
from livespec_orchestrator_beads_fabro.io import write_stderr
from livespec_orchestrator_beads_fabro.store import update_work_item_status
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "STALL_NEEDS_HUMAN_STAGE",
    "STALL_RELEASE_HELD_STAGE",
    "STALL_RELEASE_STAGE",
    "consecutive_stall_cancel_rows",
    "dispose_stall_cancel",
]

# The journal stage a released first stall appends. One literal, shared by the
# producer here and every reader, exactly as `NON_CONVERGENCE_BOUNCE_STAGE` is.
STALL_RELEASE_STAGE = "stall-cancel-release"

# The journal stage a second consecutive cancel appends. A SEPARATE stage rather
# than a field on the release row, because the two are opposite dispositions and
# a reader filtering for "was this item released" must not match the row that
# parked it.
STALL_NEEDS_HUMAN_STAGE = "stall-cancel-needs-human"

# The journal stage a replay appends when it declines to perform the release.
# Its own stage rather than a field on the release row, for the same reason the
# needs-human terminal has one: a reader asking "was this item released" must
# not match the row that says it deliberately was not.
STALL_RELEASE_HELD_STAGE = "stall-cancel-release-held"

# The two reasons a release is held, each naming the reading that stopped it.
# They are kept apart because they have different consequences: the first says
# the release already happened and nothing is owed, while the second says a
# release IS owed and could not be taken now without damaging a live dispatch.
_HELD_ALREADY_RELEASED = "already-released"
_HELD_NEWER_DISPATCH_CLAIM = "newer-dispatch-claim"

# The journal stage a dispatch writes to announce itself. Spelled here rather
# than imported, because the writer keeps it private; the hold reading only
# needs to RECOGNISE the row, and the name is part of the ratified record set.
_DISPATCH_ID_STAGE = "dispatch-id"

# The journal stage every terminal writes, spelled here for the same reason.
# Its row is shaped UNLIKE every other row this module reads: the terminal's own
# fields — `work_item_id` among them — sit NESTED under an `outcome` key rather
# than beside `stage`, because `post_run_dispositions` appends the whole
# dataclass as one value. A reading that looked for `work_item_id` at the top
# level, as `_names` correctly does for every other stage, would match no
# terminal at all and would report every item as never having finished one.
_OUTCOME_STAGE = "outcome"

# How many cancellations an item may collect before it stops being released. The
# SECOND one is the terminal, so this is the count at which the release arm
# yields to the needs-human arm rather than a tunable tolerance.
_CONSECUTIVE_CANCELS_THAT_REST = 2

_LEDGER_WRITE_ERRORS = (
    WorkItemNotFoundError,
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
)


def consecutive_stall_cancel_rows(
    *, journal: JournalFile, item_id: str
) -> tuple[Mapping[str, object], ...]:
    """The cancel rows of the item's current UNBROKEN run of non-progress.

    In journal order, which is cancellation order: the cancel site appends one
    row per cancellation, so the last is this dispatch's own and an earlier one
    belongs to a previous dispatch of the same item. The run is CUT at the
    item's last terminal that did not stall, which is what makes the row count
    the "did the PRECEDING dispatch also stall" reading Scenario 172 routes on
    rather than the lifetime count that answers a different question. On a
    journal holding nothing but this item's cancellations the two agree, which
    is why the simple history could not tell them apart.

    A terminal row this reading cannot ATTRIBUTE to the item leaves the run
    unbroken, while one it can attribute but whose status it cannot read as the
    stall status BREAKS it. The two are opposite directions on purpose: the
    first is a failure to establish whose terminal it was, so it says nothing
    about this item, whereas the second is this item's terminal and the rest arm
    is conditioned on a POSITIVE reading that the preceding dispatch also
    stalled. An unreadable status therefore releases rather than parking, which
    is the fail-soft direction `dispose_stall_cancel` documents throughout.

    Every read failure yields the EMPTY tuple rather than raising, which is the
    same fail-soft the pre-run claim release takes over the same file: the
    terminal is already final, so a disposition that crashed on an unreadable
    journal would strand the item it was about to release. An empty tuple is
    read as "no row was found", which the comment states as such.
    """
    records = _journal_records(journal=journal)
    ended_without_stalling = [
        index
        for index, record in enumerate(records)
        if _ends_a_dispatch_without_stalling(record=record, item_id=item_id)
    ]
    consecutive_from = ended_without_stalling[-1] + 1 if ended_without_stalling else 0
    return tuple(
        record
        for record in records[consecutive_from:]
        if _names(record=record, item_id=item_id, stage=STALL_CANCEL_STAGE)
    )


def _ends_a_dispatch_without_stalling(*, record: Mapping[str, object], item_id: str) -> bool:
    """Whether this record is a terminal of the item that is not a stall."""
    if record.get("stage") != _OUTCOME_STAGE:
        return False
    nested: object = record.get("outcome")
    if not isinstance(nested, Mapping):
        return False
    terminal = cast("Mapping[str, object]", nested)
    if terminal.get("work_item_id") != item_id:
        return False
    return terminal.get("status") != STALL_STATUS


def _journal_records(*, journal: JournalFile) -> tuple[Mapping[str, object], ...]:
    """Every mapping record the journal file holds, in append order.

    Append order is what both readings above it depend on: the cancel rows are
    counted in cancellation order, and the hold reading asks what the journal
    recorded AFTER a particular cancellation. A record that is not a mapping is
    dropped rather than raising, for the same reason every read failure yields
    the empty tuple — a disposition that crashed on one malformed line would
    strand the item it was about to release.
    """
    read = attempt(action=lambda: journal.path.read_text(encoding="utf-8"), exceptions=(OSError,))
    if isinstance(read, AttemptFailure):
        return ()
    parsed = attempt(
        action=lambda: [json.loads(line) for line in read.splitlines()], exceptions=(ValueError,)
    )
    if isinstance(parsed, AttemptFailure):
        return ()
    records = cast("list[object]", parsed)
    return tuple(
        cast("Mapping[str, object]", record) for record in records if isinstance(record, dict)
    )


def _release_hold_reason(*, journal: JournalFile, item_id: str) -> str | None:
    """Why this cancellation's release must not be performed now, if it must not.

    The release is keyed by the CANCELLATION — the contract's "keyed by factory
    and run" — so the question is settled by what the journal recorded after the
    item's last cancel row, and the two readings it takes are not one reading
    twice. A release row there says the release already landed, so a second pass
    owes nothing. A `dispatch-id` row there says a LATER dispatch has since
    claimed the item, so the claim now standing is not the one this cancellation
    released: performing the release would hand a live run's claim back to the
    queue, and the resulting row is byte-identical to a correct first release,
    so nothing downstream could tell the two apart.

    A journal carrying NO cancel row for the item holds nothing, which keeps the
    fail-soft direction `dispose_stall_cancel` documents: without a cancel row
    there is no "after" to read, so the newer-claim question has not been
    answered either way, and the one dispatch most likely to have left the item
    stranded is exactly the one whose record went missing.
    """
    records = _journal_records(journal=journal)
    cancelled_at = [
        index
        for index, record in enumerate(records)
        if _names(record=record, item_id=item_id, stage=STALL_CANCEL_STAGE)
    ]
    if not cancelled_at:
        return None
    following = records[cancelled_at[-1] + 1 :]
    if any(
        _names(record=record, item_id=item_id, stage=STALL_RELEASE_STAGE) for record in following
    ):
        return _HELD_ALREADY_RELEASED
    if any(
        _names(record=record, item_id=item_id, stage=_DISPATCH_ID_STAGE) for record in following
    ):
        return _HELD_NEWER_DISPATCH_CLAIM
    return None


def dispose_stall_cancel(
    *,
    repo: Path,
    item: WorkItem,
    outcome: DispatchOutcome,
    journal: JournalFile,
) -> None:
    """Route one watchdog cancellation by whether the PRECEDING dispatch stalled.

    A no-op for every outcome that is not a watchdog cancellation, which is
    every green run, every ordinary failure and every human-gate park. The
    status is the whole discriminator and no journal correlation is needed to
    identify one: `_dispatcher_engine_journal.stalled_outcome` is the single
    writer of `STALL_STATUS` and it writes it only after the run was
    `fabro rm -f`-ed.

    A journal carrying NO cancel row routes to the RELEASE arm rather than
    refusing, which is deliberate and is the fail-soft direction here. An
    interrupted dispatch can end between the cancel and the disposition, and
    those are exactly the dispatches most likely to have left the item
    stranded; parking an item for a human because its own account could not be
    read would turn a lost record into an operator interrupt.

    THE WHOLE ROUTING IS REPLAYABLE, which is what lets reconciliation finish an
    interrupted release by running it again: the release arm is held whenever
    the journal already records it landing, or records a LATER dispatch claiming
    the item. Both holds are journaled rather than silent, because a replay that
    did nothing and said nothing is indistinguishable from one that never ran.
    """
    if outcome.status != STALL_STATUS:
        return
    rows = consecutive_stall_cancel_rows(journal=journal, item_id=item.id)
    if len(rows) >= _CONSECUTIVE_CANCELS_THAT_REST:
        _rest_for_human(repo=repo, item=item, journal=journal, rows=rows)
        return
    held = _release_hold_reason(journal=journal, item_id=item.id)
    if held is not None:
        journal.append(
            record={
                "stage": STALL_RELEASE_HELD_STAGE,
                "work_item_id": item.id,
                "reason": held,
            }
        )
        return
    _release_first_cancel(repo=repo, item=item, journal=journal, row=rows[-1] if rows else None)


def _release_first_cancel(
    *,
    repo: Path,
    item: WorkItem,
    journal: JournalFile,
    row: Mapping[str, object] | None,
) -> None:
    """Return the item to `ready` with its dispatch claim dropped.

    The claim is released through the SAME seam the pre-run release uses —
    `status="ready"` with `clear_assignee=True` — so a released stall and a
    released pre-run failure leave the ledger in one shape rather than two that
    merely look alike. A `ready` item carries no dispatcher blocked-reason
    label, so no reason has to be cleared: the item was `active`, which is a
    status the escalation seam never writes a reason onto.
    """
    _ = attempt(
        action=lambda: append_work_item_comment(
            path=store_config(repo=repo),
            work_item_id=item.id,
            body=release_comment(item_id=item.id, row=row),
        ),
        exceptions=_LEDGER_WRITE_ERRORS,
    )
    released = attempt(
        action=lambda: update_work_item_status(
            path=store_config(repo=repo),
            item_id=item.id,
            status="ready",
            clear_assignee=True,
        ),
        exceptions=_LEDGER_WRITE_ERRORS,
    )
    if isinstance(released, AttemptFailure):
        journal.append(
            record={
                "stage": f"{STALL_RELEASE_STAGE}-error",
                "work_item_id": item.id,
                "reason": f"{type(released.error).__name__}",
            }
        )
        return
    journal.append(
        record={
            "stage": STALL_RELEASE_STAGE,
            "work_item_id": item.id,
            "status": "ready",
            "run_id": cancel_row_field(row=row, key="run_id"),
            "factory": cancel_row_field(row=row, key="factory"),
            "executing_stage": cancel_row_field(row=row, key="executing_stage"),
        }
    )
    _ = write_stderr(
        text=(
            f"SURFACE: work-item {item.id} was released to ready after a stall-watchdog "
            f"cancel of run {cancel_row_field(row=row, key='run_id')} on factory "
            f"{cancel_row_field(row=row, key='factory')}; the cancellation is NOT "
            f"non-convergence and the slice was not bounced to backlog.\n"
        )
    )


def _rest_for_human(
    *,
    repo: Path,
    item: WorkItem,
    journal: JournalFile,
    rows: tuple[Mapping[str, object], ...],
) -> None:
    """Park the item at `blocked` / `needs-human` on a repeat cancellation.

    The LAST TWO rows are the pair that matters, not the whole run: the clause
    asks for the item's own PRECEDING dispatch and its current one, and an item
    cancelled five times in a row would otherwise have its oldest cancellation
    reported as the one a re-dispatch is being judged against.

    `admission_policy="manual"` rides the same write for the same reason
    `escalate_needs_human_block` carries it: `blocked` alone is a status the
    drain could still be configured to admit, and the point of this terminal is
    that no further dispatch happens without a human.
    """
    previous, current = rows[-2], rows[-1]
    _ = attempt(
        action=lambda: append_work_item_comment(
            path=store_config(repo=repo),
            work_item_id=item.id,
            body=needs_human_comment(item_id=item.id, previous=previous, current=current),
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
                "stage": f"{STALL_NEEDS_HUMAN_STAGE}-error",
                "work_item_id": item.id,
                "reason": f"{type(rested.error).__name__}",
            }
        )
        return
    journal.append(
        record={
            "stage": STALL_NEEDS_HUMAN_STAGE,
            "work_item_id": item.id,
            "status": "blocked",
            "blocked_reason": "needs-human",
            "previous_run_id": cancel_row_field(row=previous, key="run_id"),
            "run_id": cancel_row_field(row=current, key="run_id"),
        }
    )
    _ = write_stderr(
        text=(
            f"SURFACE: work-item {item.id} stalled twice in a row — runs "
            f"{cancel_row_field(row=previous, key='run_id')} and "
            f"{cancel_row_field(row=current, key='run_id')} were both cancelled by the progress "
            f"watchdog; it rests at blocked / needs-human and no further dispatch or "
            f"resume is invoked automatically.\n"
        )
    )


def _names(*, record: Mapping[str, object], item_id: str, stage: str) -> bool:
    """Whether this record is the named stage, written for the named item."""
    return record.get("stage") == stage and record.get("work_item_id") == item_id
