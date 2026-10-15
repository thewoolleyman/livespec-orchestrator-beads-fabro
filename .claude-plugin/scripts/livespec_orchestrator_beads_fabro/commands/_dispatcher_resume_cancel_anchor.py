"""The anchor a resume reads off a stall-cancelled dispatch's own journal row.

`SPECIFICATION/contracts.md` section "Resume from a published pull request
(`resume --item`)" admits a SECOND anchor beside the proof record: "When no proof
record on the pull request carries the identifier of the item's latest journaled
dispatch, and that dispatch's journal carries a `watchdog-stall-cancel` record
... naming a published head, that cancel record anchors the resume instead."
This module is that reading, and it is PURE — the journal rows are handed to it —
so every bound below is assertable without a forge, a factory or a journal file.

WHY THE SECOND ANCHOR HAD TO EXIST AT ALL. A run cancelled between its last
completed `publish_draft` and `proof_capture` has published everything a resume
needs and has posted NO proof record, because posting one is the very node it
never reached. The proof-record reader therefore returns nothing, the resume
refuses for a headless pull request, and the re-dispatch takes the publish-branch
reclaim — which preserves the dead run's head to a ref, deletes the branch, and
starts over. Measured 2026-10-12: `bd-ib-z6fmp`'s run 01M4Q4XBZ5398FJAWQ131QER60
completed implement, janitor and publish_draft before its cancel at 06:33Z, and
the next dispatch at 07:08Z journaled `publish-branch-reclaim` for
`feat/bd-ib-z6fmp` and rebuilt the whole slice.

THE THREE BOUNDS ARE NOT INTERCHANGEABLE, AND EACH FAILS CLOSED.

A proof record carrying the cancelled dispatch's identifier always WINS, because
that record is evidence a stage published and the cancel row is evidence only of
where the run stopped. The clause says so outright, and the direction matters: a
cancel row names `proof_capture` unconditionally, so preferring it would re-enter
capture for a run whose capture had already completed and been reviewed.

The stage must be `proof_capture`. "A cancel in any other stage, including a
later `janitor`, `fix` or `publish_draft` of a rework loop, does not anchor,
because its head would not carry the rework." The single comparison covers BOTH
admitted shapes, which is what makes it this narrow rather than a stage set: a
run cancelled INSIDE capture reports `proof_capture` as its open node, and a run
cancelled in the gap after `publish_draft` reports `proof_capture` as the target
of the edge its last succeeded node selected. `_dispatcher_stall_run_reading`
owns both readings and answers one value.

A record naming no HEAD anchors nothing. The head is what the sandbox checks out
and what the moved-head refusal compares the pull request's current head
against, so an anchor carrying none would send that refusal after an unknown and
resume on a tree no record describes. The cancel record already states that
condition in words rather than omitting it, and this is the reader computing the
same conclusion from the absent value.

AND THE LATEST ROW IS THE ONE THAT ANSWERS. Journal order is cancellation order
— the cancel site appends exactly one row per cancellation — so an earlier row
belongs to a dispatch the item has already moved past. Anchoring on it would
enter `proof_capture` on a tree two dispatches old while the pull request carries
the newest publication.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_cancel_record import (
    STALL_CANCEL_STAGE,
)

__all__: list[str] = [
    "CANCEL_ANCHOR_RESUMED_AT",
    "SOURCE_CANCEL_RECORD",
    "CancelAnchor",
    "cancel_anchor",
]

# The ONE stage a cancel record can enter a resumed run at. It is a constant
# rather than a reading of the row, because the clause fixes it: "Under this
# anchor the earlier run is that dispatch, the published head is the head the
# record names, and the resumed-at stage is `proof_capture`." The row's own
# `executing_stage` is the GATE on whether the anchor applies at all, which is a
# different question from where the resumed run enters.
CANCEL_ANCHOR_RESUMED_AT = "proof_capture"

# Which party decided the resumed-at stage, for the `resume` record's own
# `resumed_at_source` field. It NAMES the measurement rather than ranking it, as
# `_dispatcher_resume_anchor`'s two source values do, and it names the journal
# STAGE an operator can grep for rather than a private label.
SOURCE_CANCEL_RECORD = "watchdog-stall-cancel-record"

_STAGE_KEY = "stage"
_WORK_ITEM_KEY = "work_item_id"
_RUN_ID_KEY = "run_id"
_EXECUTING_STAGE_KEY = "executing_stage"
_PUBLISHED_HEAD_KEY = "published_head"


@dataclass(frozen=True, kw_only=True)
class CancelAnchor:
    """What one cancel record says about the run a resume would finish.

    Only the two fields a resume ACTS on: the run the `resume` record links its
    identifiers to, and the head the sandbox checks out. The pull request the row
    also names is deliberately absent — the resume reads that from the forge, and
    carrying a second copy here would invite a comparison against an answer taken
    at a different moment.
    """

    run_id: str
    head: str


def cancel_anchor(
    *,
    records: Sequence[Mapping[str, object]],
    work_item_id: str,
    proof_run_ids: frozenset[str],
) -> CancelAnchor | None:
    """The anchor the item's LATEST cancel record provides, or `None` for none.

    `proof_run_ids` is every identifier the pull request's own proof records
    carry. It is passed IN rather than read here because this module is pure over
    the journal and the records live on the forge, and because the caller has
    already read them for the proof-record anchor — a second read could answer
    differently about the same pull request.

    Every arm below returns `None`, which is the whole of "this row cannot anchor
    a resume": the caller then falls back to the proof-record anchor, and the
    refusal ladder reports a headless pull request if that reader finds nothing
    either.
    """
    latest = _latest_cancel_record(records=records, work_item_id=work_item_id)
    if latest is None:
        return None
    run_id = _text(value=latest.get(_RUN_ID_KEY))
    if run_id is None:
        return None
    if run_id in proof_run_ids:
        return None
    if latest.get(_EXECUTING_STAGE_KEY) != CANCEL_ANCHOR_RESUMED_AT:
        return None
    head = _text(value=latest.get(_PUBLISHED_HEAD_KEY))
    if head is None:
        return None
    return CancelAnchor(run_id=run_id, head=head)


def _latest_cancel_record(
    *, records: Sequence[Mapping[str, object]], work_item_id: str
) -> Mapping[str, object] | None:
    """The item's newest cancel row in journal order, or `None` when it has none.

    The row is ATTRIBUTED before it is read, because the journal spans every item
    the repository dispatches: an unattributed scan would anchor one item's resume
    on another item's cancelled head, and both are perfectly well-formed shas.
    """
    found: Mapping[str, object] | None = None
    for record in records:
        if (
            record.get(_STAGE_KEY) == STALL_CANCEL_STAGE
            and record.get(_WORK_ITEM_KEY) == work_item_id
        ):
            found = record
    return found


def _text(*, value: object) -> str | None:
    """One journaled field as a non-empty string, or `None` for anything else.

    A journal row is JSON some earlier build wrote, so the field may be absent,
    null, empty or a non-string. Every such reading yields `None` rather than a
    coerced value: a `str()`-ed number reads exactly like a sha nobody published,
    and an empty string compares unequal to every real head, so both would send
    the moved-head refusal after a value no run ever pushed.
    """
    return value if isinstance(value, str) and value else None
