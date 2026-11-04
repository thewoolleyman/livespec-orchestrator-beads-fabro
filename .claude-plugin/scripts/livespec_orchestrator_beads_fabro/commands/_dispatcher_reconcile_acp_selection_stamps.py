"""Which stamped runs one reconcile pass replays, and the three bounds on that set.

Split out of `_dispatcher_reconcile_acp_selection` along its cohesion seam: this
module decides WHICH runs are worth a `fabro inspect`, and that module takes the
reading and applies it. The design record for all three bounds -- the replay
window measured from the journal's newest stamp, the unavailable-attempt
ceiling, and the once-read skip for a run whose outcomes were read while it was
terminal -- is that module's docstring; the constants below are where each bound
is stated.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta

from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_stamp import (
    STAMP_JOURNAL_STAGE,
)
from livespec_orchestrator_beads_fabro.effects import (
    IsoDatetimeParseFailure,
    parse_iso_datetime,
)

__all__: list[str] = [
    "SELECTION_OUTCOMES_READ_STAGE",
    "SELECTION_OUTCOMES_UNAVAILABLE_ATTEMPT_LIMIT",
    "SELECTION_OUTCOMES_UNAVAILABLE_STAGE",
    "SELECTION_REPLAY_WINDOW",
    "StampedRun",
    "stamped_runs",
]

# The stage one unreadable run earns. Its own stage rather than an error row,
# because its SILENCE changes an answer: a run nobody could read leaves every
# standing warning in place, which at the attention lane is indistinguishable
# from a run that executed no fallback.
SELECTION_OUTCOMES_UNAVAILABLE_STAGE = "acp-selection-outcomes-unavailable"

# The stage that records one TERMINAL run's node outcomes as read, so a later pass
# spends no `fabro inspect` on a run whose outcomes cannot change.
SELECTION_OUTCOMES_READ_STAGE = "acp-selection-outcomes-read"

# How far back from the journal's NEWEST stamp a stamp may sit and still be
# replayed. A week of this repository's own dispatch history: a run whose
# terminal node outcomes have not been read within that span will not become
# readable later, because factory run storage is pruned, so the window is this
# lane's reach rather than a throttle on it.
SELECTION_REPLAY_WINDOW = timedelta(days=7)

# How many times one run may be reported unavailable before this lane stops
# asking. The root timer drives a pass every ten minutes, so this is about two
# hours of asking -- long enough to ride out a factory restart or a transient
# outage, and a ceiling rather than one append per pass for ever.
SELECTION_OUTCOMES_UNAVAILABLE_ATTEMPT_LIMIT = 12


@dataclass(frozen=True, kw_only=True)
class StampedRun:
    """One run this factory ran, and the work-item whose selection launched it."""

    run_id: str
    work_item_id: str


def stamped_runs(
    *,
    records: tuple[Mapping[str, object], ...],
    factory: FactoryTarget,
    only_work_item_id: str | None,
) -> tuple[StampedRun, ...]:
    """Every run THIS factory ran that is still inside both of the lane's bounds.

    Keyed by run id so a re-stamped run is replayed once per pass; a stamp
    missing any of the three identities is passed over, because a run nothing
    joins to a selection cannot be evidence about one and guessing the join
    from journal order is exactly what the dispatch id replaced.

    The bounds are the parent lane module's docstring's, and the ORDER between them is
    not load-bearing -- a stamp outside either is passed over, and neither
    reading writes anything. They are applied here rather than inside
    `_replay_one_run` (in the lane module) because the cost this bounds is the `fabro inspect` that
    function OPENS with: a ceiling read after the round trip has been spent
    would bound the journal and not the pass.
    """
    dated = _dated_stamps(records=records)
    if not dated:
        return ()
    horizon = max(instant for instant, _ in dated)
    attempts = _unavailable_attempts(records=records)
    already_read = _terminal_reads(records=records)
    found: dict[str, StampedRun] = {}
    for instant, record in dated:
        target = _replay_target(record=record, factory=factory, only_work_item_id=only_work_item_id)
        if target is None or horizon - instant > SELECTION_REPLAY_WINDOW:
            continue
        if target.run_id in already_read:
            continue
        if attempts.get(target.run_id, 0) >= SELECTION_OUTCOMES_UNAVAILABLE_ATTEMPT_LIMIT:
            continue
        found[target.run_id] = target
    return tuple(found.values())


def _replay_target(
    *,
    record: Mapping[str, object],
    factory: FactoryTarget,
    only_work_item_id: str | None,
) -> StampedRun | None:
    """One stamp as this factory's replay target, or `None` when it is not one."""
    if (
        record.get("dispatch_factory") != factory.name
        or record.get("dispatch_factory_server") != factory.server
    ):
        return None
    run_id = _text(value=record.get("run_id"))
    work_item_id = _text(value=record.get("work_item_id"))
    if run_id is None or work_item_id is None or _text(value=record.get("dispatch_id")) is None:
        return None
    if only_work_item_id is not None and work_item_id != only_work_item_id:
        return None
    return StampedRun(run_id=run_id, work_item_id=work_item_id)


def _dated_stamps(
    *, records: tuple[Mapping[str, object], ...]
) -> tuple[tuple[datetime, Mapping[str, object]], ...]:
    """Every launch stamp this lane can DATE, paired with the instant it read.

    Across every factory, because the window's reference is the journal's own
    newest stamp: a per-factory horizon would let a quiet factory's whole
    history stay in the set for ever, which is the unbounded set arriving one
    factory at a time.
    """
    found: list[tuple[datetime, Mapping[str, object]]] = []
    for record in records:
        if record.get("stage") != STAMP_JOURNAL_STAGE:
            continue
        instant = _instant(value=record.get("at"))
        if instant is not None:
            found.append((instant, record))
    return tuple(found)


def _unavailable_attempts(*, records: tuple[Mapping[str, object], ...]) -> dict[str, int]:
    """How many times this lane has already reported each run unavailable."""
    counts: dict[str, int] = {}
    for record in records:
        run_id = _text(value=record.get("run_id"))
        if record.get("stage") != SELECTION_OUTCOMES_UNAVAILABLE_STAGE or run_id is None:
            continue
        counts[run_id] = counts.get(run_id, 0) + 1
    return counts


def _terminal_reads(*, records: tuple[Mapping[str, object], ...]) -> frozenset[str]:
    """Every run whose outcomes this lane has already read while it was terminal."""
    read: set[str] = set()
    for record in records:
        run_id = _text(value=record.get("run_id"))
        if record.get("stage") == SELECTION_OUTCOMES_READ_STAGE and run_id is not None:
            read.add(run_id)
    return frozenset(read)


def _instant(*, value: object) -> datetime | None:
    """One journal instant as a comparable datetime, or `None` when unreadable.

    The journal writes the `%Y-%m-%dT%H:%M:%SZ` form and this runtime's
    `fromisoformat` does not accept the trailing `Z`, so the suffix is rewritten
    to the offset it means rather than stripped -- a naive datetime would raise
    on comparison against the aware ones every other instant here produces.
    """
    text = _text(value=value)
    if text is None:
        return None
    parsed = parse_iso_datetime(text=text.removesuffix("Z") + "+00:00")
    return None if isinstance(parsed, IsoDatetimeParseFailure) else parsed


def _text(*, value: object) -> str | None:
    """Return a non-empty text identity, otherwise `None`."""
    return value.strip() if isinstance(value, str) and value.strip() else None
