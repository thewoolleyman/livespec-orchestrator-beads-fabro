"""Collect ended, owned runs only after their work-item has closed.

The normal reconciliation join deliberately considers non-terminal runs: its
job is to release active scheduler slots.  A terminal run carries no slot, but
its Petri sandbox is only stopped, not deleted.  This separate collector owns
that retention boundary.  It reads the same recorded attribution as the run
reconciler, so clearance, availability-probe, and item-less runs cannot become
collectable merely because they appear in a shared factory inventory.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandRunner,
    JournalWriter,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_preservation_ref_deletion import (
    delete_ended_run_refs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_attribution import (
    FactoryRunInventory,
    attributed_runs,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort

__all__: list[str] = ["collect_closed_ended_runs"]

_CLOSED_ITEM_STATUSES = frozenset({"closed", "done"})
_ENDED_STATUS_KINDS = frozenset({"canceled", "cancelled", "dead", "failed", "succeeded"})
_COLLECTION_STAGE = "ended-run-collected"
_RM_TIMEOUT_SECONDS = 120.0
_RM_OUTPUT_EXCERPT_CHARS = 2000


def collect_closed_ended_runs(
    *,
    inventory: FactoryRunInventory,
    port: FabroPort,
    runner: CommandRunner,
    repo: Path,
    journal: JournalWriter,
    dry_run: bool,
) -> None:
    """Delete ended sandboxes whose recorded work-item is now closed.

    The run's preservation refs are deleted from origin FIRST: once the item is
    closed and the run has ended nothing can push to them or seed from them. A
    deletion the forge refuses is journaled by the deletion and the run is left
    standing, so the next pass finds it again and retries; the item's state is
    never touched here.

    `fabro rm` is deliberately unforced: the server's provider-delete route
    is the collection operation, and its exit code and bounded response are
    journaled so a Cleaned, Preserved or Absent result and any lease-prune
    problem stay visible for diagnosis and for the next periodic pass to retry.
    A targeted inventory collects only its own item's runs.
    """
    for row in attributed_runs(inventory=inventory, include_terminal=True):
        if inventory.only_work_item_id not in (None, row.work_item_id):
            continue
        if not _collectable(status_kind=row.run.status_kind, item_status=row.work_item_status):
            continue
        if dry_run:
            continue
        if not delete_ended_run_refs(
            runner=runner,
            repo=repo,
            journal=journal,
            work_item_id=row.work_item_id,
            run_id=row.run.run_id,
        ):
            continue
        removed = port.rm(
            run_id=row.run.run_id,
            timeout_seconds=_RM_TIMEOUT_SECONDS,
            force=False,
        )
        journal.append(
            record={
                "stage": _COLLECTION_STAGE,
                "run_id": row.run.run_id,
                "factory_name": inventory.factory_name,
                "factory_server_url": inventory.factory_server_url,
                "work_item_id": row.work_item_id,
                "work_item_status": row.work_item_status,
                "rm_exit_code": removed.command.exit_code,
                "rm_stdout": removed.command.stdout.strip()[:_RM_OUTPUT_EXCERPT_CHARS],
                "rm_stderr": removed.command.stderr.strip()[:_RM_OUTPUT_EXCERPT_CHARS],
            }
        )


def _collectable(*, status_kind: str | None, item_status: str | None) -> bool:
    return status_kind in _ENDED_STATUS_KINDS and item_status in _CLOSED_ITEM_STATUSES
