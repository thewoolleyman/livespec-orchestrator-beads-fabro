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
    "MasterCiWait",
    "PendingReading",
]


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
    """The clock, the pause and the progress stream the preflight's poll loop needs."""

    now: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep
    progress: TextIO | None = None
