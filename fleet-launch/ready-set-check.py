#!/usr/bin/env python3
# PROVISIONAL / EXPERIMENTAL — part of fleet-launch/, a stopgap whose first-class
# replacements are the livespec console application and the committed launch-loop
# tool bd-ib-jr6w7v (see fleet-launch/README.md).
"""Report whether a work-item is in the Dispatcher's own ready set.

It asks the installed plugin build's ``ready_items()``, so the answer cannot diverge
from the Dispatcher's ``--item`` selection.

Usage: ready-set-check.py <plugin-root> <repo-path> <item-id> [capacity]
Exit 0: dispatchable (in the ready set, or pending-approval, which the loop admits
itself). Exit 3: not in the ready set, with the reason printed. Exit 2: usage error.

With the trailing `capacity` argument it instead prints one JSON object carrying the
repository's counted-claims count, the status of each counted work item (for the
launcher's in-flight early-yield margin), and its configured `wip_cap`, then exits 0.
"""

import json
import sys
from pathlib import Path

__all__: list[str] = ["main"]

NOT_READY = 3
USAGE_ERROR = 2
ARGC = 4
CAPACITY_ARGC = 5


def main(*, argv: list[str]) -> int:
    if len(argv) not in (ARGC, CAPACITY_ARGC) or (
        len(argv) == CAPACITY_ARGC and argv[4] != "capacity"
    ):
        print(__doc__)
        return USAGE_ERROR
    plugin, repo, item_id = argv[1], Path(argv[2]), argv[3]
    sys.path.insert(0, f"{plugin}/scripts/bin")
    from _bootstrap import bootstrap

    bootstrap()
    if len(argv) == CAPACITY_ARGC:
        return _capacity(repo=repo)
    from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
    from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_selection import (
        ready_items,
    )
    from livespec_orchestrator_beads_fabro.store import read_work_items

    items = list(read_work_items(path=resolve_store_config(cwd=repo, work_items_arg=None)))
    me = next((i for i in items if i.id == item_id), None)
    if me is None:
        print(f"READY-CHECK {item_id}: not found")
        return NOT_READY
    if me.status == "pending-approval":
        print(f"READY-CHECK {item_id}: pending-approval (the loop's admission decides)")
        return 0
    if item_id in {i.id for i in ready_items(items=items, repo=repo)}:
        print(f"READY-CHECK {item_id}: in the ready set")
        return 0
    by_id = {i.id: i for i in items}
    deps = [
        getattr(d, "work_item_id", None)
        or (d.get("work_item_id") if isinstance(d, dict) else str(d))
        for d in (me.depends_on or ())
    ]
    # The beads projection reports a closed item as `done`, so a dependency at either status is
    # satisfied and is never an open blocker.
    blockers = [
        f"{d}={by_id[d].status}"
        for d in deps
        if d in by_id and by_id[d].status not in ("closed", "done")
    ]
    print(
        f"READY-CHECK {item_id}: NOT in the ready set (status={me.status} "
        f"assignee={me.assignee} open blockers: {blockers or 'none visible'})"
    )
    return NOT_READY


def _capacity(*, repo: Path) -> int:
    from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
    from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_reclaim import (
        claimed_active_projection,
    )
    from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
    from livespec_orchestrator_beads_fabro.commands._dispatcher_valves import (
        DEFAULT_WIP_CAP,
        resolve_wip_cap,
    )
    from livespec_orchestrator_beads_fabro.store import read_work_items
    from returns.unsafe import unsafe_perform_io

    items = list(read_work_items(path=resolve_store_config(cwd=repo, work_items_arg=None)))
    cap = unsafe_perform_io(resolve_wip_cap(cwd=repo).value_or(DEFAULT_WIP_CAP))
    accounting = claimed_active_projection(
        repo=repo,
        items=items,
        journal=JournalFile(path=repo / "tmp" / "fabro-dispatch-journal.jsonl"),
    )
    counted_ids = set(accounting.live_lock_active_ids) | set(
        accounting.journal_unreadable_active_ids
    )
    counted_statuses = {item.id: item.status for item in items if item.id in counted_ids}
    print(
        json.dumps(
            {
                "counted_claims": accounting.active_count,
                "wip_cap": cap,
                "counted_item_statuses": counted_statuses,
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(argv=sys.argv))
