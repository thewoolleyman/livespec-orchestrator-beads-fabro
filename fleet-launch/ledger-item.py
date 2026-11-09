#!/usr/bin/env python3
# PROVISIONAL / EXPERIMENTAL — part of fleet-launch/, a stopgap whose first-class
# replacements are the livespec console application and the committed launch-loop
# tool bd-ib-jr6w7v (see fleet-launch/README.md).
"""Read a work-item's ledger status, or append one ledger comment to it.

Usage: ledger-item.py status <plugin-root> <repo-path> <item-id>
       ledger-item.py comment <plugin-root> <repo-path> <item-id> <body>

``status`` prints ``LEDGER-STATUS <status>`` and exits 0, or prints
``LEDGER-STATUS not-found`` and exits 3. ``comment`` appends the body as one
comment through the installed plugin build's own store seam and exits 0. Exit 2
is a usage error. Run it UNDER the tenant's credential wrapper.
"""

import sys
from pathlib import Path

__all__: list[str] = ["main"]

NOT_FOUND = 3
USAGE_ERROR = 2
STATUS_ARGC = 5
COMMENT_ARGC = 6


def main(*, argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else ""
    expected = {"status": STATUS_ARGC, "comment": COMMENT_ARGC}.get(mode)
    if expected is None or len(argv) != expected:
        print(__doc__)
        return USAGE_ERROR
    plugin, repo, item_id = argv[2], Path(argv[3]), argv[4]
    sys.path.insert(0, f"{plugin}/scripts/bin")
    from _bootstrap import bootstrap

    bootstrap()
    from livespec_orchestrator_beads_fabro._store_comments import (
        append_work_item_comment,
    )
    from livespec_orchestrator_beads_fabro.commands._config import (
        resolve_store_config,
    )
    from livespec_orchestrator_beads_fabro.store import read_work_items

    config = resolve_store_config(cwd=repo, work_items_arg=None)
    if mode == "comment":
        append_work_item_comment(path=config, work_item_id=item_id, body=argv[5])
        return 0
    item = next((i for i in read_work_items(path=config) if i.id == item_id), None)
    if item is None:
        print("LEDGER-STATUS not-found")
        return NOT_FOUND
    print(f"LEDGER-STATUS {item.status}")
    return 0


if __name__ == "__main__":
    sys.exit(main(argv=sys.argv))
