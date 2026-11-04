"""Where a run cancelled on its wall budget has its record preserved.

Split out of `_dispatcher_run_wall_budget_watch` by cohesion: that module owns
the DECISION and the cancel, and this owns the export-then-terminate
precondition those depend on — resolving the ledger a pointer is written to,
writing it, reading it back, and reporting which measurement failed when it
could not be.

AN ABSENT POINTER COVERS EVERY WAY THE PRECONDITION CAN FAIL — no ledger, no
declared factory server to export from, a write that did not land, a read-back
that did not confirm it — because they all mean the same thing to the CANCEL:
nothing durable names this run's tree yet, so the slot is held one more poll
rather than released.

THEY DO NOT MEAN THE SAME THING TO THE HELD RECORD, which is why the failing
measurement travels back beside the absence rather than being reduced to it.
The remedies differ — a ledger this host cannot resolve is a configuration
fault, a write that was refused is a tenant fault, and a write that did not
read back may already have landed — and an operator reading a run of held rows
acts on which reading stopped the cancel.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_export import (
    LedgerComments,
    export_run_reference,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsConnectionError,
    ConnectionPrefixMissingError,
    LivespecConfigUnreadableError,
)

__all__: list[str] = [
    "Preservation",
    "preserved_pointer",
    "run_wall_ledger",
]

_LEDGER_RESOLUTION_ERRORS = (
    LivespecConfigUnreadableError,
    ConnectionPrefixMissingError,
    BeadsConnectionError,
    OSError,
)

# The two measurements that fail BEFORE any export is attempted, each named in
# its own words because the remedies differ: one is a configuration fault on
# the dispatching host and the other is a factory that declares no server to
# export the run's record from. The export's own `detail` names every later
# failure, so these are the only two this module words itself.
_NO_LEDGER_MEASUREMENT = (
    "this host resolved no ledger to write the preserve-by-reference pointer to"
)
_NO_FACTORY_SERVER_MEASUREMENT = (
    "this dispatch's factory declares no server url to export the run's record from"
)


@dataclass(frozen=True, kw_only=True)
class Preservation:
    """Where this run's record is preserved, and what the export measured.

    `failed_measurement` is meaningful on BOTH arms -- the export's own account
    of what it did -- and is read only where `pointer` is None. Two fields
    rather than one union so the held record never has to re-derive a reason
    from an absence.
    """

    pointer: str | None
    failed_measurement: str


def run_wall_ledger(*, repo: Path) -> LedgerComments | None:
    """The narrow comment surface a budget export writes through, or None.

    None is the measurement failure the cancel holds on, and it is returned
    rather than raised for the reason the launcher's own work-item read is
    fail-soft: the watch loop runs beside a live `fabro run`, so an exception
    here would abandon a healthy run over a configuration read.
    """
    resolved = attempt(
        action=lambda: make_beads_client(config=store_config(repo=repo)),
        exceptions=_LEDGER_RESOLUTION_ERRORS,
    )
    if isinstance(resolved, AttemptFailure):
        return None
    return resolved


def preserved_pointer(
    *,
    plan: DispatchPlan,
    runner: CommandRunner,
    run_id: str,
    ledger: LedgerComments | None,
) -> Preservation:
    """Write and read back this run's pointer, or name the measurement that failed."""
    if ledger is None:
        return Preservation(pointer=None, failed_measurement=_NO_LEDGER_MEASUREMENT)
    if plan.fabro_factory_server is None:
        return Preservation(pointer=None, failed_measurement=_NO_FACTORY_SERVER_MEASUREMENT)
    exported = export_run_reference(
        work_item_id=plan.work_item_id,
        # The item is `active` for the life of the dispatch this watch belongs
        # to, so the pointer lands on the ITEM rather than on the journal. A
        # status read here would be a second ledger round trip answering a
        # question the dispatch already settled by claiming the item.
        work_item_status="active",
        run_id=run_id,
        factory_server_url=plan.fabro_factory_server,
        repo=plan.repo,
        fabro_bin=plan.fabro_bin,
        runner=runner,
        ledger=ledger,
    )
    if not exported.exported or exported.comment_id is None:
        return Preservation(pointer=None, failed_measurement=exported.detail)
    return Preservation(pointer=exported.comment_id, failed_measurement=exported.detail)
