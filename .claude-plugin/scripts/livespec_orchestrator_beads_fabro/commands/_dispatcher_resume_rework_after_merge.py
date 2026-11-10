"""Whether a rework rejection of an item postdates its pull request's merge.

A merged pull request on an item's publish branch holds a released item with the
close-out refusal, because the item's work landed and nothing is owed. That holds
only while nothing says otherwise: the item can be rejected to rework AFTER the
merge, by the human `reject:<id>:rework` valve or by the AI-fail automatic rework
disposition (the only two entries the rework contract lets mark an item), and a
rework dispatch that then ended at needs-human releases it for recovery with the
ORIGINAL merge still standing on the branch. Reading that merge as "complete"
sends an operator to `reconcile-merged`, which would close out an unfinished
rework (`bd-ib-nkoyln`, measured on `bd-ib-5d5aue`).

THE ORDER OF THE TWO EVENTS IS THE WHOLE DECISION, so both instants are read: the
merge from the forge, the rejection from the journal row's `at` stamp. EVERY
UNREADABLE SHAPE IS "NO REWORK AFTER THE MERGE", the hold direction, because a
rejection whose time cannot be established cannot be shown to postdate anything,
and holding costs one operator look while routing a rework over a completed
publication cuts a branch against work that already landed.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import timezone

from livespec_orchestrator_beads_fabro.effects import (
    IsoDatetimeParseFailure,
    parse_iso_datetime,
)

__all__: list[str] = [
    "rework_rejected_after_merge",
]

_HUMAN_REWORK_STAGE = "human-valve-reject-rework"
_AUTO_DISPOSITION_STAGE = "auto-disposition"
_AI_FAIL_REWORK_DISPOSITION = "ai-fail-auto-rework"
_TRAILING_Z = re.compile(r"Z$")


def rework_rejected_after_merge(
    *,
    records: Sequence[Mapping[str, object]],
    work_item_id: str,
    merged_at: str | None,
) -> bool:
    """Whether any journaled rework rejection of this item is later than the merge."""
    merged = _epoch(value=merged_at)
    if merged is None:
        return False
    return any(
        (rejected := _epoch(value=record.get("at"))) is not None and rejected > merged
        for record in records
        if record.get("work_item_id") == work_item_id and _is_rework_rejection(record=record)
    )


def _is_rework_rejection(*, record: Mapping[str, object]) -> bool:
    """Whether this journal row is one of the two rework entries."""
    stage = record.get("stage")
    if stage == _HUMAN_REWORK_STAGE:
        return True
    return stage == _AUTO_DISPOSITION_STAGE and (
        record.get("disposition") == _AI_FAIL_REWORK_DISPOSITION
    )


def _epoch(*, value: object) -> float | None:
    """An ISO-8601 instant as epoch seconds; `None` for anything unreadable."""
    if not isinstance(value, str):
        return None
    parsed = parse_iso_datetime(text=_TRAILING_Z.sub("+00:00", value))
    if isinstance(parsed, IsoDatetimeParseFailure):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()
