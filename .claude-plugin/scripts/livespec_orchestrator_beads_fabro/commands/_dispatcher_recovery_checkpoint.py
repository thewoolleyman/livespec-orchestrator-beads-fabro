"""The journal reader for a failed checkpoint's preserved tree."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_record import (
    PRESERVED_TREE_STAGE,
)

__all__: list[str] = ["newest_preserved_tree_row"]

_STAGE_KEY = "stage"
_WORK_ITEM_KEY = "work_item_id"
_REF_KEY = "preservation_ref"
_BASE_COMMIT_KEY = "base_commit"
_RUN_ID_KEY = "run_id"


def newest_preserved_tree_row(
    *, records: tuple[dict[str, object], ...], work_item_id: str
) -> tuple[str, str, str] | None:
    """Return this item's latest complete checkpoint-preservation journal row."""
    for record in reversed(records):
        if record.get(_STAGE_KEY) != PRESERVED_TREE_STAGE:
            continue
        if record.get(_WORK_ITEM_KEY) != work_item_id:
            continue
        ref = record.get(_REF_KEY)
        base = record.get(_BASE_COMMIT_KEY)
        run_id = record.get(_RUN_ID_KEY)
        if not (isinstance(ref, str) and isinstance(base, str) and isinstance(run_id, str)):
            continue
        if ref.strip() and base.strip() and run_id.strip():
            return ref.strip(), base.strip(), run_id.strip()
    return None
