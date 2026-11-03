"""The start-of-pass refusals the queue-draining loop applies before selection."""

from __future__ import annotations

import argparse
from pathlib import Path

from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    EXIT_FAILURE,
    dispatch_exit_code,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_size_gate import (
    apply_factory_size_dispatch_entry,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_close import (
    emit_outcomes,
    ledger_blocked_after_normalization,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_outcomes import (
    failed_dispatch_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "configuration_or_ledger_exit",
]


def configuration_or_ledger_exit(
    *, args: argparse.Namespace, repo: Path, items: list[WorkItem], journal: JournalFile
) -> int | None:
    """Refuse invalid size configuration before ledger normalization mutates."""
    configuration = apply_factory_size_dispatch_entry(
        cwd=repo,
        path_factory=lambda: store_config(repo=repo),
        items=(),
        journal=journal,
    )
    if not is_successful(configuration):
        failure = unsafe_perform_io(configuration.failure())
        requested_ids = set(args.items or [])
        outcome = failed_dispatch_outcome(
            journal=journal,
            work_item_id=next(iter(sorted(requested_ids)), "dispatcher-loop"),
            stage="configuration",
            detail=failure.detail,
        )
        emit_outcomes(outcomes=[outcome], as_json=args.as_json)
        return dispatch_exit_code(outcomes=[outcome])
    if not args.skip_ledger_check and ledger_blocked_after_normalization(
        items=items,
        config=store_config(repo=repo),
        journal=journal,
    ):
        return EXIT_FAILURE
    return None
