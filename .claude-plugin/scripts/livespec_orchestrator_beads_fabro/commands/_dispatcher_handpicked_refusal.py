"""The factory-safety refusal for explicitly selected loop items."""

from __future__ import annotations

import argparse
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_host_only import is_host_only_item
from livespec_orchestrator_beads_fabro.commands._dispatcher_item_ledger_reads import (
    read_dispatch_labels,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_close import load_items
from livespec_orchestrator_beads_fabro.io import write_stderr

__all__: list[str] = ["handpicked_host_only_refusal_exit"]


def handpicked_host_only_refusal_exit(*, args: argparse.Namespace, repo: Path) -> int | None:
    """Refuse a named host-only item before any mutating dispatch preparation."""
    if args.items is None:
        return None
    requested = set(args.items)
    for item in load_items(repo=repo):
        if item.id not in requested:
            continue
        raw_labels = read_dispatch_labels(repo=repo, item=item)
        if is_host_only_item(item=item, raw_labels=raw_labels):
            _ = write_stderr(
                text=(
                    f"REFUSED: work-item {item.id} is host-only; no claim was taken and "
                    "no factory run was created.\n"
                )
            )
            return 5
    return None
