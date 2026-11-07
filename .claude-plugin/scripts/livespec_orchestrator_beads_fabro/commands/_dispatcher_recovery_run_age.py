"""The journal-order comparison between a preserved ref and a published head."""

from __future__ import annotations

__all__: list[str] = ["published_head_is_later"]

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
    published_position = _publishing_run_position(records=records, head=published_head)
    preserved_position = _run_position(records=records, run_id=preserved_run_id)
    return (
        published_position is not None
        and preserved_position is not None
        and published_position > preserved_position
    )


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
