"""The bounded rider set a rendered goal and a judgement subject carry (bd-ib-l2poch).

`contracts.md`'s "A goal carries a bounded rider set" paragraph: of an item's
riders (every comment that is not a judgement receipt) the Dispatcher carries a
rider into a goal only when it is CARRIED, which is when it was appended after the
item's most recent dispatch claim, or its first line names stages in the form
`FOR <stage>[, <stage>...] ONLY:`, or its first line begins `STANDING RIDER:`. An
item never claimed for a dispatch carries every rider. A rider that is not carried
stays on the ledger unchanged and appears in no goal and no judgement subject.

Measured on bd-ib-uq2ocd: 88 comments, 1,628,501 characters, and every host taking
of its judgement ended at the 100,000-token input bound.

WHY THE GOAL AND THE SUBJECT SHARE THIS ONE MODULE. The one-rubric-one-subject
clause requires the node and every host taking to grade the same bytes, so the
question "which comments are carried" has to have one answer. Two spellings of the
bound would be the disagreement between host and in-run takings that the clause
exists to close, and the first difference in them would move a subject digest and
retire a verdict that is still good.

THE BOUND IS A JOURNAL READING. A dispatch claim is the item moving `ready` to
`active`, and the `ledger-admit` journal row the admission valve writes at that
moment is the record of it carrying the instant. The claim stamp on the item holds
no instant. The journal is this host's account, which is the same posture every
other per-dispatch reading here takes; a journal that cannot be read bounds
nothing, so every rider is carried, and that is the direction to fail in because
dropping a binding rider silently is the worse error.

THE CLAIM A DISPATCH TAKES MUST NOT MOVE THAT DISPATCH'S OWN BOUND. The goal is
rendered after the dispatch's own claim, so reading the newest `ledger-admit` would
bound the goal at the claim the dispatch itself just took and drop every rider the
operator wrote since the previous dispatch. `prior_claim_instant` therefore takes
the dispatch's own id and skips the row carrying it. A host taking before any claim
passes no id and reads the newest row.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_markers import (
    comment_marker,
    is_receipt_comment,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_journal_tail import (
    journal_tail_records,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.store import WorkItemComment

__all__: list[str] = [
    "CLAIM_JOURNAL_STAGE",
    "STANDING_RIDER_PREFIX",
    "RiderSet",
    "bound_riders",
    "carried_comment_bodies",
    "claim_journal_record",
    "left_out_line",
    "prior_claim_instant",
    "riders_for_stage",
]

STANDING_RIDER_PREFIX = "STANDING RIDER:"

# The row the admission valve appends when it moves an item `ready` to `active`.
CLAIM_JOURNAL_STAGE = "ledger-admit"

_STAGE_NAME = r"[A-Za-z_][A-Za-z0-9_-]*"
_STAGE_SCOPE = re.compile(rf"^FOR\s+(?P<stages>{_STAGE_NAME}(?:\s*,\s*{_STAGE_NAME})*)\s+ONLY:")
_EPOCH = datetime.fromtimestamp(0, tz=timezone.utc)
_TREE_CHANGING_STAGES = frozenset(("implement", "review_fix"))


@dataclass(frozen=True, kw_only=True)
class RiderSet:
    """The riders a goal carries and what it left out.

    `left_out_newest_at` is the creation time of the newest left-out rider, as the
    ledger spelled it, and is absent exactly when `left_out` is zero.
    """

    carried: tuple[WorkItemComment, ...]
    left_out: int
    left_out_newest_at: str | None


def bound_riders(*, comments: Sequence[WorkItemComment], claim_at: str | None) -> RiderSet:
    """Split an item's riders into the carried ones and the count left out.

    Receipts are neither: they are excluded from every goal and subject by their
    own rule, and the left-out line counts "only riders that are not carried,
    never the receipts".
    """
    carried: list[WorkItemComment] = []
    left_out: list[WorkItemComment] = []
    for comment in comments:
        if is_receipt_comment(body=comment.text):
            continue
        if _is_carried(comment=comment, claim_at=claim_at):
            carried.append(comment)
        else:
            left_out.append(comment)
    newest = max(
        left_out, key=lambda comment: _instant(text=comment.created_at) or _EPOCH, default=None
    )
    return RiderSet(
        carried=tuple(carried),
        left_out=len(left_out),
        left_out_newest_at=None if newest is None else newest.created_at,
    )


def carried_comment_bodies(
    *, comments: Sequence[WorkItemComment], claim_at: str | None
) -> tuple[str, ...]:
    """The bodies a judgement subject is computed from: carried riders plus receipts.

    Receipts stay in because the judgement's reuse read finds a recorded verdict
    among the comment bodies; the subject drops them itself. Only a rider that is
    not carried is removed, which is what leaves the subject digest unchanged by it.
    """
    return tuple(
        comment.text
        for comment in comments
        if is_receipt_comment(body=comment.text) or _is_carried(comment=comment, claim_at=claim_at)
    )


def riders_for_stage(
    *, riders: Sequence[WorkItemComment], stage: str
) -> tuple[WorkItemComment, ...]:
    """Return carried riders that instruct one stage.

    A standing rider governs every agent stage. A well-formed ``FOR … ONLY:``
    marker governs only its listed stages; every other rider is deliberately
    limited to the two tree-changing stages so review and proof turns cannot
    inherit implementation direction.
    """
    return tuple(comment for comment in riders if _applies_to_stage(comment=comment, stage=stage))


def left_out_line(*, item_id: str, riders: RiderSet) -> str:
    """The one line a goal states when it left riders out, or the empty string."""
    if riders.left_out == 0:
        return ""
    noun = "rider" if riders.left_out == 1 else "riders"
    return (
        f"Riders left out of this goal: {riders.left_out} {noun}, appended before the item's "
        f"last dispatch claim (newest created {riders.left_out_newest_at}); "
        f"`bd comments {item_id}` lists the item's full ledger comments."
    )


def claim_journal_record(*, item_id: str, assignee: str, dispatch_id: str) -> dict[str, object]:
    """The row the admission valve journals when it claims an item.

    Spelled HERE, beside `prior_claim_instant` which reads it, so the writer and
    the reader of the claim row cannot name its fields two ways. `dispatch_id` is
    the field that lets a dispatch skip the claim it just took.
    """
    return {
        "stage": CLAIM_JOURNAL_STAGE,
        "work_item_id": item_id,
        "assignee": assignee,
        "dispatch_id": dispatch_id,
    }


def prior_claim_instant(
    *, journal_path: Path, item_id: str, own_dispatch_id: str | None = None
) -> str | None:
    """The instant of the item's most recent dispatch claim before this dispatch's own.

    `None` when the item has never been claimed, which carries every rider, and
    also when the journal holds no readable claim row for it.
    """
    instant: str | None = None
    for record in journal_tail_records(journal_path=journal_path):
        if record.get("stage") != CLAIM_JOURNAL_STAGE or record.get("work_item_id") != item_id:
            continue
        if own_dispatch_id is not None and record.get("dispatch_id") == own_dispatch_id:
            continue
        at = record.get("at")
        if isinstance(at, str) and _instant(text=at) is not None:
            instant = at
    return instant


def _is_carried(*, comment: WorkItemComment, claim_at: str | None) -> bool:
    marker = comment_marker(body=comment.text)
    if marker.startswith(STANDING_RIDER_PREFIX) or _STAGE_SCOPE.match(marker):
        return True
    claimed = _instant(text=claim_at)
    created = _instant(text=comment.created_at)
    return claimed is None or created is None or created >= claimed


def _applies_to_stage(*, comment: WorkItemComment, stage: str) -> bool:
    marker = comment_marker(body=comment.text)
    if marker.startswith(STANDING_RIDER_PREFIX):
        return True
    scope = _STAGE_SCOPE.match(marker)
    if scope is None:
        return stage in _TREE_CHANGING_STAGES
    return stage in {name.strip() for name in scope.group("stages").split(",")}


def _instant(*, text: str | None) -> datetime | None:
    if text is None:
        return None
    parsed = attempt(
        action=lambda: datetime.fromisoformat(text.replace("Z", "+00:00")),
        exceptions=(ValueError,),
    )
    if isinstance(parsed, AttemptFailure):
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
