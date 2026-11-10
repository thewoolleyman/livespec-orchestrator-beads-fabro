"""The journal-order comparison between a preserved ref and a published head."""

from __future__ import annotations

from typing import Literal

__all__: list[str] = ["foreign_run_ids", "published_head_is_later", "published_head_relation"]

_PUBLISHED_HEAD_KEY = "published_head"
_RUN_ID_KEY = "run_id"


def published_head_is_later(
    *, records: tuple[dict[str, object], ...], preserved_run_id: str, published_head: str
) -> bool:
    """Whether the journal attributes ``published_head`` to a later run.

    Missing attribution is deliberately not guessed here.  The routing reader
    owns the resulting held decision; this comparison only supplies the proven
    older-than relation that makes the observed head win.
    """
    return (
        published_head_relation(
            records=records,
            preserved_run_id=preserved_run_id,
            published_head=published_head,
        )
        is True
    )


def published_head_relation(
    *,
    records: tuple[dict[str, object], ...],
    preserved_run_id: str,
    published_head: str,
    publications: tuple[tuple[str, str], ...] = (),
) -> Literal[True, False] | None:
    """Compare the two runs, or name the attribution gap with ``None``.

    ``None`` is deliberately distinct from ``False``: a recovery route may keep
    an established terminal tree when the head is proven not newer, but cannot
    reclaim either tree when neither the journal nor a publication record can
    establish which run published it. ``publications`` pairs each head a
    publication record declares with the run that record names; a head published
    by the preserved ref's own run needs no journal order to be ranked.
    """
    published_position = _publishing_run_position(records=records, head=published_head)
    if published_position is None:
        publishing_run = next((run for head, run in publications if head == published_head), None)
        if publishing_run is None:
            return None
        if publishing_run == preserved_run_id:
            return False
        published_position = _run_position(records=records, run_id=publishing_run)
    preserved_position = _run_position(records=records, run_id=preserved_run_id)
    if published_position is None or preserved_position is None:
        return None
    return published_position > preserved_position


def _publishing_run_position(*, records: tuple[dict[str, object], ...], head: str) -> int | None:
    """The dispatch position whose journal record names ``head``."""
    for position, record in reversed(tuple(enumerate(records))):
        if record.get(_PUBLISHED_HEAD_KEY) != head:
            continue
        run_id = record.get(_RUN_ID_KEY)
        if isinstance(run_id, str) and run_id.strip():
            return _run_position(records=records, run_id=run_id.strip(), fallback=position)
    return None


def _run_position(
    *, records: tuple[dict[str, object], ...], run_id: str, fallback: int | None = None
) -> int | None:
    """The latest record that names a run, preserving journal dispatch order."""
    for position, record in reversed(tuple(enumerate(records))):
        if record.get(_RUN_ID_KEY) == run_id:
            return position
    return fallback


def foreign_run_ids(
    *, records: tuple[dict[str, object], ...], work_item_id: str, own: tuple[str, ...]
) -> frozenset[str]:
    """Run and dispatch identifiers the journal attributes to another item and not this one."""
    return frozenset(
        value
        for record in records
        if isinstance(record.get("work_item_id"), str) and record["work_item_id"] != work_item_id
        for key in (_RUN_ID_KEY, "dispatch_id")
        if isinstance(value := record.get(key), str) and value and value not in own
    )
