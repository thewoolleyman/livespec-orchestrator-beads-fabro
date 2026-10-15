"""The one journal record a `stalled-no-progress` watchdog cancel writes.

`SPECIFICATION/contracts.md` section "Dispatcher progress watchdog" -> "The
cancel record" enumerates what it MUST name: the work-item, the dispatch id,
the run id, the factory, and the stage the run was executing — plus, when the
run completed a `publish_draft`, the pull request and the head that publication
pushed. This module renders it, and it is PURE, so every field is assertable
without a factory and without a journal.

WHY THE RECORD IS THIS WIDE, when the row before it carried only the work-item,
the run id and the three stall-window figures. A cancellation is read by three
different readers and each needs a different half of it. An operator triaging a
false kill needs the STAGE, because the whole false-kill class is a cancel
inside an open command node (`bd-ib-qsk4o5`) and the stage is the only field
that distinguishes it from a genuinely quiet run. A resume needs the PULL
REQUEST and the HEAD, because the "A first stall cancel is released and
recovered" paragraph makes this record a resume anchor. And anyone correlating
the cancellation with the run's own telemetry needs the DISPATCH ID and the
FACTORY, because the dispatch id is what selects this dispatch's spans and
commit series and the factory is what says which host's run history to look in
— neither of which is recoverable from the other fields, and the factory
especially not, since this fleet routinely runs two factories on different
builds.

EVERY KEY IS WRITTEN ON EVERY CANCEL, nulls included. An omitted key is exactly
what a record from a build predating this renderer looks like, so a reader
could not tell "this run published nothing" from "this build was never asked" —
the same reason `_dispatcher_sandbox_image_source` writes all three of its keys
on every launch.

AND THE UNREADABLE HEAD IS STATED IN WORDS rather than left as a bare null. The
clause requires that when the head "cannot be read, the record MUST say so
rather than omit it", and the reason is that `published_head: null` on a record
that DOES name a pull request is ambiguous in the EXPENSIVE direction. It reads
as "this run published nothing" to a resume, whose remedy for no head is a plain
dispatch — and a plain dispatch reclaims the publish branch, preserving the dead
run's head to a ref and deleting the branch, so the one thing an unreadable head
must not do is advise the act that destroys the publication nobody could name.

`published_head_unreadable` therefore carries the statement, and it is present
ONLY on the arm that MEASURED a publication without a head. An unpublished run
reports null there, because nothing about it was unreadable: a statement on that
arm would claim a failed measurement where none was attempted, which is the
mirror-image error — a diagnostic reported as a finding.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_run_reading import (
    StallPublication,
)

__all__: list[str] = [
    "STALL_CANCEL_STAGE",
    "UNREADABLE_PUBLISHED_HEAD",
    "stall_cancel_record",
]

# The journal stage. One literal, shared by this producer and every reader —
# the resume anchor, the stall disposition and an operator's `grep`.
STALL_CANCEL_STAGE = "watchdog-stall-cancel"

# The statement the record carries in place of a head it could not read. It
# names the NODE whose push is unaccounted for, because that is what tells an
# operator where to look: a `publish_draft` whose head is unknown still has a
# pull request whose head can be read by hand. And it states the CONSEQUENCE —
# that this record cannot anchor a resume — because the resume refusal ladder
# computes that same conclusion from the absent head, and a record that reported
# only the absence leaves the reader to re-derive it.
UNREADABLE_PUBLISHED_HEAD = (
    "the head this run's last completed publish_draft pushed could not be read "
    "from the run's own record, so this record cannot anchor a resume"
)


def stall_cancel_record(
    *,
    work_item_id: str,
    dispatch_id: str | None,
    run_id: str,
    factory: str,
    executing_stage: str | None,
    publication: StallPublication | None,
) -> dict[str, object]:
    """Render the cancel record's identifying half.

    The caller merges the stall-window figures it measured onto this — the
    resolved window, the layer that supplied it, the quiet duration confirmed
    and the `fabro rm` exit code — because those are facts about the DECISION
    while these are facts about the RUN, and only the caller holds both.

    `dispatch_id` is optional because the launcher is wired with one only when
    the dispatch minted one; a null there is an honest "this launch carried no
    dispatch id", which is distinguishable from an id nobody wrote down.
    """
    return {
        "stage": STALL_CANCEL_STAGE,
        "work_item_id": work_item_id,
        "dispatch_id": dispatch_id,
        "run_id": run_id,
        "factory": factory,
        "executing_stage": executing_stage,
        "pull_request": None if publication is None else publication.pull_request,
        "published_head": None if publication is None else publication.published_head,
        "published_head_unreadable": _unreadable_statement(publication=publication),
    }


def _unreadable_statement(*, publication: StallPublication | None) -> str | None:
    """The statement, on the one arm that measured a publication with no head.

    An unpublished run reports `None` rather than the statement, and so does a
    publication whose head WAS read: in the first nothing was unreadable, and in
    the second nothing failed. Either would read as a failed measurement, which
    is a diagnostic reported as a finding.
    """
    if publication is None or publication.published_head is not None:
        return None
    return UNREADABLE_PUBLISHED_HEAD
