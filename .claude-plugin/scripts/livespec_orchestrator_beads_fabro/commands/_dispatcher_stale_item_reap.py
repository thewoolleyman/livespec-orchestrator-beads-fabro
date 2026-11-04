"""Reaping a live run whose work-item is no longer dispatchable.

Extracted VERBATIM from `_dispatcher_io_fabro_launcher` when the whole-run wall
budget's arm pushed that module past its LLOC ceiling. The launcher keeps
LAUNCHING AND WATCHING — the `fabro run` thread, the poll loop, the two cancel
decisions — while this owns the one question neither of those answers: is this
run's work-item still THIS dispatch's to run at all?

IT IS NOT A WATCHDOG ARM, which is why it is its own concern rather than a third
branch beside the stall and budget cancels. Those two measure the RUN and decide
it has gone wrong; this reads the LEDGER and finds that the decision was taken
elsewhere — a human moved the item, a reconciliation superseded the dispatch, the
item was closed. The run may be perfectly healthy; it simply has nothing left to
do, and the slot it holds is owed back.

THE LEDGER READ IS FAIL-SOFT IN BOTH OF ITS ARMS, and that direction is
load-bearing: this reader runs beside a LIVE `fabro run`, so a target with no
resolvable configuration or a tenant that cannot be reached must leave the run
alone. Reaping on a failed read would destroy healthy work over a configuration
fault, which is the expensive direction; leaving it costs at most the slot until
the run finishes on its own.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandRunner,
    JournalWriter,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_cancel import (
    FABRO_RM_TIMEOUT_SECONDS,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import fabro_port_for_plan
from livespec_orchestrator_beads_fabro.errors import BeadsCommandError, BeadsConnectionError
from livespec_orchestrator_beads_fabro.store import read_work_items

__all__: list[str] = ["stale_item_reap"]

_STALE_RUN_REAP_STAGE = "stale-run-reap"


def stale_item_reap(
    *,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    run_id: str,
) -> str | None:
    """Reap this run when its item left `active`, returning the status it left for.

    None means the run is still this dispatch's to watch — either the item is
    `active`, or the ledger could not be read, which this module treats the same
    way for the reason its docstring gives.

    The STATUS is returned rather than a boolean because the launcher reports it
    on the dispatch's terminal: "abandoned because work-item X status is Y" is
    what tells an operator which decision overtook the run, and a boolean would
    make every abandonment read the same.
    """
    item_status = _work_item_status(repo=plan.repo, work_item_id=plan.work_item_id)
    if item_status is None or item_status == "active":
        return None
    rm = fabro_port_for_plan(plan=plan, runner=runner).rm(
        run_id=run_id,
        timeout_seconds=FABRO_RM_TIMEOUT_SECONDS,
    )
    journal.append(
        record={
            "work_item_id": plan.work_item_id,
            "stage": _STALE_RUN_REAP_STAGE,
            "run_id": run_id,
            "item_status": item_status,
            "rm_exit_code": rm.command.exit_code,
        }
    )
    return item_status


def _work_item_status(*, repo: Path, work_item_id: str) -> str | None:
    config = store_config(repo=repo) if (repo / ".livespec.jsonc").is_file() else None
    if config is None:
        return None
    try:
        # The ledger read runs during iteration, not generator creation.
        items = list(read_work_items(path=config))
    except (BeadsCommandError, BeadsConnectionError):
        return None
    for item in items:
        if item.id == work_item_id:
            return item.status
    return None
