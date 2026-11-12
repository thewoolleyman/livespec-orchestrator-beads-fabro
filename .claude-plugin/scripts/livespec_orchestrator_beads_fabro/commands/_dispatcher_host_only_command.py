"""Read-only CLI projection of the factory-safety routing predicate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_host_only import (
    declares_workflow_scope_refusal,
    is_host_only_item,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_item_ledger_reads import (
    read_dispatch_labels,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_close import load_items
from livespec_orchestrator_beads_fabro.io import write_stdout

__all__: list[str] = ["add_host_only_arguments", "run_host_only_command"]


def add_host_only_arguments(*, parser: argparse.ArgumentParser) -> None:
    """Add the read-only host-only predicate command's arguments."""
    _ = parser.add_argument("--repo", dest="repo", required=True)
    _ = parser.add_argument("--item", dest="item", required=True)
    _ = parser.add_argument("--json", dest="as_json", action="store_true")


def run_host_only_command(*, args: argparse.Namespace) -> int:
    """Print the shared factory-safety routing verdict for one work item."""
    repo = Path(args.repo)
    item = next(candidate for candidate in load_items(repo=repo) if candidate.id == args.item)
    raw_labels = read_dispatch_labels(repo=repo, item=item)
    host_only = is_host_only_item(item=item, raw_labels=raw_labels)
    payload: dict[str, str | bool] = {"work_item_id": item.id, "host_only": host_only}
    if host_only:
        payload["reason"] = (
            "workflow declaration"
            if declares_workflow_scope_refusal(item=item, raw_labels=raw_labels)
            else "factory_safety"
        )
    _ = write_stdout(text=json.dumps(payload, sort_keys=True) + "\n")
    return 0
