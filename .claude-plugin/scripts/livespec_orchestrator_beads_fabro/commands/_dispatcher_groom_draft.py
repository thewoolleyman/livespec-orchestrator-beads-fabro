"""The drafted decomposition as a ledger comment: how it is written and read.

`SPECIFICATION/contracts.md` section "Grooming and slice-size calibration" ->
"Consensus-gated automated groom cut" puts the draft on the LEDGER rather than
in the run: a groom variant's propose phase terminates at a needs-human
outcome, and "when the Dispatcher journals that termination it MUST record the
draft on the item as a ledger comment, beside the preserve-by-reference
pointer; that comment is where the draft rests, and it is what the apply phase
reads."

WHY THE LEDGER AND NOT THE RUN. Under the ratified rule that a factory run
never awaits a human, the drafting run is DEAD by the time a human sees the
draft. Everything reachable only through that run -- its sandbox, its
`inspect` record -- is gone the moment the run is reaped, and this repository's
own reap protocol authorises reaping a dead run once its record is exported.
A draft that lived only in the run would therefore be destroyed by a
sanctioned operation. The ledger comment is what survives it, and it is
also the channel the next dispatch's goal render already carries verbatim,
so the apply run reads the draft without any new seam.

WHY THE APPROVAL IS POSITIONAL RATHER THAN A FLAG. An approval is the operator
answer `resolve-blocked:<work-item-id>:ready` writes, and both records are
comments on one append-only list. So "approved" means an answer comment
appearing AFTER the newest draft comment -- not merely somewhere on the item.
That ordering is what makes a re-draft self-invalidating: the contract's
`resolve-blocked:<work-item-id>:backlog` sends a draft back for re-drafting,
and the re-draft's comment lands after the old approval, which correctly reads
as an unapproved draft again. A boolean "has an approval" flag would have kept
the stale consent alive across the bounce.

WHY POSITION IS NOT SUFFICIENT ON ITS OWN. Ordering makes a newer DRAFT win; it
never makes a send-back stop reading as consent. `drive` accepts `--answer` on
`resolve-blocked:<work-item-id>:backlog` -- attaching feedback to a bounce is
the documented path, not a misuse -- so an operator who rejects a cut as too
coarse and says why has written an answer comment after that draft. A reader
keying on the answer MARKER alone therefore turns that rejection into the
consent for filing the very decomposition it rejected: in the window before
any re-draft lands, and permanently when none ever does, which is the ordinary
outcome for an item that is abandoned, hand-groomed or re-scoped instead.

So the DISPOSITION is read, not just the position. The action id already rides
in the answer comment's header, and `ready` is the only disposition that
consents; every other answer leaves the draft unapproved and a `backlog` one
revokes an earlier consent, because the newest answer is the operator's
standing verdict on the draft it follows.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._drive_answer import answering_action_id
from livespec_orchestrator_beads_fabro.store import read_work_item_comments

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "GROOM_DRAFT_COMMENT_MARKER",
    "approved_groom_draft",
    "approved_groom_draft_for",
    "drafting_groom_variant",
    "render_groom_draft_comment",
]

# The stable opening token of every draft comment. The goal brief renders a
# ledger comment verbatim, so this line is what tells the apply run that what
# follows is the DRAFT it must file rather than one more operator rider.
GROOM_DRAFT_COMMENT_MARKER = "livespec-groom-draft"

_OPEN = " ("
_CLOSE = ","

# The tail of the ONE `resolve-blocked` disposition that is consent to file.
# Matched as a suffix of the whole action id so `resolve-blocked:<id>:ready`
# qualifies and `resolve-blocked:<id>:backlog` does not.
_READY_DISPOSITION = ":ready"


def render_groom_draft_comment(*, draft: str, variant: str, run_id: str, at: str) -> str:
    """Render the comment body the apply dispatch's brief will carry verbatim.

    The drafting VARIANT is written into the body rather than left to the
    item's `dispatch_workflow` pin, because the pin is exactly what the apply
    gate must be able to catch being changed: an item whose pin was cleared
    still has to read as carrying a groom draft, or clearing the pin would
    silently disarm the gate that exists to refuse that very substitution.
    """
    return f"{GROOM_DRAFT_COMMENT_MARKER}{_OPEN}{variant}{_CLOSE} run {run_id}, {at}):\n{draft}"


def drafting_groom_variant(*, text: str) -> str | None:
    """The variant that drafted this comment, or None if it is not a draft.

    Deliberately strict about the marker's POSITION: only a comment whose first
    line opens with the marker is a draft. A comment merely quoting the marker
    -- an operator explaining the mechanism, or a failure write-up pasting a
    body -- must not be mistaken for a draft, since doing so would let prose
    about grooming satisfy the apply gate.
    """
    head = text.split("\n", 1)[0]
    prefix = f"{GROOM_DRAFT_COMMENT_MARKER}{_OPEN}"
    if not head.startswith(prefix):
        return None
    variant = head[len(prefix) :].split(_CLOSE, 1)[0].strip()
    return variant if variant != "" else None


def approved_groom_draft(*, comments: Sequence[str]) -> str | None:
    """The variant of the newest draft, when a READY answer follows it; else None.

    `None` covers four genuinely different items with one answer, and that is
    correct here: an item with no draft, an item whose draft is still awaiting
    a human, an item whose draft was sent back with a `backlog` disposition,
    and an item whose draft was bounced and then re-drafted are all items with
    NO approved draft awaiting an apply dispatch.

    A comment that is neither a draft nor a readable answer -- an ordinary
    operator rider -- is passed over rather than treated as either, so a rider
    appended after an approval does not silently withdraw it.
    """
    drafted: str | None = None
    approved: str | None = None
    for text in comments:
        variant = drafting_groom_variant(text=text)
        if variant is not None:
            drafted = variant
            approved = None
            continue
        aid = answering_action_id(text=text)
        if aid is None or drafted is None:
            continue
        approved = drafted if aid.endswith(_READY_DISPOSITION) else None
    return approved


def approved_groom_draft_for(*, path: StoreConfig, work_item_id: str) -> str | None:
    """Read the item's comments and report the approved draft's variant, if any."""
    comments = read_work_item_comments(path=path, work_item_id=work_item_id)
    return approved_groom_draft(comments=tuple(comment.text for comment in comments))
