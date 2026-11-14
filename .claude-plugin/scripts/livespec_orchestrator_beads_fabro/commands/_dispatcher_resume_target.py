"""Resolve and size-gate the one row `resume --item` names, before observation or walls."""

from __future__ import annotations

import argparse
from pathlib import Path

from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    EXIT_PRECONDITION_ERROR,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_tail import (
    dispatch_tail_exit,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_size_gate import (
    apply_factory_size_dispatch_entry,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_outcomes import (
    failed_dispatch_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.io import write_stderr
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = ["resume_target_or_exit"]


def resume_target_or_exit(
    *,
    args: argparse.Namespace,
    repo: Path,
    items: list[WorkItem],
    journal: JournalFile,
) -> WorkItem | int:
    """Resolve and size-gate the named row before resume observation or walls."""
    item = next((one for one in items if one.id == args.item), None)
    if item is None:
        _ = write_stderr(
            text=(
                f"ERROR: work-item {args.item} not found in the target-tenant"
                f" ({repo.name}); --repo and --item must reference the same tenant\n"
            )
        )
        return EXIT_PRECONDITION_ERROR
    size_result = apply_factory_size_dispatch_entry(
        cwd=repo,
        path_factory=lambda: store_config(repo=repo),
        items=(item,),
        journal=journal,
    )
    if not is_successful(size_result):
        failure = unsafe_perform_io(size_result.failure())
        outcome = failed_dispatch_outcome(
            journal=journal,
            work_item_id=item.id,
            stage="configuration",
            detail=failure.detail,
        )
        return dispatch_tail_exit(args=args, repo=repo, outcome=outcome, journal=journal)
    size_refusals = unsafe_perform_io(size_result.unwrap())
    if size_refusals:
        return dispatch_tail_exit(
            args=args,
            repo=repo,
            outcome=size_refusals[0],
            journal=journal,
        )
    return item
