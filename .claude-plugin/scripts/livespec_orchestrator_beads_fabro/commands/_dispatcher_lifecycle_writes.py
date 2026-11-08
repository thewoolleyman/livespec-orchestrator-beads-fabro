"""The lifecycle write seam that couples a ledger disposition to its run.

THE CHOKEPOINT is `_reconcile(...)` below. Every function in this module ends
at it, and the five valves that dispose of a work-item write through this
module rather than through the store seams directly:

| valve            | entry point here                       | store seam |
| ---              | ---                                    | --- |
| close            | `close_work_item_and_reconcile`        | `append_work_item` |
| accept           | `write_work_item_status_and_reconcile` | `update_work_item_status` |
| move             | `write_work_item_status_and_reconcile` | `update_work_item_status` |
| reconcile-merged | `write_work_item_status_and_reconcile` | `update_work_item_status` |
| resolve-blocked  | `write_blocked_state_and_reconcile`    | `update_work_item_blocked_state` |

The reconciliation is a WRAPPER at this layer rather than a hook inside
`_store_mutations` / `_store_blocked_mutations` for one structural reason: the
store layer is handed a `StoreConfig` and knows nothing about factories, fabro
binaries, or the dispatch journal, and reaching from it into `commands/` would
invert the package's dependency direction. This module is the lowest layer that
can see BOTH the write and the factory, which is what makes it the seam.

It is a wrapper rather than five call-site additions for the reason
`_store_blocked_mutations` gives for owning its own label clear: an exit path
added later inherits the coupling by default instead of having to remember it.

What this module deliberately does NOT cover is any disposition that never
reaches Python — a hand `bd close`, or another repo's session moving an item.
Nothing in-process can observe those. The `orphaned-factory-run` ledger check,
the loop tick's sweep, and the systemd timer are what cover them, and they are
the fail-closed half of the invariant; this seam is the fast path, not the
guarantee.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro import store
from livespec_orchestrator_beads_fabro._store_blocked_mutations import (
    update_work_item_blocked_state,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_reconcile_hook import (
    reconcile_after_lifecycle_write,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = [
    "close_work_item_and_reconcile",
    "write_blocked_state_and_reconcile",
    "write_work_item_status_and_reconcile",
]


def close_work_item_and_reconcile(*, path: StoreConfig, item: WorkItem) -> None:
    """Close an item in place, then reconcile the runs it just disowned."""
    store.append_work_item(path=path, item=item)
    _reconcile(path=path, item_id=item.id, status=item.status)


def write_work_item_status_and_reconcile(
    *,
    path: StoreConfig,
    item_id: str,
    status: str,
    assignee: str | None = None,
    clear_assignee: bool = False,
) -> None:
    """Transition an item's status, then reconcile the runs it just disowned."""
    store.update_work_item_status(
        path=path,
        item_id=item_id,
        status=status,
        assignee=assignee,
        clear_assignee=clear_assignee,
    )
    _reconcile(path=path, item_id=item_id, status=status)


def write_blocked_state_and_reconcile(
    *,
    item_id: str,
    status: str,
    blocked_reason: str | None,
    path: StoreConfig | None = None,
    repo: Path | None = None,
    admission_policy: str | None = None,
) -> None:
    """Rewrite an item's blocked state, then reconcile the runs it disowned.

    The store is named by `path`, or by `repo` for a caller that holds only the
    target repository and so lets the store location be resolved here.
    """
    path = path if path is not None else store_config(repo=cast("Path", repo))
    update_work_item_blocked_state(
        path=path,
        item_id=item_id,
        status=status,
        blocked_reason=blocked_reason,
        admission_policy=admission_policy,
    )
    _reconcile(path=path, item_id=item_id, status=status)


def _reconcile(*, path: StoreConfig, item_id: str, status: str) -> None:
    """The chokepoint: one post-write call, reached from every seam above.

    It runs AFTER the store call returns, so a write that raised never reaches
    it and a run is never reconciled against a disposition that did not land.
    """
    reconcile_after_lifecycle_write(path=path, item_id=item_id, status=status)
