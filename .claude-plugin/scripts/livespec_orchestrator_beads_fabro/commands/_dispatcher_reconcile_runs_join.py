"""Pure classification of a factory's attributed runs into orphans and holds.

The reconciler's whole safety argument lives here: an ORPHAN is a run the
LEDGER says nothing is waiting on, and every other run is left alone. The
attribution beneath this layer decides which item each run belongs to and
whether the ledger has a moot-question reason for it
(`_dispatcher_reconcile_runs_attribution.py`); this layer decides what
becomes of each row.

One arm is NOT about mootness. A run parked in a human-input-required state
whose item is still live has a question nobody has answered, so the
moot-question reasons do not reach it; the grace arm bounds how long it may
hold a slot on that basis, and it OVERRIDES the moot reading for exactly
that population. An item resting at `blocked` reads as `item-not-active` to
the attribution layer — true, and beside the point, because
`blocked / needs-human` is the ledger state a LIVE decision waits in. Left
alone, that reading would terminate the parked run the instant it was seen,
which is the behaviour the ratified grace exists to replace. A SUPERSEDED
run keeps the moot reading: another run now owns the item, so its question
really has stopped mattering and there is nothing left to wait for.

Orphans and holds come out as SEPARATE collections rather than as one list
carrying a disposition field. Only orphans reach the termination path, and a
held run cannot be handed to it by a caller that forgot to check a flag.
"""

from __future__ import annotations

from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_attribution import (
    ORPHAN_REASON_SUPERSEDED_RUN,
    AttributedRun,
    FactoryRunInventory,
    attributed_runs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_grace import (
    ORPHAN_REASON_BLOCKED_PAST_GRACE,
    BlockedRunGrace,
    HeldRun,
    grace_hold_reason,
    seconds_remaining,
)

__all__: list[str] = [
    "OrphanRun",
    "blocked_grace_candidate_ids",
    "classify_blocked_holds",
    "classify_orphans",
]

_BLOCKED_STATUS_KIND = "blocked"
# The ledger statuses under which a parked run's question is still LIVE:
# `active` is work in flight, and `blocked` is a decision waiting on a human.
# Every other status means the ledger has moved on.
_LIVE_ITEM_STATUSES = ("active", "blocked")


@dataclass(frozen=True, kw_only=True)
class OrphanRun:
    """One non-terminal run this ledger says nothing is waiting on.

    `parked_seconds` and `grace_seconds` are populated only on the
    `blocked-past-grace` arm, and they are the whole justification for that
    arm: the record that terminated a run whose question was NOT moot has to
    carry the measurement and the bound it exceeded, or nobody can tell a
    correct reap from a misread clock.
    """

    run_id: str
    factory_name: str
    factory_server_url: str
    status_kind: str
    work_item_id: str
    work_item_status: str | None
    orphan_reason: str
    parked_seconds: float | None = None
    grace_seconds: int | None = None
    tenant: str = ""
    attribution_source: str = "journal"


@dataclass(frozen=True, kw_only=True)
class _GraceReading:
    """One run's final orphan reason beside the measurement behind it."""

    reason: str | None
    parked_seconds: float | None = None
    grace_seconds: int | None = None


def classify_orphans(
    *,
    inventory: FactoryRunInventory,
    grace: BlockedRunGrace | None = None,
) -> tuple[OrphanRun, ...]:
    """Return the orphans among one factory's runs, leaving every other run."""
    orphans: list[OrphanRun] = []
    for row in attributed_runs(inventory=inventory):
        reading = _reason_with_grace(row=row, inventory=inventory, grace=grace)
        if reading.reason is None:
            continue
        orphans.append(
            OrphanRun(
                run_id=row.run.run_id,
                factory_name=inventory.factory_name,
                factory_server_url=inventory.factory_server_url,
                status_kind=str(row.run.status_kind),
                work_item_id=row.work_item_id,
                tenant=inventory.id_prefix,
                attribution_source=row.attribution_source,
                work_item_status=row.work_item_status,
                orphan_reason=reading.reason,
                parked_seconds=reading.parked_seconds,
                grace_seconds=reading.grace_seconds,
            )
        )
    return tuple(orphans)


def blocked_grace_candidate_ids(*, inventory: FactoryRunInventory) -> tuple[str, ...]:
    """The run ids the grace arm governs, named BEFORE their parks are measured.

    Measuring a park costs a `fabro inspect` per run, so the caller asks which
    runs are worth the call rather than inspecting the whole inventory.
    """
    return tuple(
        row.run.run_id
        for row in attributed_runs(inventory=inventory)
        if _grace_governed(row=row, inventory=inventory)
    )


def classify_blocked_holds(
    *,
    inventory: FactoryRunInventory,
    grace: BlockedRunGrace | None = None,
) -> tuple[HeldRun, ...]:
    """The parked runs the grace arm is holding — reported, never terminated."""
    if grace is None or grace.grace_seconds <= 0:
        return ()
    held: list[HeldRun] = []
    for row in attributed_runs(inventory=inventory):
        if not _grace_governed(row=row, inventory=inventory):
            continue
        parked = grace.parked_seconds_by_run.get(row.run.run_id)
        hold_reason = grace_hold_reason(parked_seconds=parked, grace_seconds=grace.grace_seconds)
        if hold_reason == ORPHAN_REASON_BLOCKED_PAST_GRACE:
            continue
        held.append(_held_run(row=row, inventory=inventory, grace=grace, parked=parked))
    return tuple(held)


def _held_run(
    *,
    row: AttributedRun,
    inventory: FactoryRunInventory,
    grace: BlockedRunGrace,
    parked: float | None,
) -> HeldRun:
    return HeldRun(
        run_id=row.run.run_id,
        factory_name=inventory.factory_name,
        factory_server_url=inventory.factory_server_url,
        status_kind=str(row.run.status_kind),
        work_item_id=row.work_item_id,
        work_item_status=row.work_item_status,
        hold_reason=grace_hold_reason(parked_seconds=parked, grace_seconds=grace.grace_seconds),
        parked_seconds=parked,
        seconds_remaining=seconds_remaining(
            parked_seconds=parked, grace_seconds=grace.grace_seconds
        ),
        grace_seconds=grace.grace_seconds,
    )


def _grace_governed(*, row: AttributedRun, inventory: FactoryRunInventory) -> bool:
    if inventory.only_work_item_id not in (None, row.work_item_id):
        return False
    return (
        row.run.status_kind == _BLOCKED_STATUS_KIND
        and row.work_item_status in _LIVE_ITEM_STATUSES
        and row.base_reason != ORPHAN_REASON_SUPERSEDED_RUN
    )


def _reason_with_grace(
    *,
    row: AttributedRun,
    inventory: FactoryRunInventory,
    grace: BlockedRunGrace | None,
) -> _GraceReading:
    """One run's orphan reason, with the measurement that justifies a reap.

    The reason and its measurement are decided together rather than looked up
    twice: `blocked-past-grace` is the ONE arm whose justification is a number
    taken against a clock, and a record carrying the reason without the number
    it was read from cannot be checked afterwards.
    """
    governed = _grace_governed(row=row, inventory=inventory)
    if grace is None or grace.grace_seconds <= 0 or not governed:
        return _GraceReading(reason=row.base_reason)
    parked = grace.parked_seconds_by_run.get(row.run.run_id)
    hold_reason = grace_hold_reason(parked_seconds=parked, grace_seconds=grace.grace_seconds)
    if hold_reason != ORPHAN_REASON_BLOCKED_PAST_GRACE:
        return _GraceReading(reason=None)
    return _GraceReading(
        reason=hold_reason,
        parked_seconds=parked,
        grace_seconds=grace.grace_seconds,
    )
