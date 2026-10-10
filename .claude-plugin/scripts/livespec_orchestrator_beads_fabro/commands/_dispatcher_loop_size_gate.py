"""Factory-size entry gate for the queue-draining dispatch command."""

from __future__ import annotations

import argparse
from pathlib import Path

from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    dispatch_exit_code,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_size_gate import (
    apply_factory_size_dispatch_entry,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_close import emit_outcomes
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_outcomes import (
    failed_dispatch_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = ["factory_size_loop_exit"]


def factory_size_loop_exit(
    *, args: argparse.Namespace, repo: Path, items: list[WorkItem], journal: JournalFile
) -> int | None:
    """Apply the size gate before the loop enumerates or filters candidates."""
    requested_ids = set(args.items or [])
    size_items = (
        ()
        if args.dry_run
        else tuple(
            item
            for item in items
            if item.status == "ready" or (requested_ids and item.id in requested_ids)
        )
    )
    size_result = apply_factory_size_dispatch_entry(
        cwd=repo,
        path_factory=lambda: store_config(repo=repo),
        items=size_items,
        journal=journal,
    )
    if not is_successful(size_result):
        failure = unsafe_perform_io(size_result.failure())
        work_item_id = next(iter(sorted(requested_ids)), "dispatcher-loop")
        outcomes = [
            failed_dispatch_outcome(
                journal=journal,
                work_item_id=work_item_id,
                stage="configuration",
                detail=failure.detail,
            )
        ]
        emit_outcomes(outcomes=outcomes, as_json=args.as_json)
        return dispatch_exit_code(outcomes=outcomes)
    size_refusals = list(unsafe_perform_io(size_result.unwrap()))
    if size_refusals:
        emit_outcomes(outcomes=size_refusals, as_json=args.as_json)
        return dispatch_exit_code(outcomes=size_refusals)
    return None
