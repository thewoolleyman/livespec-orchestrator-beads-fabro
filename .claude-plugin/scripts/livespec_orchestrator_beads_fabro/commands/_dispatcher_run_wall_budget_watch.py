"""What one watchdog poll does about a run past its whole-run wall budget.

`SPECIFICATION/contracts.md` section "Dispatcher progress watchdog" -> "The
whole-run wall budget": "When the budget is exceeded, the Dispatcher MUST first
export the run's record under the export-then-terminate precondition ...
writing and reading back the preserve-by-reference pointer. Only then MUST it
cancel the run; cancelling the run is what releases its slot." And when the
export cannot be read back it "MUST NOT cancel the run on that export alone",
re-attempts the export and lists the refs on origin on every later poll, and
"MUST cancel the run as soon as either a re-attempted export reads back or a
verified preservation ref exists" (`_dispatcher_run_wall_budget_refs`).

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
The export itself, and which measurement failed when it could not be taken,
live in `_dispatcher_run_wall_budget_preserve`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandRunner,
    JournalWriter,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_export import (
    LedgerComments,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_hold import (
    RunWallHoldState,
    hold_run,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_preserve import (
    preserved_pointer,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_records import (
    run_wall_budget_exceeded_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_refs import (
    PreservationRefsUnobservable,
    VerifiedPreservationRef,
    committed_tip,
    verified_preservation_ref,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_clock import (
    RunWallStart,
    budget_exceeded,
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
    WatchdogRunReading,
    watchdog_run_reading,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort
from livespec_orchestrator_beads_fabro.errors import (
    BeadsConnectionError,
    ConnectionPrefixMissingError,
    LivespecConfigUnreadableError,
)

__all__: list[str] = [
    "RunWallBudgetWatch",
    "RunWallVerdict",
    "RunWallVerdictValue",
    "cancel_run_past_budget",
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


class RunWallVerdict:
    """What one poll decided about its run's whole-run wall budget."""

    WITHIN: Final = RunWallVerdictValue(value="within-budget")
    CANCELLED: Final = RunWallVerdictValue(value="run-wall-budget-exceeded")
    HELD: Final = RunWallVerdictValue(value="run-wall-budget-held")


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
    hold: RunWallHoldState | None = None,
) -> RunWallVerdictValue:
    """Export, cancel and journal a run past its budget; hold it when it cannot.

    A run WITHIN its budget costs nothing at all -- no probe, no ledger read,
    no journal row -- which is what keeps the budget off the per-poll critical
    path of every healthy dispatch.

    The cancel has TWO releases and no others: the export reads back, or a remote
    ref listing of origin shows a verified preservation ref of the run's committed
    tree. A poll that has neither HOLDS, naming every measurement that failed --
    a ref listing that could not be taken is one of them, and is never read as
    "origin holds no ref". `hold` is the per-run count the third consecutive
    held poll escalates on; a caller passing none can never escalate.
    """
    elapsed = slot_holding_seconds(start=start, now_epoch=now_epoch)
    if (
        start is None
        or elapsed is None
        or not budget_exceeded(elapsed_seconds=elapsed, budget=plan.run_wall_budget)
    ):
        return RunWallVerdict.WITHIN
    preserved = preserved_pointer(plan=plan, runner=runner, run_id=run_id, ledger=ledger)
    # The run's own record is read BEFORE anything can destroy it, on both
    # routes to a cancel: `rm -f` is what makes it unavailable.
    reading = watchdog_run_reading(port=port, run_id=run_id)

    def cancel(
        *, pointer: str | None, verified_ref: VerifiedPreservationRef | None
    ) -> RunWallVerdictValue:
        _cancel(
            dispatch_id=dispatch_id,
            plan=plan,
            port=port,
            journal=journal,
            run_id=run_id,
            elapsed_seconds=elapsed,
            start=start,
            reading=reading,
            pointer=pointer,
            verified_ref=verified_ref,
            export_failure=preserved.failed_measurement,
        )
        return RunWallVerdict.CANCELLED

    if preserved.pointer is not None:
        return cancel(pointer=preserved.pointer, verified_ref=None)
    located = verified_preservation_ref(
        runner=runner,
        repo=plan.repo,
        work_item_id=plan.work_item_id,
        run_id=run_id,
        tip_commit=committed_tip(record=reading.record),
    )
    if isinstance(located, VerifiedPreservationRef):
        return cancel(pointer=None, verified_ref=located)
    hold_run(
        state=RunWallHoldState() if hold is None else hold,
        plan=plan,
        journal=journal,
        ledger=ledger,
        run_id=run_id,
        elapsed_seconds=elapsed,
        failed_measurement=_failed_measurement(
            export=preserved.failed_measurement, located=located
        ),
    )
    return RunWallVerdict.HELD


def _failed_measurement(*, export: str, located: PreservationRefsUnobservable | None) -> str:
    """The export's failure, with the ref listing's when it also could not be taken."""
    if isinstance(located, PreservationRefsUnobservable):
        return f"{export}; {located.detail}"
    return export


def _cancel(  # noqa: PLR0913 — kw-only cancel; the dispatch, the two seams, the run and the two measured figures are independent inputs.
    *,
    dispatch_id: str | None,
    plan: DispatchPlan,
    port: FabroPort,
    journal: JournalWriter,
    run_id: str,
    elapsed_seconds: float,
    start: RunWallStart,
    reading: WatchdogRunReading,
    pointer: str | None,
    verified_ref: VerifiedPreservationRef | None,
    export_failure: str,
) -> None:
    """Destroy the run, then write the record of the reading taken BEFORE it.

    The reading is taken by the caller FIRST for the reason the stall cancel's
    is: `rm -f` is what makes the record unavailable, and a reading taken
    afterwards succeeds while describing nothing.
    """
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
                preserved_ref=None if verified_ref is None else verified_ref.ref,
                preserved_ref_commit=None if verified_ref is None else verified_ref.commit,
                export_failed_measurement=export_failure,
            ),
            "rm_exit_code": rm.command.exit_code,
        }
    )


@dataclass(kw_only=True)
class RunWallBudgetWatch:
    """One run's budget clock and the ledger its export writes through.

    MUTABLE, and the one field that moves is the whole reason this exists: the
    clock is fixed ONCE, on the first poll that observed the run `running`, and
    kept for the life of the run. A clock re-derived per poll could move when
    one reading failed and another succeeded, and a budget that moved would
    cancel at a different elapsed figure than its own record names.

    `hold` is the run's count of consecutive held polls, kept here for the same
    reason: a count the loop re-derived per poll could never reach the third
    consecutive hold the escalation is owed at.

    `ledger` is resolved once, before any poll, because it is a property of the
    dispatching host rather than of the run — a per-poll resolution would put a
    configuration read on every poll of every dispatch. None is a host with no
    ledger, which HOLDS a budget cancel rather than taking one.

    It lives here rather than in the watch loop so the loop holds no budget
    state of its own: a loop that tracked the clock itself would be the second
    place the fix-it-once rule above could be broken.
    """

    ledger: LedgerComments | None
    start: RunWallStart | None = None
    hold: RunWallHoldState = field(default_factory=RunWallHoldState)

    def verdict(  # noqa: PLR0913 — kw-only per-poll decision; the dispatch, the three seams, the run and the two clock readings are independent inputs.
        self,
        *,
        dispatch_id: str | None,
        plan: DispatchPlan,
        port: FabroPort,
        runner: CommandRunner,
        journal: JournalWriter,
        run_id: str,
        recorded_epoch: float | None,
        now_epoch: float,
    ) -> RunWallVerdictValue:
        """This poll's budget decision, fixing the clock on the first running poll.

        ONE wall-clock reading serves both the fixing and the measurement, which
        the caller takes and passes in: the instant the clock is fixed at and
        the instant the elapsed figure is measured to are the same poll, so two
        readings would report a span this poll did not observe.

        `recorded_epoch` arrives from the poll's OWN observation rather than
        being read here, which is what keeps the budget off the per-poll probe
        budget entirely: the per-run read the watchdog already takes carries the
        run's record, so the instant costs no round trip — and a second
        `fabro inspect` for it would be a second answer about one run with
        nothing announcing a divergence.
        """
        if self.start is None:
            self.start = run_wall_start_from(
                recorded_epoch=recorded_epoch, observed_at_epoch=now_epoch
            )
        return cancel_run_past_budget(
            dispatch_id=dispatch_id,
            plan=plan,
            port=port,
            runner=runner,
            journal=journal,
            run_id=run_id,
            start=self.start,
            now_epoch=now_epoch,
            ledger=self.ledger,
            hold=self.hold,
        )
