"""The bounded wait a still-running master-CI run earns instead of a refusal.

A RUN THAT HAS NOT CONCLUDED HAS NOT FAILED. The preflight used to read a
still-pending latest default-branch run as an absence of proof and refuse on
it, which reported healthy work as a failure: this repository's default branch
re-runs CI on every merge, so the window recurs constantly -- 12 runs in about
4.5 hours, measured 2026-10-13 -- and every caller hand-rolled its own retry
loop that then raced the newer runs those merges started.

So a pending reading is deliberately NOT an outcome. It is this module's
`PendingReading`, which the classifier returns INSTEAD of a verdict: an outcome
is journaled and ends the step, and the whole point of the ratified waiting rule
is that this observation does neither.

WHY THE EFFECTS ARE A VALUE. The ratified bound is 1800 seconds at a cadence of
no more than 60, so a test that let the real clock and the real `time.sleep` run
would take half an hour to assert one expiry. `MasterCiWait` carries the three
effects the poll loop needs and its defaults ARE production, so no caller has to
know it exists.

WHY ITS DEFAULTS ARE BUILTINS AND THE PROGRESS SEAM IS A STREAM. `time.monotonic`
and `time.sleep` are builtin functions, which implement no descriptor protocol,
so reading one back off a dataclass instance yields the function itself. A
module-level Python `def` placed here as a default would instead bind as a METHOD
on attribute access and receive the instance as its first argument. The progress
line is therefore emitted through `io.write_stderr`'s own injectable `stream`
rather than through a callable wrapper around it, which is also the seam every
other surface in this package already uses to capture its output.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TextIO

__all__: list[str] = [
    "POLL_INTERVAL_SECONDS",
    "WAIT_BOUND_SECONDS",
    "MasterCiWait",
    "PendingReading",
    "master_ci_wait",
    "pending_progress_line",
    "poll_pause",
]

# Ratified in `SPECIFICATION/contracts.md`, "A still-running master CI run is
# not a failure": poll at an interval of no more than 60 seconds, for a bounded
# window of 1800 seconds measured from the START of the preflight -- not from
# the first pending reading, so a slow lookup cannot buy itself a longer wait
# than the one ratified.
WAIT_BOUND_SECONDS = 1800.0
POLL_INTERVAL_SECONDS = 60.0


@dataclass(frozen=True, kw_only=True)
class PendingReading:
    """One poll's reading that the latest run has not reached a verdict yet.

    `status` is the pending status actually observed -- the RUN's own status, or
    the aggregate JOB's when the run itself has completed -- rather than a
    normalized "pending" marker, because the operator-facing line and the
    deferral record both have to name what the forge said.
    """

    run_id: str
    status: str


@dataclass(frozen=True, kw_only=True)
class MasterCiWait:
    """The clock, the pause, the progress stream and the bound the poll loop needs."""

    now: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep
    progress: TextIO | None = None
    bound_seconds: float = WAIT_BOUND_SECONDS


def master_ci_wait(*, waived: bool) -> MasterCiWait:
    """The production wait for one dispatch, given whether the step is waived.

    A WAIVED step gets a bound of ZERO, which makes the first pending reading
    the deferral and lets the step gate waive it at once. The ratified clause
    says a committed `master-ci` waiver still waives the step BEFORE any
    waiting, and the whole bound otherwise sits between the two: a repository
    that has already declared it cannot verify master CI would pay 1800 seconds
    on every dispatch to be told what it said itself.

    The waiver is read by the gate, which has already resolved it to decide
    whether a refusal proceeds, and passed in -- rather than re-read here,
    where a second resolution could disagree with the one the gate will act on.
    """
    return MasterCiWait(bound_seconds=0.0 if waived else WAIT_BOUND_SECONDS)


def pending_progress_line(*, reading: PendingReading, branch: str) -> str:
    """One pending poll's progress line: which run, which status, which branch.

    Ratified so an operator watching a dispatch can tell a WAIT from a HANG,
    which is only true if the line names the run and what the forge said about
    it: a bare "waiting" repeated thirty times is itself indistinguishable from
    a hang. It also states that the run has not failed, because the line an
    operator reads first is the one that has to carry that.
    """
    return (
        f"master-ci preflight: `{branch}` run {reading.run_id} is {reading.status}; "
        "it has not failed. Waiting for its verdict.\n"
    )


def poll_pause(*, waited: float, bound: float) -> float | None:
    """How long to pause before the next poll, or None once the bound is spent.

    The pause is CLAMPED to what is left of the bound rather than being a flat
    cadence, so the last poll lands on the bound instead of overshooting it by
    up to a full interval -- which would make the deferral report a wait longer
    than the one the clause ratifies.
    """
    remaining = bound - waited
    if remaining <= 0:
        return None
    return min(POLL_INTERVAL_SECONDS, remaining)
