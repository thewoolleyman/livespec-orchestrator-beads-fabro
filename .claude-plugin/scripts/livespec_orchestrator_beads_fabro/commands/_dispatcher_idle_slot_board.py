"""The configured factory's run board, read side-effect-free and attributed.

Three definitions from the idle-slot clause of
`SPECIFICATION/contracts.md` live here, and each one is a place a looser
reading produces a confident wrong answer.

A row is LIVE when its status is non-terminal, and the set is the run
reconciler's OWN `NON_TERMINAL_STATUS_KINDS` rather than a second list spelled
here: two lists would be two authorities on what a live run is, and they would
disagree the moment one gained a status.

A row is QUEUED when its status is `runnable`. A `submitted` or `pending` row
is NEITHER live nor queued — the Dispatcher starts every run it submits and
creates no approval-gated child run, so such a row is not its dispatch. Both
spellings are simply absent from the non-terminal set, so they fall out of
both counts without a special case.

A live row is ATTRIBUTED to the work-item whose id the Dispatcher stamps into
the run's goal, which is exactly what `FabroRunSummary.work_item_id` carries.
The dispatch journal is deliberately NOT consulted: the audit reads priority
epics across tenants, and this repository's journal knows nothing about another
tenant's dispatches, so a journal-assisted attribution would be complete for
one tenant and blind for the rest.

An unreadable board is UNOBSERVABLE, with both counts `None`. A zero would
read as a factory with nothing on it, which is the one reading that makes the
finding line fire — so the absence is carried as absence, never computed.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from livespec_orchestrator_beads_fabro.commands._acp_factory_run_reader import FactoryRunReader
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_attribution import (
    NON_TERMINAL_STATUS_KINDS,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import FabroRunSummary

__all__: list[str] = [
    "QUEUED_STATUS_KIND",
    "UNOBSERVABLE_BOARD",
    "BoardReading",
    "RunLister",
    "board_reading",
    "read_idle_slot_board",
]

QUEUED_STATUS_KIND = "runnable"


@dataclass(frozen=True, kw_only=True)
class BoardReading:
    """One factory board reading, and everything the audit reads off it.

    `live_count` and `queued_count` are `None` exactly when `observable` is
    False. They are reported as counts of rows on the factory, attributed to
    the Fabro server's own board, and are never presented as an Orchestrator
    bound or as available capacity.
    """

    observable: bool
    live_count: int | None
    queued_count: int | None
    live_item_ids: frozenset[str]


UNOBSERVABLE_BOARD = BoardReading(
    observable=False,
    live_count=None,
    queued_count=None,
    live_item_ids=frozenset(),
)


class RunLister(Protocol):
    """The side-effect-free run listing the audit reads a factory through."""

    def list_runs(self, *, factory: str) -> tuple[FabroRunSummary, ...] | None: ...


def read_idle_slot_board(
    *,
    repo: Path,
    factory: str,
    lister: RunLister | None = None,
) -> BoardReading:
    """Read one declared factory's board, or report it unobservable."""
    resolved = FactoryRunReader(repo=repo) if lister is None else lister
    runs = resolved.list_runs(factory=factory)
    if runs is None:
        return UNOBSERVABLE_BOARD
    return board_reading(runs=runs)


def board_reading(*, runs: Sequence[FabroRunSummary]) -> BoardReading:
    """Project a parsed run listing into the audit's board reading."""
    live = [run for run in runs if run.status_kind in NON_TERMINAL_STATUS_KINDS]
    queued = [run for run in live if run.status_kind == QUEUED_STATUS_KIND]
    return BoardReading(
        observable=True,
        live_count=len(live),
        queued_count=len(queued),
        live_item_ids=frozenset(run.work_item_id for run in live if run.work_item_id is not None),
    )
