"""Run independent pre-launch steps without waiting for one another.

`## Dispatch pre-launch step attribution and concurrency` requires steps whose
inputs do not depend on another step's result to start together, and requires the
dispatch to apply a refusing step's rule exactly as it would had the steps run one
after another. This module is the one place that equivalence is kept.

THE ANSWER IS THE LOWEST-ORDERED HIT, NOT THE FIRST TO FINISH. Run one after
another, step N is reached only when steps 0..N-1 returned nothing and did not
raise; so a hit at N is the answer, and an exception at N is the answer only when
no earlier step hit. Here every step has been started, so the outcomes are read
back in step order with the same rule: an exception at a LOWER index than the
first hit propagates, and one at a higher index is never consulted.

EVERY STEP HAS COMPLETED BEFORE THIS RETURNS, including those past the hit. The
pool's own exit joins its workers, which is what lets a caller say nothing is
submitted to a factory while a step that could still have withheld the dispatch is
running.

THE PHASES CLOSE IN TABLE ORDER once a concurrent group has finished. Rows that
overlap have no individual CPU to account, so closing them as each ends would
charge the group's CPU to whichever happened to finish first and make the
journaled phase order vary from one dispatch to the next.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from itertools import groupby
from typing import TypeVar

from livespec_orchestrator_beads_fabro.commands._dispatcher_prelaunch_cpu import (
    PrelaunchCheckpoint,
    prelaunch_phase,
)

__all__: list[str] = [
    "RefusalRow",
    "first_concurrent_hit",
    "first_refusal",
]

_Hit = TypeVar("_Hit")

# (ask, exit code, whether the refusal text ends in a newline, phase name, concurrent)
RefusalRow = tuple[Callable[[], str | None], int, bool, str, bool]


def first_concurrent_hit(*, steps: Sequence[Callable[[], _Hit | None]]) -> tuple[int, _Hit] | None:
    """Start every step together; return the lowest-ordered non-None answer.

    `steps` is non-empty. The result is the step's index with its answer, or None
    when no step answered.
    """
    with ThreadPoolExecutor(max_workers=len(steps)) as pool:
        futures = [pool.submit(step) for step in steps]
    for index, future in enumerate(futures):
        answer = future.result()
        if answer is not None:
            return index, answer
    return None


def first_refusal(
    *, rows: Sequence[RefusalRow], checkpoint: PrelaunchCheckpoint
) -> tuple[RefusalRow, str] | None:
    """The refusal the rows produce taken in table order, or None when none refuses.

    Each contiguous run of rows sharing the concurrent flag is one group, and a
    group is only entered when every earlier group returned nothing.
    """
    for concurrent, run in groupby(rows, key=lambda row: row[4]):
        group = tuple(run)
        hit = (
            _concurrent_group(rows=group, checkpoint=checkpoint)
            if concurrent
            else _sequential_group(rows=group, checkpoint=checkpoint)
        )
        if hit is not None:
            index, refusal = hit
            return group[index], refusal
    return None


def _concurrent_group(
    *, rows: tuple[RefusalRow, ...], checkpoint: PrelaunchCheckpoint
) -> tuple[int, str] | None:
    try:
        return first_concurrent_hit(steps=[row[0] for row in rows])
    finally:
        for row in rows:
            checkpoint(name=row[3])


def _sequential_group(
    *, rows: tuple[RefusalRow, ...], checkpoint: PrelaunchCheckpoint
) -> tuple[int, str] | None:
    for index, row in enumerate(rows):
        with prelaunch_phase(checkpoint=checkpoint, name=row[3]):
            refusal = row[0]()
        if refusal is not None:
            return index, refusal
    return None
