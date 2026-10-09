"""Whether a `superseded-run` reading still holds at the moment of the cancel.

`superseded-run` is the one orphan reason whose evidence is a SNAPSHOT.
`_dispatcher_reconcile_runs_attribution.read_journaled_runs` reads the dispatch
journal once, at the head of the pass, and the join then judges an inventory
`fabro ps` returned tens of seconds later. A `dispatch-run-stamp` another
session appends between those two reads leaves the pass holding the PREVIOUS
dispatch's run id for that item — so the run it judges superseded is the NEWEST
one, and cancelling it destroys live work and abandons its item. Measured
2026-10-09 on this tenant: run 01M4FRSXDJX27VJCSCH6F52284 was stamped at
07:26:18Z and a sibling session's pass, whose snapshot predated that stamp,
cancelled it at 07:26:30Z with only its start node complete.

The repair is to RE-TAKE the snapshot immediately before the cancel and ask the
question again. No clock is compared and no run id is decoded: the journal's
append order is the evidence this arm already uses, and the re-read is that
same evidence taken at the moment of the act rather than tens of seconds
earlier. A run the fresh read names as its item's newest stamp is superseded by
nothing, whatever the stale snapshot said.

EVERY ARM THAT CANNOT RE-MEASURE HOLDS, and the direction is the whole point. A
snapshot carrying no source path cannot be re-taken, and a journal that has
become unreadable reads back as no knowledge at all, naming no newest run for
the item. Either way the supersession is UNCONFIRMED and the run keeps running:
a held orphan holds a scheduler slot and is reported, while a wrongly cancelled
run cannot be given back.

Only the `superseded-run` arm is re-confirmed. `item-missing` and
`item-not-active` are read off the LEDGER rather than off this snapshot, and
`blocked-past-grace` carries its own measurement, so none of them goes stale
with the journal and re-reading for them would spend a file read per orphan to
answer a question nothing asked.

The hold carries its OWN reason rather than one of the grace arm's.
`blocked-within-grace` and `blocked-park-unmeasured` both say a human decision
is still waiting; this one says the sweep's evidence was older than the run it
was judging, which is a statement about the sweep and not about the work.

The verdict is carried as the HOLD REASON rather than as a boolean beside one,
so there is no pair of fields that can disagree about whether the cancellation
may proceed.
"""

from __future__ import annotations

from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_attribution import (
    ORPHAN_REASON_SUPERSEDED_RUN,
    JournaledRuns,
    read_journaled_runs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_inputs import (
    ReconcileInputs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_join import OrphanRun

__all__: list[str] = [
    "HOLD_REASON_SUPERSESSION_UNCONFIRMED",
    "SupersessionConfirmation",
    "confirm_supersession",
    "supersession_held",
]

HOLD_REASON_SUPERSESSION_UNCONFIRMED = "supersession-unconfirmed"

_DETAIL_NOT_SUPERSEDED = (
    "this orphan reason does not rest on the journal snapshot, so there is " "nothing to re-confirm"
)
_DETAIL_CONFIRMED = (
    "a fresh read of the dispatch journal still names a different run as this "
    "item's newest launch stamp"
)
_DETAIL_NO_SOURCE = (
    "the journal snapshot names no source path, so it cannot be re-taken and "
    "the supersession cannot be re-confirmed against evidence as new as the run"
)
_DETAIL_UNNAMED = (
    "a fresh read of the dispatch journal names no launch stamp for this item, "
    "so nothing supersedes this run"
)
_DETAIL_NEWEST = (
    "a fresh read of the dispatch journal names THIS run as the item's newest "
    "launch stamp: it was stamped after the snapshot this pass was judging it "
    "against, so it is the newest dispatch rather than a superseded one"
)


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
    if orphan.orphan_reason != ORPHAN_REASON_SUPERSEDED_RUN:
        return _confirmed(newest_run_id=None, detail=_DETAIL_NOT_SUPERSEDED)
    if journaled.source_path is None:
        return _held(newest_run_id=None, detail=_DETAIL_NO_SOURCE)
    fresh = read_journaled_runs(path=journaled.source_path)
    newest = fresh.newest_run_id_by_item.get(orphan.work_item_id)
    if newest is None:
        return _held(newest_run_id=None, detail=_DETAIL_UNNAMED)
    if newest == orphan.run_id:
        return _held(newest_run_id=newest, detail=_DETAIL_NEWEST)
    return _confirmed(newest_run_id=newest, detail=_DETAIL_CONFIRMED)


def supersession_held(*, orphan: OrphanRun, inputs: ReconcileInputs) -> bool:
    """Whether this orphan is held back from the termination path.

    The impure half, kept beside the decision rather than at the survey loop so
    that one place owns both "is the reading still good" and "what the pass does
    about it not being". The loop sees a single predicate, which is what keeps a
    hold from becoming a cancellation by an edit that forgets to check a field.
    """
    confirmation = confirm_supersession(orphan=orphan, journaled=inputs.journaled)
    return confirmation.hold_reason is not None


def _confirmed(*, newest_run_id: str | None, detail: str) -> SupersessionConfirmation:
    return SupersessionConfirmation(
        hold_reason=None,
        newest_run_id=newest_run_id,
        detail=detail,
    )


def _held(*, newest_run_id: str | None, detail: str) -> SupersessionConfirmation:
    return SupersessionConfirmation(
        hold_reason=HOLD_REASON_SUPERSESSION_UNCONFIRMED,
        newest_run_id=newest_run_id,
        detail=detail,
    )
