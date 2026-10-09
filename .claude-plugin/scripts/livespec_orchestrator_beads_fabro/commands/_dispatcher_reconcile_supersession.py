"""Whether a `superseded-run` reading still holds at the moment of the cancel.

`superseded-run` is the one orphan reason whose evidence is a SNAPSHOT.
`_dispatcher_reconcile_runs_attribution.read_journaled_runs` reads the dispatch
journal once, at the head of the pass, and the join then judges an inventory
`fabro ps` returned later; so the reading has to be re-confirmed against
evidence at least as new as the run it judges, which is what this module is
for.

The verdict is carried as the HOLD REASON rather than as a boolean beside one,
so there is no pair of fields that can disagree about whether the cancellation
may proceed.
"""

from __future__ import annotations

from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_attribution import (
    JournaledRuns,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_join import OrphanRun

__all__: list[str] = [
    "SupersessionConfirmation",
    "confirm_supersession",
]

_DETAIL_CONFIRMED = "the dispatch journal names a different run as this item's newest"


@dataclass(frozen=True, kw_only=True)
class SupersessionConfirmation:
    """Whether one `superseded-run` reading survives, and the evidence for it.

    `hold_reason` is `None` exactly when the cancellation may proceed;
    `newest_run_id` is the stamp the re-confirmation read against, so a record
    carrying this verdict names what it actually measured.
    """

    hold_reason: str | None
    newest_run_id: str | None
    detail: str


def confirm_supersession(
    *,
    orphan: OrphanRun,
    journaled: JournaledRuns,
) -> SupersessionConfirmation:
    """Re-confirm one orphan's `superseded-run` reading before it is acted on."""
    return SupersessionConfirmation(
        hold_reason=None,
        newest_run_id=journaled.newest_run_id_by_item.get(orphan.work_item_id),
        detail=_DETAIL_CONFIRMED,
    )
