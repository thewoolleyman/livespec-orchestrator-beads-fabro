"""Cancelling a stalled run, and the one journal record that cancellation writes.

Split out of `_dispatcher_io_fabro_launcher` by cohesion once the cancel record
grew the run's own half (`bd-ib-nfbyot`) and pushed that file past its LLOC
ceiling. The launcher keeps LAUNCHING AND WATCHING — the `fabro run` thread, the
poll loop, the stall decision — while this owns what happens once the decision
has been made: read the run's own record while the run still exists, destroy the
run, and write the record.

THE ORDER IS THE WHOLE REASON THESE TWO ACTS LIVE TOGETHER. `fabro rm -f` is
what makes the readings unavailable, so a reading taken afterwards is a reading
of nothing — and it would still SUCCEED, reporting an unobservable run as a run
with no publication. Keeping the probe, the destruction and the record in one
function is what makes that ordering a property of the code rather than a rule a
caller has to remember.

THE PROBE ITSELF moved to `_dispatcher_watchdog_run_probe` when the whole-run
wall budget became the second cancel class taking the same reading. The
ordering rule above still governs THIS function; what is shared is the reading,
because a second copy of it would be a second place for that rule to be got
wrong.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import JournalWriter
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_cancel_record import (
    stall_cancel_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_run_reading import (
    executing_stage,
    last_publish_draft_publication,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_watchdog_run_probe import (
    watchdog_run_reading,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort

__all__: list[str] = [
    "FABRO_RM_TIMEOUT_SECONDS",
    "cancel_stalled_run",
]

# The budget for the `fabro rm -f` that releases the stalled run's slot. PUBLIC
# because the launcher also joins its run thread against it: the two numbers
# have to be the same one, since the thread is waiting for the very `fabro run`
# that this `rm` is what ends.
FABRO_RM_TIMEOUT_SECONDS = 120.0


def cancel_stalled_run(
    *,
    dispatch_id: str | None,
    plan: DispatchPlan,
    port: FabroPort,
    journal: JournalWriter,
    run_id: str,
    quiet_seconds: float | None,
) -> None:
    """`fabro rm -f` the stalled run and journal what governed the decision.

    THREE figures ride the record, and each answers a question the other
    two cannot. `plan.stall_window.seconds` is the resolved interval and
    `quiet_seconds` is the window actually confirmed against it: the
    interval alone cannot be checked — it says what the threshold was,
    never that anything reached it — and the 2026-10-09 incident
    (bd-ib-n44n4e) had to be reconstructed from the run's own event stream
    because the record carried neither figure.

    `plan.stall_window.layer` is the third, and it is the FIRST question
    asked of a cancellation: an interval of 7200 seconds is the fleet
    default on one target and a deliberate repository override on another,
    and only the layer separates them — so only the layer says whether
    raising `dispatcher.stall_timeout_seconds` would have saved this run
    or whether it had already been raised. The interval is read off the
    plan here rather than taken as an argument so the record cannot name
    one window while the decision above graded against another.

    The run's OWN half of the record — the stage it was executing, and the
    pull request and head its last completed `publish_draft` pushed — is
    read BEFORE the `fabro rm`, which is the ordering the whole reading
    depends on: `rm -f` is what destroys the run, and a factory that has
    dropped it answers no `events` and no `inspect`, so a reading taken
    afterwards is a reading of nothing. It would still succeed, reporting
    an unobservable run as a run with no publication — which is a confident
    negative earned from a read that saw nothing, and which reads exactly
    like a correct record of an unpublished run.

    An unreadable probe is journaled as the absence it is rather than
    retried: the run is about to be cancelled either way, and a cancel held
    up by a probe is a factory slot held by a run that has already been
    judged dead.
    """
    reading = watchdog_run_reading(port=port, run_id=run_id)
    rm = port.rm(
        run_id=run_id,
        timeout_seconds=FABRO_RM_TIMEOUT_SECONDS,
    )
    journal.append(
        record={
            **stall_cancel_record(
                work_item_id=plan.work_item_id,
                dispatch_id=dispatch_id,
                run_id=run_id,
                factory=plan.fabro_factory_name,
                executing_stage=executing_stage(events_json=reading.events_json),
                publication=last_publish_draft_publication(
                    events_json=reading.events_json,
                    record_text=reading.record_text,
                ),
            ),
            "rm_exit_code": rm.command.exit_code,
            "stall_seconds": plan.stall_window.seconds,
            "stall_layer": plan.stall_window.layer,
            "quiet_seconds": quiet_seconds,
        }
    )
