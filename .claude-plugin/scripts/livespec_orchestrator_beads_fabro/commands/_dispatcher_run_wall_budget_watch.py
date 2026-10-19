"""What one watchdog poll does about a run past its whole-run wall budget.

`SPECIFICATION/contracts.md` section "Dispatcher progress watchdog" -> "The
whole-run wall budget": "When the budget is exceeded, the Dispatcher MUST first
export the run's record under the export-then-terminate precondition ...
writing and reading back the preserve-by-reference pointer. Only then MUST it
cancel the run; cancelling the run is what releases its slot." And when the
export cannot be read back it "MUST NOT cancel the run ... and MUST re-attempt
the export on the next poll, cancelling only once a read-back succeeds."

THE ORDER IS THE WHOLE POINT, and it is a property of this function rather than
a rule a caller remembers: `fabro rm -f` is what makes the run's record
unavailable, so an export attempted after it exports nothing -- and it would
still succeed, reporting a run whose work was just destroyed as a run that had
none. The export, the destruction and the record therefore sit in one function,
in that order, exactly as the stall cancel's do.

THREE VERDICTS, NOT A BOOLEAN, because the launcher owes each a different act
and two of the three must NOT fall through to the stall arm:

* `WITHIN` -- the budget is not exceeded (or is unmeasured). The poll continues
  to the stall decision as it always did.
* `CANCELLED` -- the pointer is durable and the run is gone. The dispatch ends
  on its own outcome.
* `HELD` -- the budget IS exceeded and the export could not be read back. One
  `run-wall-budget-held` record is journaled naming the failed measurement, the
  run keeps its slot for one more poll and the export is re-attempted then --
  and the clause requires that "while the run's budget export is held pending
  its read-back it is not cancelled as stalled-no-progress", so this verdict
  must not be collapsed into `WITHIN`. A quiet run past its budget usually
  satisfies the stall rule as well, so collapsing the two would cancel it as
  stalled -- the wrong record, the wrong disposition, and the pointer the hold
  exists to secure still unwritten.

THE RE-ATTEMPT NEEDS NO STATE HERE. A held poll leaves the run alive, so the
next poll of the same loop measures the same exceeded budget and performs the
same export; `export_run_reference` locates an existing pointer rather than
rewriting one, so a write that landed and a read-back that failed converge on
the second attempt instead of growing the ledger.

THE LEDGER IS AN INJECTED SEAM, and an UNRESOLVABLE one is a failed measurement
rather than a licence to proceed. A cancel taken with no ledger to write to
would destroy a live run with nothing durable naming its tree -- the
discarded-work path the export-then-terminate precondition exists to close.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandRunner,
    JournalWriter,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_export import (
    LedgerComments,
    export_run_reference,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_records import (
    run_wall_budget_exceeded_record,
    run_wall_budget_held_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_clock import (
    RunWallStart,
    budget_exceeded,
    recorded_running_epoch,
    run_wall_start_from,
    slot_holding_seconds,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_cancel import (
    FABRO_RM_TIMEOUT_SECONDS,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_run_reading import (
    executing_stage,
    last_publish_draft_publication,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_watchdog_run_probe import (
    watchdog_run_reading,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsConnectionError,
    ConnectionPrefixMissingError,
    LivespecConfigUnreadableError,
)

__all__: list[str] = [
    "RunWallVerdict",
    "RunWallVerdictValue",
    "cancel_run_past_budget",
    "observe_run_wall_start",
    "run_wall_ledger",
]

_INSPECT_TIMEOUT_SECONDS = 60.0

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
_LEDGER_RESOLUTION_ERRORS = (
    LivespecConfigUnreadableError,
    ConnectionPrefixMissingError,
    BeadsConnectionError,
    OSError,
)


@dataclass(frozen=True, kw_only=True, slots=True)
class RunWallVerdictValue:
    """Enum-like budget verdict value without subclassing."""

    value: str


@dataclass(frozen=True, kw_only=True)
class _Preservation:
    """Where this run's record is preserved, and what the export measured.

    `failed_measurement` is meaningful on BOTH arms -- the export's own account
    of what it did -- and is read only where `pointer` is None. Two fields
    rather than one union so the held record never has to re-derive a reason
    from an absence.
    """

    pointer: str | None
    failed_measurement: str


class RunWallVerdict:
    """What one poll decided about its run's whole-run wall budget."""

    WITHIN: Final = RunWallVerdictValue(value="within-budget")
    CANCELLED: Final = RunWallVerdictValue(value="run-wall-budget-exceeded")
    HELD: Final = RunWallVerdictValue(value="run-wall-budget-held")


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


def observe_run_wall_start(
    *,
    port: FabroPort,
    run_id: str,
    observed_at_epoch: float,
) -> RunWallStart:
    """Fix this run's slot-holding clock, ONCE, on the poll that saw it running.

    One extra `fabro inspect` per DISPATCH rather than per poll: the caller
    keeps the answer for the life of the run, because a clock re-derived each
    poll could move when one reading failed and another succeeded, and a budget
    that moved would cancel at a different elapsed figure than its record names.
    """
    inspected = port.inspect(run_id=run_id, timeout_seconds=_INSPECT_TIMEOUT_SECONDS)
    return run_wall_start_from(
        recorded_epoch=recorded_running_epoch(payload=inspected.payload),
        observed_at_epoch=observed_at_epoch,
    )


def cancel_run_past_budget(  # noqa: PLR0913 — kw-only per-poll decision; the dispatch, the two seams, the run and the clock reading are independent inputs.
    *,
    dispatch_id: str | None,
    plan: DispatchPlan,
    port: FabroPort,
    runner: CommandRunner,
    journal: JournalWriter,
    run_id: str,
    start: RunWallStart | None,
    now_epoch: float,
    ledger: LedgerComments | None,
) -> RunWallVerdictValue:
    """Export, cancel and journal a run past its budget; hold it when it cannot.

    A run WITHIN its budget costs nothing at all -- no probe, no ledger read,
    no journal row -- which is what keeps the budget off the per-poll critical
    path of every healthy dispatch.
    """
    elapsed = slot_holding_seconds(start=start, now_epoch=now_epoch)
    if (
        start is None
        or elapsed is None
        or not budget_exceeded(elapsed_seconds=elapsed, budget=plan.run_wall_budget)
    ):
        return RunWallVerdict.WITHIN
    preserved = _preserved_pointer(plan=plan, runner=runner, run_id=run_id, ledger=ledger)
    if preserved.pointer is None:
        journal.append(
            record=run_wall_budget_held_record(
                work_item_id=plan.work_item_id,
                run_id=run_id,
                elapsed_seconds=elapsed,
                budget=plan.run_wall_budget,
                failed_measurement=preserved.failed_measurement,
            )
        )
        return RunWallVerdict.HELD
    _cancel(
        dispatch_id=dispatch_id,
        plan=plan,
        port=port,
        journal=journal,
        run_id=run_id,
        elapsed_seconds=elapsed,
        start=start,
        pointer=preserved.pointer,
    )
    return RunWallVerdict.CANCELLED


def _preserved_pointer(
    *,
    plan: DispatchPlan,
    runner: CommandRunner,
    run_id: str,
    ledger: LedgerComments | None,
) -> _Preservation:
    """Where this run's record is durably preserved, or which measurement failed.

    An absent pointer covers every way the precondition can fail -- no ledger,
    no declared factory server to export from, a write that did not land, a
    read-back that did not confirm it -- because they all mean the same thing
    to the CANCEL: nothing durable names this run's tree yet, so the slot is
    held one more poll rather than released.

    They do NOT mean the same thing to the HELD RECORD, which is why the
    failing measurement travels back beside the absence rather than being
    reduced to it. The remedies differ, and an operator reading a run of held
    rows acts on which reading stopped the cancel.
    """
    if ledger is None:
        return _Preservation(pointer=None, failed_measurement=_NO_LEDGER_MEASUREMENT)
    if plan.fabro_factory_server is None:
        return _Preservation(pointer=None, failed_measurement=_NO_FACTORY_SERVER_MEASUREMENT)
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
        return _Preservation(pointer=None, failed_measurement=exported.detail)
    return _Preservation(pointer=exported.comment_id, failed_measurement=exported.detail)


def _cancel(  # noqa: PLR0913 — kw-only cancel; the dispatch, the two seams, the run and the two measured figures are independent inputs.
    *,
    dispatch_id: str | None,
    plan: DispatchPlan,
    port: FabroPort,
    journal: JournalWriter,
    run_id: str,
    elapsed_seconds: float,
    start: RunWallStart,
    pointer: str,
) -> None:
    """Read the run's own record, destroy the run, then write the record.

    The reading comes FIRST for the reason the stall cancel's does: `rm -f` is
    what makes the record unavailable, and a reading taken afterwards succeeds
    while describing nothing.
    """
    reading = watchdog_run_reading(port=port, run_id=run_id)
    rm = port.rm(run_id=run_id, timeout_seconds=FABRO_RM_TIMEOUT_SECONDS)
    journal.append(
        record={
            **run_wall_budget_exceeded_record(
                work_item_id=plan.work_item_id,
                dispatch_id=dispatch_id,
                run_id=run_id,
                factory=plan.fabro_factory_name,
                executing_stage=executing_stage(events_json=reading.events_json),
                publication=last_publish_draft_publication(
                    events_json=reading.events_json,
                    record_text=reading.record_text,
                ),
                elapsed_seconds=elapsed_seconds,
                budget=plan.run_wall_budget,
                start_source=start.source,
                preserved_pointer=pointer,
            ),
            "rm_exit_code": rm.command.exit_code,
        }
    )
