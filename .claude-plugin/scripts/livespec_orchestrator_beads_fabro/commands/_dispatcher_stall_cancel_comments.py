"""What a stall-watchdog cancellation says on the ledger, as the ledger keeps it.

Split out of `_dispatcher_stall_disposition` by cohesion once the replay guards
pushed that file past its LLOC ceiling. The disposition decides WHICH route one
cancellation takes and performs the ledger and journal writes; this renders the
durable prose each route leaves behind, and it is PURE, so every word is
assertable without a tenant and without a journal.

THE COMMENT IS THE DURABLE HALF of either disposition, and it is required rather
than decorative for the reason `_dispatcher_needs_human_cause` gives at length:
the dispatch journal is a per-clone file and the run record is pruned, so once
the dispatching clone is gone the ledger comment is the ONLY surface still
naming which run was cancelled. A triager deciding whether a kill was genuine
needs the run id, the factory it ran on and the stage it was executing — the
three facts `watchdog-stall-cancel` carries — and a released item with no
comment offers a re-dispatch no way to tell a released stall from work never
dispatched at all.

A FACT THE JOURNAL DOES NOT CARRY IS STATED AS UNREAD rather than omitted, for
the reason the cancel record's own unreadable-head arm is: an omission is what a
record written by a build predating this reading looks like, so a comment that
simply left the run unnamed would be indistinguishable from one whose cancel row
could not be found. Both are possible — the journal is a file, and an
interrupted dispatch can end between the cancel and the disposition — and only
the second is a fault.
"""

from __future__ import annotations

from collections.abc import Mapping

__all__: list[str] = [
    "UNREAD_CANCEL_ROW",
    "cancel_row_field",
    "needs_human_comment",
    "release_comment",
]

# What the comment says in place of a fact the journal carried no row for. It
# states the MEASUREMENT that failed rather than leaving a blank, because an
# unnamed run and a run whose cancel row could not be read support different
# conclusions and a blank reads as the first.
UNREAD_CANCEL_ROW = "not recorded (this dispatch journalled no cancel row for the item)"


def needs_human_comment(
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
    run_id = cancel_row_field(row=row, key="run_id")
    factory = cancel_row_field(row=row, key="factory")
    stage = cancel_row_field(row=row, key="executing_stage")
    return f"{label}: {run_id} on factory {factory}, executing {stage}"


def release_comment(*, item_id: str, row: Mapping[str, object] | None) -> str:
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
            f"cancelled run id: {cancel_row_field(row=row, key='run_id')}",
            f"factory: {cancel_row_field(row=row, key='factory')}",
            _executing_line(row=row),
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


def _executing_line(*, row: Mapping[str, object] | None) -> str:
    """The release comment's stage line, which is too long to render inline."""
    stage = cancel_row_field(row=row, key="executing_stage")
    return f"stage the run was executing: {stage}"


def cancel_row_field(*, row: Mapping[str, object] | None, key: str) -> str:
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
