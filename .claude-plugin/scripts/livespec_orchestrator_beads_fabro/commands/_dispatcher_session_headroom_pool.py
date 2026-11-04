"""Choosing ONE credential out of the whole injected slot pool.

`SPECIFICATION/scenarios.md` Scenario 278: a factory dispatch takes its
credential from the best-qualifying slot of the whole injected
`CLAUDE_CODE_OAUTH_TOKEN__*` pool, not from the slot the caam loop selected for
interactive spend. A run keeps the token it was dispatched with, so only the
injected slot's own headroom matters -- measured 2026-10-30, when the
caam-selected account was refused for a headroom shortfall while three other
slots sat at zero utilization and every factory lane starved.

A SLOT QUALIFIES when no headroom shortfall stops it, and the shortfall test is
the SAME `headroom_skip_kind` the per-candidate filter applies (floor, seven-day,
projection; an unobservable reading is a floor skip), so admission cannot qualify
a slot the filter would then skip.

AMONG QUALIFYING SLOTS the ranking is, in order: a slot whose projection was
MEASURED outranks one whose projection is unavailable; then the sooner
provider-reported window reset wins, so quota does not expire unused; a slot
whose reset claim is missing or unreadable ranks after every slot with a
readable one, because nothing says when it would reset; then the larger remaining
headroom; then the slot name, so the choice is deterministic. The reset claim
ranks slots against each other and is never a reason to qualify or skip one --
the projection skip is still decided without it.

WHEN NO SLOT QUALIFIES nothing is chosen, and the REPRESENTATIVE reading -- the
one the per-candidate filter turns into the existing `HEADROOM_SKIP` -- is the
most-headroomed slot, so the refusal that follows reads the nearest miss. Every
reading comes back annotated with a `SlotSelection` naming its slot, skip kind
and fate, which is what lets the refusal name every slot.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, replace

from livespec_orchestrator_beads_fabro.commands._acp_session_headroom import (
    PROJECTED_RESULT,
    SessionHeadroomReading,
    SlotSelection,
)
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom_drain import (
    parse_session_headroom_instant,
)
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom_projection import (
    headroom_skip_kind,
)

__all__: list[str] = [
    "RANKED_LOWER_LATER_RESET",
    "RANKED_LOWER_PROJECTION_UNAVAILABLE",
    "PoolSelection",
    "select_pool_slot",
]

RANKED_LOWER_LATER_RESET = "ranked-lower-later-reset"
RANKED_LOWER_PROJECTION_UNAVAILABLE = "ranked-lower-projection-unavailable"

_NO_REMAINING = -1.0


@dataclass(frozen=True, kw_only=True)
class PoolSelection:
    """The pool's annotated readings, the chosen slot name and the filter's reading."""

    readings: tuple[SessionHeadroomReading, ...]
    chosen_slot: str | None
    representative: SessionHeadroomReading


def select_pool_slot(
    *, readings: Sequence[tuple[str, SessionHeadroomReading]], floor_percent: int
) -> PoolSelection:
    """Rank the pool: the qualifying slot to project, or nothing when none qualifies.

    `readings` is non-empty: a pool with no slot is the caller's single
    absent-credential reading and never reaches the ranking.
    """
    kinds = {
        slot: headroom_skip_kind(reading=reading, floor_percent=floor_percent)
        for slot, reading in readings
    }
    qualifying = sorted(
        (pair for pair in readings if kinds[pair[0]] is None), key=lambda pair: _rank(pair=pair)
    )
    winner = qualifying[0] if qualifying else None
    annotated = tuple(
        replace(
            reading,
            slot=SlotSelection(
                slot=slot,
                skip_kind=kinds[slot],
                chosen=winner is not None and winner[0] == slot,
                not_chosen_reason=_not_chosen_reason(
                    slot=slot,
                    reading=reading,
                    kind=kinds[slot],
                    winner_slot=None if winner is None else winner[0],
                    winner_measured=winner is not None and _measured(reading=winner[1]),
                ),
            ),
        )
        for slot, reading in readings
    )
    by_slot = {reading.slot.slot: reading for reading in annotated if reading.slot is not None}
    if winner is not None:
        return PoolSelection(
            readings=annotated, chosen_slot=winner[0], representative=by_slot[winner[0]]
        )
    return PoolSelection(
        readings=annotated,
        chosen_slot=None,
        representative=max(annotated, key=lambda reading: _remaining(reading=reading)),
    )


def _rank(*, pair: tuple[str, SessionHeadroomReading]) -> tuple[bool, bool, float, float, str]:
    slot, reading = pair
    reset = _reset_epoch(claim=reading.provider_reset_claim)
    return (
        not _measured(reading=reading),
        reset is None,
        0.0 if reset is None else reset,
        -_remaining(reading=reading),
        slot,
    )


def _not_chosen_reason(
    *,
    slot: str,
    reading: SessionHeadroomReading,
    kind: str | None,
    winner_slot: str | None,
    winner_measured: bool,
) -> str | None:
    if kind is not None:
        return f"{kind}-skip"
    if winner_slot == slot:
        return None
    if winner_measured and not _measured(reading=reading):
        return RANKED_LOWER_PROJECTION_UNAVAILABLE
    return RANKED_LOWER_LATER_RESET


def _measured(*, reading: SessionHeadroomReading) -> bool:
    return reading.projection is not None and reading.projection.result == PROJECTED_RESULT


def _remaining(*, reading: SessionHeadroomReading) -> float:
    return _NO_REMAINING if reading.remaining_percent is None else reading.remaining_percent


def _reset_epoch(*, claim: str | None) -> float | None:
    """The provider's reset claim as epoch seconds, or `None` when unreadable.

    The provider sends either epoch seconds or an ISO instant; both are read, and
    anything else ranks as an unknown reset rather than as a guess.
    """
    if claim is None:
        return None
    try:
        seconds = float(claim)
    except ValueError:
        instant = parse_session_headroom_instant(text=claim.strip())
        return None if instant is None else instant.timestamp()
    return seconds if math.isfinite(seconds) else None
