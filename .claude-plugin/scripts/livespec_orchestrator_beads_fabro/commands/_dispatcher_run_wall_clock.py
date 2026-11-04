"""How long one run has held a factory slot, measured against its wall budget.

`SPECIFICATION/contracts.md` section "Dispatcher progress watchdog" -> "The
whole-run wall budget": the clock starts at the instant the factory first
reports the run `running`, read from the run's own record when the record
carries it and otherwise fixed by the first watchdog poll that observed the run
`running`; time spent queued before that instant, `runnable` included, MUST NOT
count, because a queued run holds no slot.

PURE, so every arm is assertable without a factory. The one reading that needs
a factory -- asking the run's record for its running instant -- is taken by the
watch seam that already holds the port, and arrives here as a `recorded_epoch`.

QUEUE TIME IS EXCLUDED STRUCTURALLY RATHER THAN SUBTRACTED. The start is a
value a caller can only build from a reading that OBSERVED the run running, so
there is no expression anywhere in which a `runnable` stretch could be added to
it. A design that measured from the run's submission and subtracted the queue
would need the queue's length -- a second measurement, absent from every record
this fleet can read -- and its failure mode would be a charge nobody could see.

THE START IS FIXED ONCE PER RUN AND THEN KEPT, which is why `RunWallStart`
exists as a value instead of the elapsed seconds being recomputed from a fresh
reading each poll. A clock re-derived per poll could move backwards when one
reading failed and another succeeded, and a budget that moved backwards would
cancel a run at a different elapsed figure than the one its record names.

`source` rides with the instant because the two routes are not equally strong:
a RECORDED instant is the factory's own account of when the slot was taken,
while a FIRST-POLL instant is this host's observation, late by up to one poll
interval. A cancel record naming the elapsed seconds without naming which route
dated them cannot be checked against the run's own history.

THE SUBMISSION INSTANT IS DELIBERATELY NOT IN `RUNNING_SINCE_KEYS`, and that is
the one judgement call worth naming -- the same call `PARKED_SINCE_KEYS` makes
one module over, for the mirror-image reason. `start_time` is the engine's
instant for when the run BEGAN, which includes however long it sat queued, so
reading it would charge a run that waited an hour as `runnable` with an hour of
slot-holding the moment it started working. That is the exact charge the
queue-time clause forbids, and it is invisible: the resulting elapsed figure is
plausible, and the run it cancels early looks like a run that genuinely ran
long. `start_record` is excluded for the same reason -- it is the run's start
intent, not its running transition.

Which key the pinned Fabro build emits for the running transition was NOT
verifiable where this was written, for the reason the grace arm records: the
implementation sandbox reaches no factory and this repository holds no captured
`inspect` payload. The list is therefore a SEARCH, most-specific-first, and an
unmatched record leaves the clock to the first-running-poll fallback the clause
itself provides -- which can never charge queue time, so the fail-closed
direction here costs at most one poll interval of under-charging.
"""

from __future__ import annotations

from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget import RunWallBudget
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import fabro_inspect_record
from livespec_orchestrator_beads_fabro.commands._fabro_record_instant import record_instant_epoch

__all__: list[str] = [
    "FIRST_RUNNING_POLL_SOURCE",
    "RUNNING_SINCE_KEYS",
    "RUN_RECORD_SOURCE",
    "RunWallStart",
    "budget_exceeded",
    "recorded_running_epoch",
    "run_wall_start_from",
    "slot_holding_seconds",
]

# Ordered most-specific-first; see the module docstring for why the run's
# submission instant is absent and why this is a search rather than a schema.
RUNNING_SINCE_KEYS: tuple[str, ...] = (
    "running_at",
    "running_since",
    "started_running_at",
    "running_at_epoch",
)

# Which route dated the clock. Named values rather than a boolean, because a
# record that said only "recorded: false" would leave a reader to guess what
# the other route was.
RUN_RECORD_SOURCE = "run-record"
FIRST_RUNNING_POLL_SOURCE = "first-running-poll"


@dataclass(frozen=True, kw_only=True)
class RunWallStart:
    """When this run's slot-holding clock started, and which route dated it."""

    epoch: float
    source: str


def recorded_running_epoch(*, payload: object | None) -> float | None:
    """The running instant the run's own `inspect` record carries, or None.

    None is the UNMEASURED answer the first-running-poll fallback exists for,
    not a claim that the run is not running: a record this reader cannot match
    says nothing either way, and the caller already knows the run is running
    because that is what fixed the clock at all.
    """
    return record_instant_epoch(
        record=fabro_inspect_record(payload=payload),
        keys=RUNNING_SINCE_KEYS,
    )


def run_wall_start_from(
    *,
    recorded_epoch: float | None,
    observed_at_epoch: float,
) -> RunWallStart:
    """Fix this run's clock from its record, else from the poll that saw it running.

    `observed_at_epoch` is the instant of the poll that OBSERVED the run
    running, which is what makes the fallback incapable of charging queue time:
    a poll that found the run `runnable` never reaches this function.
    """
    if recorded_epoch is None:
        return RunWallStart(epoch=observed_at_epoch, source=FIRST_RUNNING_POLL_SOURCE)
    return RunWallStart(epoch=recorded_epoch, source=RUN_RECORD_SOURCE)


def slot_holding_seconds(*, start: RunWallStart | None, now_epoch: float) -> float | None:
    """How long this run has held its slot, or None when the start is unfixed.

    None is UNMEASURED and never zero. A zero would read as a run that has just
    taken its slot, which compares as comfortably within every budget -- so a
    measurement failure would hide behind a plausible number on exactly the
    path the clause requires not to cancel.

    A start in the FUTURE measures zero rather than a negative span. Clock skew
    between this host and the factory is the ordinary cause, and a negative
    span is both meaningless and, like the zero above, indistinguishable from a
    healthy young run -- except that it would arrive from a start the record
    genuinely named, so there is a measurement to keep rather than to discard.
    """
    if start is None:
        return None
    return max(0.0, now_epoch - start.epoch)


def budget_exceeded(*, elapsed_seconds: float | None, budget: RunWallBudget) -> bool:
    """Whether this run's measured slot-holding time is PAST its budget.

    Strictly greater, per the clause: a run whose slot-holding time equals its
    budget exactly has not exceeded it. An UNMEASURED elapsed is not exceeded
    either, which is the clause's own fail-closed arm -- "the budget is
    unmeasured, and the watchdog MUST NOT cancel on it".
    """
    if elapsed_seconds is None:
        return False
    return elapsed_seconds > budget.seconds
