"""Backlog groom-out helpers for the grooming lifecycle.

The ratified seven-state lifecycle has no separate regroom label or status.
Items that need decomposition are ordinary `backlog` work-items: intake-routed
epics land there, and Dispatcher non-convergence bounces return there. The
`groom` front-end drafts read-only against that backlog target, then on
maintainer approval files replacement slices and explicitly closes the original
item as no longer applicable.

This module owns the small shared mechanical checks for that flow:

- `require_backlog_target` confirms the target exists and currently carries the
  `backlog` status.
- `close_regroomed_out` refuses an empty replacement set and then closes the
  original item with a concrete disposition naming the replacement slice ids.

Expected misuse raises `WorkItemNotFoundError`, `GroomTargetNotBacklogError`, or
`GroomExitRefusedError`; bugs propagate as built-in exceptions.
"""

from __future__ import annotations

from dataclasses import replace

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro.errors import (
    GroomExitRefusedError,
    GroomTargetNotBacklogError,
    WorkItemNotFoundError,
)
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "BACKLOG_STATUS",
    "close_regroomed_out",
    "require_backlog_target",
]

BACKLOG_STATUS = "backlog"
_REGROOMED_OUT_RESOLUTION = "no-longer-applicable"


def require_backlog_target(*, path: StoreConfig, item_id: str) -> None:
    """Raise unless `item_id` exists and is currently a backlog item."""
    client = make_beads_client(config=path)
    if not client.exists(issue_id=item_id):
        raise WorkItemNotFoundError(item_id=item_id)
    record = client.show_issue(issue_id=item_id)
    if record.get("status") != BACKLOG_STATUS:
        raise GroomTargetNotBacklogError(item_id=item_id)


def close_regroomed_out(
    *, path: StoreConfig, item_id: str, replacement_slice_ids: list[str]
) -> None:
    """Close a backlog grooming target with an explicit replacement disposition."""
    require_backlog_target(path=path, item_id=item_id)
    if not replacement_slice_ids:
        raise GroomExitRefusedError(
            item_id=item_id,
            detail="no replacement slices were filed (an item is regroomed-out, never dropped)",
        )
    item = materialize_work_items(records=read_work_items(path=path))[item_id]
    closed = replace(
        item,
        status="done",
        resolution=_REGROOMED_OUT_RESOLUTION,
        reason=_regroomed_out_reason(replacement_slice_ids=replacement_slice_ids),
        audit=None,
    )
    append_work_item(path=path, item=closed)


def _regroomed_out_reason(*, replacement_slice_ids: list[str]) -> str:
    return "regroomed out into replacement slices: " + ", ".join(replacement_slice_ids)
