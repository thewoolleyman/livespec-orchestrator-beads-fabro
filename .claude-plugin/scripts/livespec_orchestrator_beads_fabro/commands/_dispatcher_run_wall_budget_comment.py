"""What a wall-budget cancel says on the ledger, as the ledger keeps it.

The PURE half of the budget disposition pair: that module decides the route and
performs the ledger and journal writes, and this renders the durable prose it
leaves behind, so every word is assertable without a tenant and without a
journal.

THE COMMENT IS THE DURABLE HALF, and it is required rather than decorative for
the reason `_dispatcher_stall_cancel_comments` gives at length: the dispatch
journal is a per-clone file and the run record is pruned, so once the
dispatching clone is gone the ledger comment is the ONLY surface still naming
which run was cancelled, how long it had held its slot, and where its tree was
preserved. A budget-rested item with no comment offers a person nothing to
decide with -- and nothing automatic leaves that state, so there is no later
pass to supply it.

THE REMEDY IS SPELLED AS THE VALVE rather than described, and the wording is the
resume ladder's own `resolve-blocked` clause, so the comment and the refusal an
operator meets next cannot say two different things.

A FACT THE JOURNAL DOES NOT CARRY IS STATED AS UNREAD rather than omitted, which
is why `cancel_row_field` is imported rather than re-written: an omission is what
a record written by a build predating this reading looks like, so a comment that
simply left the run unnamed would be indistinguishable from one whose row could
not be found -- and both are possible, because an interrupted dispatch can end
between the cancel and the disposition.

THE PUBLICATION IS REPORTED IN THREE DISTINGUISHABLE STATES, never as a
silence. A run that completed a `publish_draft` names its pull request and the
head it pushed; one whose head could not be read carries the record's own
statement of that; and one that published nothing says so. A comment that
simply omitted the lines would read identically in all three -- and the
recoveries differ, because the resume ladder's remedy for no head is a PLAIN
dispatch, which reclaims the publish branch and deletes the very head nobody
could name.

Those two surfaces state the unreadable head with ONE literal,
`UNREADABLE_PUBLISHED_HEAD`, imported rather than reworded: the clause binds the
budget record to the stall record's rules for the published head, and two
wordings would let one cancel class advise an act the other did not.

TWO OF THE FACTS ARE NUMBERS, AND THAT NEEDS ITS OWN READER. `cancel_row_field`
admits STRING values only, deliberately: every fact the stall comment names is
an identifier, so a non-string there is a row this build cannot read. The
elapsed seconds and the budget are the measurement itself, and a string-only
reader reports BOTH of them as unread on a perfectly well-formed row -- which is
the one failure this comment cannot afford, because the measurement is the whole
justification for the cancellation it is explaining. `_measured_field` therefore
renders a number as its figure and falls through to the shared statement for
everything else, `bool` included: `True` is an `int` in Python and would render
as a one-second budget.
"""

from __future__ import annotations

from collections.abc import Mapping

from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_cancel_comments import (
    UNREAD_CANCEL_ROW,
    cancel_row_field,
)

__all__: list[str] = [
    "RUN_WALL_BUDGET_COMMENT_MARKER",
    "run_wall_budget_comment",
]

# Labelled so it is greppable beside the `livespec-needs-human-cause`,
# `livespec-stall-cancel-needs-human` and `livespec-preserve-by-reference`
# records an operator already reads on a parked item.
RUN_WALL_BUDGET_COMMENT_MARKER = "livespec-run-wall-budget-exceeded"


def run_wall_budget_comment(*, item_id: str, row: Mapping[str, object] | None) -> str:
    """The durable account of one budget cancel, plus the way out.

    Plain lines rather than a fenced block, for the reason the proof-attachment
    renderer gives: a fenced body is invisible to the surfaces that scan a
    record's own lines.

    The MEASUREMENT is named beside the BUDGET because the budget alone cannot
    be checked -- it says what the threshold was and never that anything reached
    it -- and the LAYER is named beside both because 21600 seconds is the fleet
    default on one target and a deliberate override on another: only the layer
    tells a person whether raising the key would have saved this run.
    """
    return "\n".join(
        (
            RUN_WALL_BUDGET_COMMENT_MARKER,
            "",
            f"work-item: {item_id}",
            f"cancelled run id: {cancel_row_field(row=row, key='run_id')}",
            f"factory: {cancel_row_field(row=row, key='factory')}",
            f"stage the run was executing: {cancel_row_field(row=row, key='executing_stage')}",
            f"slot-holding seconds: {_measured_field(row=row, key='elapsed_seconds')}",
            f"whole-run wall budget seconds: {_measured_field(row=row, key='budget_seconds')}",
            f"budget supplied by layer: {cancel_row_field(row=row, key='budget_layer')}",
            f"preserve-by-reference pointer: {cancel_row_field(row=row, key='preserved_pointer')}",
            *_publication_lines(row=row),
            "",
            "This run held a factory slot past its whole-run wall budget, so its",
            "record was exported and read back and the run was then cancelled to",
            "release the slot. A budget cancel is NOT factory non-convergence:",
            "the item was not bounced to backlog, no non-convergence observation",
            "was recorded, and its across-dispatch progress count is unchanged.",
            "",
            "Remedies:",
            f"- release it with `resolve-blocked:{item_id}:ready`, which is the",
            "  only route out of blocked and what the resume refusal ladder names",
            "  for an item resting on a human decision.",
            "- read the preserve-by-reference pointer above before re-dispatching:",
            "  it names the factory and the run the cancelled tree was exported",
            "  from, which is what a re-dispatch from preserved work reads.",
        )
    )


def _measured_field(*, row: Mapping[str, object] | None, key: str) -> str:
    """One MEASURED figure off the cancel row, or the statement that it is unread.

    Rendered without a trailing `.0`, because the journal carries these as
    floats while every resolved budget and every whole-second measurement is an
    integer count: a comment reading `21600.0 seconds` invites a reader to
    wonder what the fraction means.

    `bool` is excluded explicitly for the reason `positive_int_seconds` excludes
    it: it is an `int` subclass, so a row carrying `true` would render as a
    one-second budget rather than as the unreadable value it is.
    """
    value: object = None if row is None else row.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        return cancel_row_field(row=row, key=key)
    return f"{value:g}"


def _publication_lines(*, row: Mapping[str, object] | None) -> tuple[str, ...]:
    """What this cancelled run published, in whichever of the three states it is.

    The states are kept apart because they support different recoveries, and
    the module docstring records what collapsing them costs. An UNREAD row is a
    fourth state and is reported as such: a dispatch that journalled no cancel
    row has not established that the run published nothing.
    """
    if row is None:
        return (f"publication: {UNREAD_CANCEL_ROW}",)
    unreadable: object = row.get("published_head_unreadable")
    if isinstance(unreadable, str) and unreadable.strip():
        return (
            f"published pull request: {_measured_field(row=row, key='pull_request')}",
            f"published head: {unreadable}",
        )
    if row.get("pull_request") is None and row.get("published_head") is None:
        return ("publication: this run completed no publish_draft",)
    return (
        f"published pull request: {_measured_field(row=row, key='pull_request')}",
        f"published head: {cancel_row_field(row=row, key='published_head')}",
    )
