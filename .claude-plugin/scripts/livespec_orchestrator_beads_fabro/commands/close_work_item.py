"""`close-work-item` — the atomic close + `resolution:<enum>` wrapper.

The "pit of success" for the closed-item-integrity invariant
(SPECIFICATION/constraints.md; the
implementation-approach note in contracts.md). The two-step close recipe codified in
(`bd close --reason …` THEN `bd update --add-label
resolution:completed`) can be half-done — an item closed without the
label is "closed but unproven" and is FORBIDDEN. This wrapper makes the
compliant path the path of least resistance: it CLOSES a work-item AND
applies `resolution:completed` in ONE operation, so the label can never
be forgotten. A close given no `--resolution` applies `resolution:completed`;
a non-completion administrative closure (`wontfix`, `duplicate`,
`spec-revised`, `no-longer-applicable`, `resolved-out-of-band`) names its
resolution with `--resolution`.

In two halves, mirroring the other front-ends:

- `close_completed` — the load-bearing mechanical seam. It reads the
  existing work-item, builds a closed copy carrying
  `resolution="completed"` (and the close reason), and persists it
  through the same `append_work_item` machinery every close flows
  through — which routes a status-`closed` mutation for an existing id to
  the store's in-place `bd close` + `resolution:completed` label + audit
  metadata. The label and the close land together or not at all.
- `main` — the thin CLI surface (`close-work-item <id> [--resolution …]
  [--reason …] [--project-root …]`) skills and recipes shell to.

Per SPECIFICATION/constraints.md (the
Result-vs-bugs split), the one EXPECTED misuse — closing an id that was
never filed — raises the typed `WorkItemNotFoundError`; genuine bugs
propagate as raised built-in exceptions.
"""

from __future__ import annotations

import argparse
import dataclasses
from pathlib import Path
from typing import TYPE_CHECKING, get_args

from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
from livespec_orchestrator_beads_fabro.errors import WorkItemNotFoundError
from livespec_orchestrator_beads_fabro.io import write_stderr, write_stdout
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import Resolution

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = ["close_completed", "close_with_resolution", "main"]

_RESOLUTION_COMPLETED: Resolution = "completed"
_EXIT_NOT_FOUND = 3


def close_with_resolution(
    *, path: StoreConfig, item_id: str, resolution: Resolution, reason: str | None = None
) -> WorkItem:
    """Close `item_id` AND apply `resolution:<resolution>` atomically.

    Reads the existing work-item, builds a closed copy carrying
    `status="done"`, the given `resolution`, and the close `reason`
    (falling back to the item's existing reason when none is supplied),
    and persists it through `append_work_item` — which routes the
    status-`done` mutation of an existing id to the store's in-place
    close + resolution label write. The close and the label land in the
    SAME store operation, so an item can never be left "closed without a
    resolution label".

    Returns the closed WorkItem. Raises `WorkItemNotFoundError` if
    `item_id` is not present in the tenant (an expected misuse — a typo,
    or an id closed and pruned between read and write).
    """
    index = materialize_work_items(records=read_work_items(path=path))
    existing = index.get(item_id)
    if existing is None:
        raise WorkItemNotFoundError(item_id=item_id)
    closed = dataclasses.replace(
        existing,
        status="done",
        resolution=resolution,
        reason=reason if reason is not None else existing.reason,
    )
    append_work_item(path=path, item=closed)
    return closed


def close_completed(*, path: StoreConfig, item_id: str, reason: str | None = None) -> WorkItem:
    """Close `item_id` AND apply `resolution:completed` atomically."""
    return close_with_resolution(
        path=path, item_id=item_id, resolution=_RESOLUTION_COMPLETED, reason=reason
    )


def main(*, argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="close-work-item")
    _ = parser.add_argument("work_item_id", help="The work-item id to close.")
    _ = parser.add_argument(
        "--reason",
        dest="reason",
        default=None,
        help="The close reason (defaults to the item's existing reason).",
    )
    _ = parser.add_argument(
        "--resolution",
        dest="resolution",
        choices=get_args(Resolution),
        default=_RESOLUTION_COMPLETED,
        help="The resolution label to apply (defaults to completed).",
    )
    _ = parser.add_argument("--project-root", dest="project_root", default=None)
    args = parser.parse_args(argv)
    project_root = Path(args.project_root) if args.project_root is not None else Path.cwd()
    config = resolve_store_config(cwd=project_root, work_items_arg=None)
    try:
        closed = close_with_resolution(
            path=config,
            item_id=args.work_item_id,
            resolution=args.resolution,
            reason=args.reason,
        )
    except WorkItemNotFoundError as exc:
        _ = write_stderr(text=f"ERROR: {exc}\n")
        return _EXIT_NOT_FOUND
    _ = write_stdout(text=f"closed {closed.id} resolution:{closed.resolution}\n")
    return 0
