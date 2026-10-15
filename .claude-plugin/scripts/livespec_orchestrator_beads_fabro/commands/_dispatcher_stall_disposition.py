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

THE COMMENT IS THE DURABLE HALF, and it is required rather than decorative for
the reason `_dispatcher_needs_human_cause` gives at length: the dispatch
journal is a per-clone file and the run record is pruned, so once the
dispatching clone is gone the ledger comment is the ONLY surface still naming
which run was cancelled. A triager deciding whether a kill was genuine needs
the run id, the factory it ran on and the stage it was executing — the three
facts `watchdog-stall-cancel` carries — and a released item with no comment
offers a re-dispatch no way to tell a released stall from work never dispatched
at all.

THE THREE FACTS ARE READ BACK OFF THE JOURNAL RATHER THAN RE-DERIVED. The
cancel site already read them from the run's own record while the run still
existed, which is the one moment they are readable; by the time the disposition
runs the run has been `fabro rm -f`-ed, so re-probing would answer about
nothing and would still succeed. Reading the row the cancel wrote is therefore
not a shortcut — it is the only honest source, and it also keeps the comment
and the journal from describing the same cancellation two ways.

A ROW THE JOURNAL DOES NOT CARRY IS STATED AS UNREAD rather than omitted, for
the reason the cancel record's own unreadable-head arm is: an omission is what a
record written by a build predating this reading looks like, so a comment that
simply left the run unnamed would be indistinguishable from one whose cancel row
could not be found. Both are possible — the journal is a file, and an
interrupted dispatch can end between the cancel and the disposition — and only
the second is a fault.

THE SECOND CANCEL IS A DIFFERENT DISPOSITION, AND THE ROW COUNT IS THE WHOLE
DISCRIMINATOR. One cancellation says nothing about the slice, so it is released.
An item whose FRESH run stalls again is either genuinely unrunnable or is being
killed by something a re-dispatch will meet again, and releasing it a second
time is an unbounded loop with no operator in it — so the second rests at
`blocked` / `needs-human` and nothing automatic leaves that state.

The count is read off the journal's own cancel rows rather than from a stored
per-item counter, because the rows ARE the across-dispatch record: the cancel
site appends exactly one per cancellation, so "how many times has this item been
cancelled" is a question the journal already answers. Note what that does NOT
claim to be. `contracts.md`'s "progress high-water mark" paragraph defines a
CONSECUTIVE NON-PROGRESS COUNT with a committed `dispatcher.redispatch_no_progress_limit`
refusing the next dispatch, and nothing in this repository implements that
mechanism yet — so this routing does not increment it, does not reset it, and
must not be read as having implemented it. A local counter no admission gate
consults would be a field written and never read, which is the
constant-reported-as-a-measurement failure `_dispatcher_non_convergence_cap`'s
own docstring warns about.

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
    "STALL_RELEASE_STAGE",
    "UNREAD_CANCEL_ROW",
    "dispose_stall_cancel",
    "item_stall_cancel_rows",
]

# The journal stage a released first stall appends. One literal, shared by the
# producer here and every reader, exactly as `NON_CONVERGENCE_BOUNCE_STAGE` is.
STALL_RELEASE_STAGE = "stall-cancel-release"

# The journal stage a second consecutive cancel appends. A SEPARATE stage rather
# than a field on the release row, because the two are opposite dispositions and
# a reader filtering for "was this item released" must not match the row that
# parked it.
STALL_NEEDS_HUMAN_STAGE = "stall-cancel-needs-human"

# What the comment says in place of a fact the journal carried no row for. It
# states the MEASUREMENT that failed rather than leaving a blank, because an
# unnamed run and a run whose cancel row could not be read support different
# conclusions and a blank reads as the first.
UNREAD_CANCEL_ROW = "not recorded (this dispatch journalled no cancel row for the item)"

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


def item_stall_cancel_rows(
    *, journal: JournalFile, item_id: str
) -> tuple[Mapping[str, object], ...]:
    """Every `watchdog-stall-cancel` row this journal carries for one item.

    In journal order, which is cancellation order: the cancel site appends one
    row per cancellation, so the last is this dispatch's own and any earlier one
    belongs to a previous dispatch of the same item. That ordering is what makes
    the row count the "first or second cancel" reading Scenario 172 routes on.

    Every read failure yields the EMPTY tuple rather than raising, which is the
    same fail-soft the pre-run claim release takes over the same file: the
    terminal is already final, so a disposition that crashed on an unreadable
    journal would strand the item it was about to release. An empty tuple is
    read as "no row was found", which the comment states as such.
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
        cast("Mapping[str, object]", record)
        for record in records
        if _is_cancel_row(record=record, item_id=item_id)
    )


def dispose_stall_cancel(
    *,
    repo: Path,
    item: WorkItem,
    outcome: DispatchOutcome,
    journal: JournalFile,
) -> None:
    """Route one watchdog cancellation to the disposition its count calls for.

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
    """
    if outcome.status != STALL_STATUS:
        return
    rows = item_stall_cancel_rows(journal=journal, item_id=item.id)
    if len(rows) >= _CONSECUTIVE_CANCELS_THAT_REST:
        _rest_for_human(repo=repo, item=item, journal=journal, rows=rows)
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
            body=_release_comment(item_id=item.id, row=row),
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
            "run_id": _field(row=row, key="run_id"),
            "factory": _field(row=row, key="factory"),
            "executing_stage": _field(row=row, key="executing_stage"),
        }
    )
    _ = write_stderr(
        text=(
            f"SURFACE: work-item {item.id} was released to ready after a stall-watchdog "
            f"cancel of run {_field(row=row, key='run_id')} on factory "
            f"{_field(row=row, key='factory')}; the cancellation is NOT "
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

    The LAST TWO rows are the pair that matters, not the whole history: the
    clause asks for the item's own PRECEDING dispatch and its current one, and
    an item cancelled five times would otherwise have its oldest cancellation
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
            body=_needs_human_comment(item_id=item.id, previous=previous, current=current),
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
            "previous_run_id": _field(row=previous, key="run_id"),
            "run_id": _field(row=current, key="run_id"),
        }
    )
    _ = write_stderr(
        text=(
            f"SURFACE: work-item {item.id} stalled twice in a row — runs "
            f"{_field(row=previous, key='run_id')} and "
            f"{_field(row=current, key='run_id')} were both cancelled by the progress "
            f"watchdog; it rests at blocked / needs-human and no further dispatch or "
            f"resume is invoked automatically.\n"
        )
    )


def _needs_human_comment(
    *,
    item_id: str,
    previous: Mapping[str, object],
    current: Mapping[str, object],
) -> str:
    """The durable account of BOTH cancellations, plus the way out.

    Both runs are named with their factory and stage because that is what tells
    an operator whether the two kills share a cause: the same factory twice
    points at the host, the same stage twice points at a false kill inside one
    open command node, and two unrelated stages point at the work.

    The REMEDY is spelled as the valve rather than described, and the wording is
    the resume ladder's own `resolve-blocked` clause, so the comment and the
    refusal an operator meets next cannot say two different things. The
    plain-dispatch line is the second applicable remedy: a cancel record whose
    published head could not be read cannot anchor a resume, which is the
    ladder's headless refusal, and its remedy is a plain dispatch.
    """
    return "\n".join(
        (
            "livespec-stall-cancel-needs-human",
            "",
            f"work-item: {item_id}",
            _run_line(label="preceding cancelled run", row=previous),
            _run_line(label="current cancelled run", row=current),
            "",
            "This item stalled twice in a row, so it rests at blocked /",
            "needs-human and no further dispatch or resume is invoked",
            "automatically. A stall cancel is still NOT factory non-convergence:",
            "the item was not bounced to backlog and no slice-size calibration",
            "observation was recorded for either run.",
            "",
            "Remedies:",
            f"- release it with `resolve-blocked:{item_id}:ready`, which is the",
            "  only route out of blocked and what the resume refusal ladder names",
            "  for an item resting on a human decision.",
            "- if a resume then refuses because no record names a publish-branch",
            "  head, dispatch it plainly instead; a cancel record whose published",
            "  head could not be read cannot anchor a resume.",
        )
    )


def _run_line(*, label: str, row: Mapping[str, object]) -> str:
    """One cancelled run named with the three facts that locate it.

    The run, its factory and the stage it was executing travel together on one
    line because they are read together: the same factory twice points at the
    host, the same stage twice at a false kill inside one open command node,
    and two unrelated stages at the work itself.
    """
    run_id = _field(row=row, key="run_id")
    factory = _field(row=row, key="factory")
    stage = _field(row=row, key="executing_stage")
    return f"{label}: {run_id} on factory {factory}, executing {stage}"


def _release_comment(*, item_id: str, row: Mapping[str, object] | None) -> str:
    """The durable account of the cancellation, as the ledger will keep it.

    Labelled `livespec-stall-cancel-release` so it is greppable beside the
    `livespec-needs-human-cause` and `livespec-preserve-by-reference` records
    an operator already reads on a parked item. Plain lines rather than a
    fenced block, for the reason the proof-attachment renderer gives: a fenced
    body is invisible to the surfaces that scan a record's own lines.
    """
    return "\n".join(
        (
            "livespec-stall-cancel-release",
            "",
            f"work-item: {item_id}",
            f"cancelled run id: {_field(row=row, key='run_id')}",
            f"factory: {_field(row=row, key='factory')}",
            f"stage the run was executing: {_field(row=row, key='executing_stage')}",
            "",
            "A stall-watchdog cancel is NOT factory non-convergence, so this item",
            "was not bounced to backlog. The dispatch claim was released and the",
            "item returned to ready; the ordinary admission valve will pick it up.",
            "Triage the cancelled run above before assuming the slice is at fault:",
            "a hang, a per-container OOM kill and a false kill inside an open",
            "command node all end this way, and none of them is a verdict about",
            "the work.",
        )
    )


def _field(*, row: Mapping[str, object] | None, key: str) -> str:
    """One fact off the cancel row, or the statement that no row carried it.

    A row present but holding a null or a non-string value reports the same
    statement as an absent row, because both are the same finding: this
    dispatch's journal does not say. Rendering a bare `None` into the comment
    would put the word "None" where an operator expects a run id.
    """
    if row is None:
        return UNREAD_CANCEL_ROW
    value: object = row.get(key)
    if isinstance(value, str) and value.strip():
        return value
    return UNREAD_CANCEL_ROW


def _is_cancel_row(*, record: object, item_id: str) -> bool:
    """Whether this record is a cancel row for the item under disposition."""
    if not isinstance(record, dict):
        return False
    values = cast("Mapping[str, object]", record)
    return values.get("stage") == STALL_CANCEL_STAGE and values.get("work_item_id") == item_id
