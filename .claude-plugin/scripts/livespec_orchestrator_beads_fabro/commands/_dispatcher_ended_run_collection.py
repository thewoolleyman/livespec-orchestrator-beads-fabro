"""Collect ended, owned runs only after their work-item has closed.

The normal reconciliation join deliberately considers non-terminal runs: its
job is to release active scheduler slots.  A terminal run carries no slot, but
its Petri sandbox is only stopped, not deleted.  This separate collector owns
that retention boundary.  It reads the same recorded attribution as the run
reconciler, so clearance, availability-probe, and item-less runs cannot become
collectable merely because they appear in a shared factory inventory.

The collector serves ONE dispatching repository per call: `repo` is the
repository whose journal and ledger the inventory was attributed against, which
is also the repository whose forge origin holds the run's preservation refs.
`_dispatcher_fleet_run_collection` calls it once per other repository that
dispatches to the same factory, so a repository's runs never depend on a pass of
that repository's own.

Every ended run the inventory attributes and the collector does NOT collect is
a REFUSAL, journaled with the run, its dispatching repository, its work-item and
the status read -- or `None` where no status could be read, which is also what an
unreadable ledger looks like.  A refusal already journaled for the same run at the
same status is not journaled again, because the periodic pass would otherwise
append every standing refusal on every tick.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandRunner,
    JournalWriter,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_journal_tail import (
    journal_tail_records,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_preservation_ref_deletion import (
    delete_ended_run_refs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_attribution import (
    AttributedRun,
    FactoryRunInventory,
    attributed_runs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_rm_pacing import DeletionPacer
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort

__all__: list[str] = [
    "JOURNAL_STAGE_COLLECTION_REFUSED",
    "collect_closed_ended_runs",
    "journaled_refusals",
]

_CLOSED_ITEM_STATUSES = frozenset({"closed", "done"})
_ENDED_STATUS_KINDS = frozenset({"canceled", "cancelled", "dead", "failed", "succeeded"})
_COLLECTION_STAGE = "ended-run-collected"
JOURNAL_STAGE_COLLECTION_REFUSED = "ended-run-collection-refused"
_REASON_NOT_CLOSED = "item-not-closed"
_REASON_NO_STATUS = "item-status-unreadable"
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
    has_running_run = any(run.status_kind == "running" for run in inventory.runs)
    pacer = DeletionPacer(repo=repo)
    for row in attributed_runs(inventory=inventory, include_terminal=True):
        if inventory.only_work_item_id not in (None, row.work_item_id):
            continue
        if row.run.status_kind not in _ENDED_STATUS_KINDS or dry_run:
            continue
        if row.work_item_status not in _CLOSED_ITEM_STATUSES:
            if (row.run.run_id, row.work_item_status) not in inventory.refused_before:
                _journal_refusal(inventory=inventory, repo=repo, journal=journal, row=row)
            continue
        if not pacer.permit(
            factory=inventory.factory_name,
            run_id=row.run.run_id,
            caller="ended-run-collection",
            has_running_run=has_running_run,
            collection=True,
            journal=journal,
        ):
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
                "dispatching_repository": repo.name,
                "work_item_id": row.work_item_id,
                "work_item_status": row.work_item_status,
                "rm_exit_code": removed.command.exit_code,
                "rm_stdout": removed.command.stdout.strip()[:_RM_OUTPUT_EXCERPT_CHARS],
                "rm_stderr": removed.command.stderr.strip()[:_RM_OUTPUT_EXCERPT_CHARS],
            }
        )


def journaled_refusals(*, journal_path: Path | None) -> frozenset[tuple[str, str | None]]:
    """The (run id, item status) pairs whose refusal the journal already holds."""
    if journal_path is None:
        return frozenset()
    refused: set[tuple[str, str | None]] = set()
    for record in journal_tail_records(journal_path=journal_path):
        run_id = record.get("run_id")
        status = record.get("work_item_status")
        if record.get("stage") != JOURNAL_STAGE_COLLECTION_REFUSED or not isinstance(run_id, str):
            continue
        refused.add((run_id, status if isinstance(status, str) else None))
    return frozenset(refused)


def _journal_refusal(
    *,
    inventory: FactoryRunInventory,
    repo: Path,
    journal: JournalWriter,
    row: AttributedRun,
) -> None:
    journal.append(
        record={
            "stage": JOURNAL_STAGE_COLLECTION_REFUSED,
            "run_id": row.run.run_id,
            "factory_name": inventory.factory_name,
            "factory_server_url": inventory.factory_server_url,
            "dispatching_repository": repo.name,
            "work_item_id": row.work_item_id,
            "work_item_status": row.work_item_status,
            "reason": _REASON_NO_STATUS if row.work_item_status is None else _REASON_NOT_CLOSED,
        }
    )
