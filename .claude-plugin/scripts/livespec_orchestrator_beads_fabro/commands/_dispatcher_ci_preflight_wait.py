"""The bounded wait a still-running default branch earns before any verdict.

Split out of `_dispatcher_ci_preflight` along the cohesion seam between
CLASSIFYING one reading of the default branch -- which stays there, with the
lookups it drives -- and REPEATING that reading until it yields a verdict,
which is all this module does. The two change for different reasons: a policy
change about what counts as proof touches only the classifier, and a change to
the cadence or the window touches only this.

WHY A WAIT EXISTS AT ALL. A run that has not concluded has not failed, and this
repository's default branch re-runs CI on every merge, so a preflight that
refused on a pending run reported healthy work as a failure -- and pushed a
retry loop onto every caller, a loop that then raced the newer runs the merges
kept starting (`SPECIFICATION/contracts.md`, "A still-running master CI run is
not a failure").

THE READING IS RE-TAKEN WHOLE, NEVER NARROWED TO THE RUN FIRST SEEN. `read` is
the caller's entire default-branch classification, so a newer run that starts
during the wait -- because the default branch moved, which is precisely what
keeps happening here -- BECOMES the run being waited on. Polling only the first
run's aggregate job would be cheaper and would answer confidently about a run
nobody is waiting for any more.

ONLY A PENDING READING WAITS. Every other unprovable condition -- no usable
credential, an unresolvable pipeline, no runs yet, a conclusion that is neither
green nor red -- is returned the instant it is read, because no amount of
waiting repairs any of them and the bound would turn each into a half-hour
stall on every dispatch.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_ci_pipeline_view import (
    MasterCiPipeline,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_ci_preflight_refusals import (
    MasterCiOutcome,
    pending_outcome,
)

__all__: list[str] = [
    "POLL_INTERVAL_SECONDS",
    "WAIT_BOUND_SECONDS",
    "PendingRun",
    "awaited_outcome",
]

# Both figures are RATIFIED rather than tuned, and they are not the same KIND of
# figure: the window is measured from the start of the preflight, while the
# interval is a CEILING on each poll and not a cadence -- which is what lets the
# last poll land exactly at the bound instead of past it.
WAIT_BOUND_SECONDS = 1800.0
POLL_INTERVAL_SECONDS = 60.0


@dataclass(frozen=True, kw_only=True)
class PendingRun:
    """One reading that found the latest run, or its aggregate job, unconcluded.

    It carries the run and the status it was last OBSERVED at rather than a
    verdict, because there is no verdict yet: these two values are what the
    deferral names if the window expires, and what each progress line reports
    while it has not.
    """

    run_id: str
    status: str


def awaited_outcome(
    *,
    pipeline: MasterCiPipeline,
    branch: str,
    read: Callable[[], MasterCiOutcome | PendingRun],
    sleep: Callable[[float], None] | None = None,
    clock: Callable[[], float] | None = None,
) -> MasterCiOutcome:
    """Re-read the default branch until it has a verdict, or the window expires.

    Returns whatever verdict the reading finally yields -- a pass, a red
    refusal, or any unprovable refusal -- and the DEFERRED outcome only when
    the bound expires with the reading still pending.
    """
    sleeper = time.sleep if sleep is None else sleep
    now = time.monotonic if clock is None else clock
    started = now()
    reading = read()
    while isinstance(reading, PendingRun):
        waited = now() - started
        if waited >= WAIT_BOUND_SECONDS:
            return pending_outcome(
                pipeline=pipeline,
                branch=branch,
                run_id=reading.run_id,
                status=reading.status,
                waited_seconds=waited,
            )
        sleeper(min(POLL_INTERVAL_SECONDS, WAIT_BOUND_SECONDS - waited))
        reading = read()
    return reading
