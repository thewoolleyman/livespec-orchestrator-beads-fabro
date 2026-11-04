"""Choosing ONE credential out of the whole injected slot pool.

Binds Scenario 278 ("A factory dispatch takes its credential from the whole
slot pool, preferring the sooner window reset, and refuses only when no slot
qualifies") in `SPECIFICATION/scenarios.md`. A slot qualifies when no headroom
shortfall (floor, seven-day or projection) stops it; among qualifying slots a
measured projection outranks an unavailable one and the sooner provider-reported
window reset wins; when none qualifies nothing is chosen and every slot is named
with its skip kind.
"""

from __future__ import annotations

import dataclasses
import importlib
from pathlib import Path
from types import ModuleType

from livespec_orchestrator_beads_fabro.commands import _acp_session_headroom as headroom

_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_session_headroom_pool.py"
)
_NOW = "2026-10-30T22:00:00Z"
_FLOOR = 20
_HOUR_SECONDS = 3600
_RESET_BASE = 1_761_800_000


def _pool() -> ModuleType:
    assert _MODULE_PATH.is_file(), "the slot-pool ranking module must exist"
    return importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_session_headroom_pool"
    )


def _reading(
    *,
    identity: str,
    utilization: float | None,
    reset_hours: float | None = None,
    measured: bool = False,
    reset_claim: str | None = None,
) -> headroom.SessionHeadroomReading:
    claim = reset_claim
    if reset_hours is not None:
        claim = str(int(_RESET_BASE + reset_hours * _HOUR_SECONDS))
    if utilization is None:
        reading = headroom.unobservable_session_headroom(
            credential_identity=identity,
            observed_at=_NOW,
            reason="transport-failed",
            provider_reset_claim=claim,
        )
    else:
        reading = headroom.session_headroom_reading(
            credential_identity=identity,
            observed_at=_NOW,
            utilization=utilization,
            provider_reset_claim=claim,
        )
    result = headroom.PROJECTED_RESULT if measured else headroom.UNAVAILABLE_RESULT
    return dataclasses.replace(
        reading, projection=headroom.SessionHeadroomProjection(result=result)
    )


def _by_slot(*, selection: object) -> dict[str, headroom.SessionHeadroomReading]:
    readings: tuple[headroom.SessionHeadroomReading, ...] = selection.readings  # type: ignore[attr-defined]
    return {reading.slot.slot: reading for reading in readings if reading.slot is not None}


def test_a_floor_short_slot_loses_to_a_qualifying_slot_and_names_the_floor_skip() -> None:
    pool = _pool()

    selection = pool.select_pool_slot(
        readings=(
            ("CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_2", _reading(identity="id2", utilization=90)),
            ("CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_3", _reading(identity="id3", utilization=0)),
        ),
        floor_percent=_FLOOR,
    )

    slots = _by_slot(selection=selection)
    assert selection.chosen_slot == "CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_3"
    chosen = slots["CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_3"].slot
    assert chosen is not None
    assert chosen.chosen is True
    assert chosen.not_chosen_reason is None
    rejected = slots["CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_2"].slot
    assert rejected is not None
    assert (rejected.chosen, rejected.skip_kind, rejected.not_chosen_reason) == (
        False,
        "floor",
        "floor-skip",
    )


def test_two_qualifying_slots_choose_the_sooner_window_reset() -> None:
    pool = _pool()

    selection = pool.select_pool_slot(
        readings=(
            (
                "CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_3",
                _reading(identity="id3", utilization=10, reset_hours=4),
            ),
            (
                "CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_4",
                _reading(identity="id4", utilization=30, reset_hours=1),
            ),
            ("CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_2", _reading(identity="id2", utilization=95)),
        ),
        floor_percent=_FLOOR,
    )

    slots = _by_slot(selection=selection)
    assert selection.chosen_slot == "CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_4"
    loser = slots["CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_3"].slot
    assert loser is not None
    assert (loser.skip_kind, loser.not_chosen_reason) == (None, "ranked-lower-later-reset")


def test_a_measured_qualifying_projection_outranks_an_unavailable_one() -> None:
    pool = _pool()

    selection = pool.select_pool_slot(
        readings=(
            (
                "CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_3",
                _reading(identity="id3", utilization=10, reset_hours=1, measured=False),
            ),
            (
                "CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_4",
                _reading(identity="id4", utilization=10, reset_hours=3, measured=True),
            ),
        ),
        floor_percent=_FLOOR,
    )

    slots = _by_slot(selection=selection)
    assert selection.chosen_slot == "CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_4"
    loser = slots["CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_3"].slot
    assert loser is not None
    assert loser.not_chosen_reason == "ranked-lower-projection-unavailable"


def test_a_slot_with_no_reset_claim_ranks_after_one_with_a_reset_claim() -> None:
    pool = _pool()

    selection = pool.select_pool_slot(
        readings=(
            ("CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_2", _reading(identity="id2", utilization=5)),
            (
                "CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_3",
                _reading(identity="id3", utilization=50, reset_claim="2026-10-30T23:00:00Z"),
            ),
        ),
        floor_percent=_FLOOR,
    )

    assert selection.chosen_slot == "CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_3"


def test_no_qualifying_slot_chooses_nothing_and_names_every_slot_with_its_skip_kind() -> None:
    pool = _pool()

    selection = pool.select_pool_slot(
        readings=(
            ("CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_2", _reading(identity="id2", utilization=85)),
            ("CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_3", _reading(identity="id3", utilization=None)),
            (
                "CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_4",
                dataclasses.replace(
                    _reading(identity="id4", utilization=40),
                    projection=headroom.SessionHeadroomProjection(
                        result=headroom.PROJECTED_RESULT, skip_applied=True
                    ),
                ),
            ),
        ),
        floor_percent=_FLOOR,
    )

    slots = _by_slot(selection=selection)
    assert selection.chosen_slot is None
    kinds = {name: reading.slot.skip_kind for name, reading in slots.items() if reading.slot}
    assert kinds == {
        "CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_2": "floor",
        "CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_3": "floor",
        "CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_4": "projection",
    }
    assert all(reading.slot and not reading.slot.chosen for reading in slots.values())
    assert selection.representative.credential_identity == "id4"
