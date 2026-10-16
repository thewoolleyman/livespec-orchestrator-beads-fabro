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

"THE DISPATCH'S IDENTIFIER" IS EITHER OF TWO VALUES, and the cancel row carries
both. `_dispatcher_proof_attribution` attributes one record to one dispatch by its
Fabro RUN id or by its DISPATCH id — the widening it exists for — and the clause
inherits that reading, since the earlier run is "resolved through the dispatch
journal exactly as the acceptance pass attributes a record". So the precedence
test asks about both: a cancelled dispatch whose capture HAD completed, and whose
record names it by dispatch id, otherwise reads here as a dispatch with no record
at all, and the resume re-captures a head already proved.

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

BUT THE LATEST CANCEL ROW IS NOT THE LATEST DISPATCH. The clause scopes this
anchor to the item's LATEST JOURNALED DISPATCH — "no proof record ... carries the
identifier of the item's latest journaled dispatch, and THAT dispatch's journal
carries a `watchdog-stall-cancel` record" — and a cancel row can be the newest
cancel while belonging to a dispatch a later PLAIN dispatch has superseded. That
later dispatch was never cancelled, so it contributes no row of its own and
nothing in the cancel rows announces that it happened; the `dispatch-id` row it
wrote at launch is the only evidence, which is why this reader has to look at
them. Anchoring on the superseded row is wrong in BOTH directions at once: when
the pull request carries the later dispatch's head, the moved-head refusal fires
on a two-dispatches-old sha and names a plain dispatch as the remedy — which
reclaims the publish branch this module exists to preserve — and when the two
heads coincide, the resume re-enters `proof_capture` on a tree the later dispatch
had already captured and had reviewed.

THE SUPERSESSION IS READ TWO WAYS, because neither way is complete alone. The
journal is append-only and a `dispatch-id` row is written at LAUNCH, before any
stage of that dispatch can be cancelled, so a `dispatch-id` row for the item
AFTER the cancel row is a later dispatch and the row is superseded by POSITION —
which is the only reading available for a row written before the cancel site
recorded a dispatch id. Position alone is not enough, though: a reconciliation of
a stranded run journals its cancel row after that dispatch was superseded, so the
row sits last in the journal while naming a dispatch the item has moved past.
When both parties name an id, IDENTITY settles it. And the precedence comparison
takes the LATEST DISPATCH's identifiers rather than the row's own, which is the
same set whenever the row names its dispatch and a strictly wider one when it
does not.

ONE RESOLUTION SERVES BOTH READINGS. `cancel_anchor` and
`unanchoring_cancel_stage` answer different questions about the SAME row — what
anchors, and what the refusal says about a row that could not — so resolving the
row twice is how the decision and its explanation come to describe different
dispatches. The gate therefore lives in the shared resolution, not in each
caller.
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
    "unanchoring_cancel_stage",
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
_DISPATCH_ID_KEY = "dispatch_id"
_EXECUTING_STAGE_KEY = "executing_stage"
_PUBLISHED_HEAD_KEY = "published_head"

# The journal stage one dispatch writes at LAUNCH, which is how this reader
# learns that a dispatch happened at all. Spelled here rather than imported from
# `_dispatcher_dispatch_id_journal`, which this leaf must not depend on; the
# literal is the one every reader of that record already shares.
_DISPATCH_ID_STAGE = "dispatch-id"


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


@dataclass(frozen=True, kw_only=True)
class _LatestCancel:
    """One admitted cancel row beside the identity of the dispatch it belongs to.

    `dispatch_id` is the LATEST JOURNALED DISPATCH's own id, not the row's, and it
    is `None` when no `dispatch-id` row for the item named a readable one. The two
    travel together because the precedence comparison needs the dispatch's
    identifiers while every other bound reads the row, and resolving them
    separately is how one reading comes to describe a dispatch the other did not.
    """

    record: Mapping[str, object]
    dispatch_id: str | None


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
    differently about the same pull request. It is compared against EVERY
    identifier the latest journaled dispatch answers to; see the module docstring
    for why one is not enough.

    Every arm below returns `None`, which is the whole of "this row cannot anchor
    a resume": the caller then falls back to the proof-record anchor, and the
    refusal ladder reports a headless pull request if that reader finds nothing
    either.
    """
    latest = _latest_cancel_record(records=records, work_item_id=work_item_id)
    if latest is None:
        return None
    record = latest.record
    run_id = _text(value=record.get(_RUN_ID_KEY))
    if run_id is None:
        return None
    identifiers = _dispatch_identifiers(
        record=record, run_id=run_id, journaled_dispatch_id=latest.dispatch_id
    )
    if not proof_run_ids.isdisjoint(identifiers):
        return None
    if record.get(_EXECUTING_STAGE_KEY) != CANCEL_ANCHOR_RESUMED_AT:
        return None
    head = _text(value=record.get(_PUBLISHED_HEAD_KEY))
    if head is None:
        return None
    return CancelAnchor(run_id=run_id, head=head)


def unanchoring_cancel_stage(
    *, records: Sequence[Mapping[str, object]], work_item_id: str
) -> str | None:
    """The stage of a cancel record that names a head and still cannot anchor.

    The REWORK-STAGE case, and only it: the row named a published head, so an
    operator can see a head-naming record on the journal, and it was refused for
    its stage because "its head would not carry the rework". The refusal needs
    that stage to state the whole of its condition.

    Every other reason a row cannot anchor returns `None`, because none of them
    leaves an operator with a head-naming record to wonder about: a row naming no
    head says so in words, a row outranked by a proof record was superseded by
    better evidence, and an item with no cancel record has nothing to explain. The
    head test therefore runs FIRST — a `janitor` cancel whose head was unreadable
    is the no-head case, not the rework case, and reporting its stage would offer
    the rework rule as the reason a resume cannot proceed when the real reason is
    that nothing was measured.
    """
    latest = _latest_cancel_record(records=records, work_item_id=work_item_id)
    if latest is None:
        return None
    if _text(value=latest.record.get(_PUBLISHED_HEAD_KEY)) is None:
        return None
    stage = _text(value=latest.record.get(_EXECUTING_STAGE_KEY))
    if stage is None or stage == CANCEL_ANCHOR_RESUMED_AT:
        return None
    return stage


def _dispatch_identifiers(
    *, record: Mapping[str, object], run_id: str, journaled_dispatch_id: str | None
) -> frozenset[str]:
    """Every identifier a proof record may carry and still belong to this dispatch.

    The run id is already in hand and is always a member. Each dispatch id is
    added when it is readable, and there are TWO places one can be read: the
    cancel row itself, and the `dispatch-id` row the same dispatch wrote at
    launch. A row written before the cancel site recorded the dispatch id
    therefore still contributes its dispatch's id through the journal, which is
    what keeps a proof record naming that dispatch outranking the row; and a
    journal predating the `dispatch-id` record degrades to the run id alone
    rather than refusing, because an older row is still a perfectly good anchor
    and the only thing a missing dispatch id costs is a precedence comparison.
    """
    named = {run_id}
    for candidate in (_text(value=record.get(_DISPATCH_ID_KEY)), journaled_dispatch_id):
        if candidate is not None:
            named.add(candidate)
    return frozenset(named)


def _latest_cancel_record(
    *, records: Sequence[Mapping[str, object]], work_item_id: str
) -> _LatestCancel | None:
    """The item's newest cancel row, when it belongs to the item's LATEST dispatch.

    The row is ATTRIBUTED before it is read, because the journal spans every item
    the repository dispatches: an unattributed scan would anchor one item's resume
    on another item's cancelled head, and both are perfectly well-formed shas.

    A `dispatch-id` row DISCARDS whatever cancel row preceded it, which is the
    positional half of the supersession reading: that row is a dispatch which
    began after the cancellation and was never cancelled itself, so the cancel
    row belongs to a dispatch the item has moved past. It discards the row
    whether or not the dispatch named a readable id, because a later dispatch
    supersedes an earlier cancellation either way — the id decides only what the
    precedence comparison can ask about.

    The identity half then catches the row position cannot: a cancel row
    journaled AFTER its dispatch was superseded sits last and still names the
    earlier dispatch. Both ids must be readable for that comparison to mean
    anything, so a row or a journal naming none degrades to the positional
    reading rather than refusing.
    """
    found: Mapping[str, object] | None = None
    journaled_dispatch_id: str | None = None
    for record in records:
        if record.get(_WORK_ITEM_KEY) != work_item_id:
            continue
        stage = record.get(_STAGE_KEY)
        if stage == _DISPATCH_ID_STAGE:
            found = None
            journaled_dispatch_id = _text(value=record.get(_DISPATCH_ID_KEY))
        elif stage == STALL_CANCEL_STAGE:
            found = record
    if found is None:
        return None
    row_dispatch_id = _text(value=found.get(_DISPATCH_ID_KEY))
    if (
        journaled_dispatch_id is not None
        and row_dispatch_id is not None
        and row_dispatch_id != journaled_dispatch_id
    ):
        return None
    return _LatestCancel(record=found, dispatch_id=journaled_dispatch_id)


def _text(*, value: object) -> str | None:
    """One journaled field as a non-empty string, or `None` for anything else.

    A journal row is JSON some earlier build wrote, so the field may be absent,
    null, empty or a non-string. Every such reading yields `None` rather than a
    coerced value: a `str()`-ed number reads exactly like a sha nobody published,
    and an empty string compares unequal to every real head, so both would send
    the moved-head refusal after a value no run ever pushed.
    """
    return value if isinstance(value, str) and value else None
