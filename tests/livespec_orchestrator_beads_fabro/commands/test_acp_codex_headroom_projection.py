"""Projecting each Codex window's exhaustion, per credential AND per window length.

Binds the projection half of "Admission filters Codex candidates by projected
usage-window headroom" in `SPECIFICATION/contracts.md` and Scenario 243: the
projection is attempted only for a valid reading that passes the floor and is
allowed; every other reading carries an explicit `not-projected` result with a
closed reason; `not-projected` stays distinct from `unavailable`; and a baseline
of one window length is never used for another.
"""

from __future__ import annotations

from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import _acp_codex_headroom as codex
from livespec_orchestrator_beads_fabro.commands import _acp_codex_headroom_projection as projection
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom_drain import (
    SessionHeadroomBaseline,
)

_NOW = "2026-10-28T06:00:00Z"
_FIVE_HOURS = 18000
_WEEK = 604800


def _baseline(*, used: float, hours: float = 1.0) -> SessionHeadroomBaseline:
    return SessionHeadroomBaseline(
        utilization_percent=used, observed_at="2026-10-28T05:00:00Z", elapsed_hours=hours
    )


def _reading(
    *, primary: float | None = 40.0, secondary: float | None = None, **limits: object
) -> codex.CodexHeadroomReading:
    window = lambda used, seconds: {"used_percent": used, "limit_window_seconds": seconds}  # noqa: E731
    response: dict[str, Any] = {
        "rate_limit": {
            "allowed": True,
            "limit_reached": False,
            "primary_window": None if primary is None else window(primary, _FIVE_HOURS),
            "secondary_window": None if secondary is None else window(secondary, _WEEK),
            **limits,
        }
    }
    return codex.codex_headroom_reading(
        credential_identity="cred", observed_at=_NOW, response=response
    )


def _assessed(
    reading: codex.CodexHeadroomReading,
    *,
    baselines: dict[int, SessionHeadroomBaseline] | None = None,
    floor: int = 20,
    horizon: int = 180,
) -> codex.CodexHeadroomReading:
    return projection.assessed_codex_reading(
        reading=reading,
        baselines={} if baselines is None else baselines,
        floor_percent=floor,
        horizon_minutes=horizon,
    )


def _only(reading: codex.CodexHeadroomReading) -> codex.CodexWindowProjection:
    window_projection = reading.windows[0].projection
    assert window_projection is not None
    return window_projection


def test_a_drain_that_exhausts_inside_the_horizon_projects_a_skip() -> None:
    assessed = _assessed(_reading(primary=60.0), baselines={_FIVE_HOURS: _baseline(used=30.0)})

    result = _only(assessed)
    assert result.result == projection.PROJECTED
    assert result.drain_percent_per_hour == 30.0
    assert result.projected_exhaustion_at == "2026-10-28T07:20:00Z"
    assert result.baseline_observed_at == "2026-10-28T05:00:00Z"
    assert result.horizon_minutes == 180
    assert result.skip_applied is True
    assert assessed.windows[0].drain_percent_per_hour == 30.0


def test_an_exhaustion_exactly_at_the_horizon_is_not_inside_it() -> None:
    assessed = _assessed(_reading(primary=40.0), baselines={_FIVE_HOURS: _baseline(used=20.0)})

    assert _only(assessed).projected_exhaustion_at == "2026-10-28T09:00:00Z"
    assert _only(assessed).skip_applied is False


def test_a_horizon_of_zero_never_applies_a_projection_skip() -> None:
    assessed = _assessed(
        _reading(primary=60.0), baselines={_FIVE_HOURS: _baseline(used=30.0)}, horizon=0
    )

    assert _only(assessed).result == projection.PROJECTED
    assert _only(assessed).skip_applied is False


def test_a_secondary_window_projection_is_carried_on_its_own_window() -> None:
    assessed = _assessed(
        _reading(primary=30.0, secondary=60.0),
        baselines={_FIVE_HOURS: _baseline(used=30.0), _WEEK: _baseline(used=30.0)},
    )

    primary, secondary = assessed.windows
    assert primary.projection is not None
    assert primary.projection.reason == projection.UTILIZATION_NOT_HIGHER_REASON
    assert primary.projection.skip_applied is False
    assert secondary.projection is not None
    assert secondary.projection.skip_applied is True
    assert codex.codex_headroom_skip_kind(reading=assessed, floor_percent=20) == "projection"


def test_a_baseline_of_another_window_length_is_never_used() -> None:
    assessed = _assessed(_reading(primary=60.0), baselines={_WEEK: _baseline(used=30.0)})

    result = _only(assessed)
    assert result.result == projection.UNAVAILABLE
    assert result.reason == projection.NO_BASELINE_REASON
    assert result.baseline_observed_at is None
    assert result.skip_applied is False
    assert assessed.windows[0].drain_percent_per_hour is None


def test_a_baseline_that_did_not_rise_leaves_the_projection_unavailable() -> None:
    assessed = _assessed(_reading(primary=30.0), baselines={_FIVE_HOURS: _baseline(used=30.0)})

    result = _only(assessed)
    assert result.result == projection.UNAVAILABLE
    assert result.reason == projection.UTILIZATION_NOT_HIGHER_REASON
    assert result.baseline_observed_at == "2026-10-28T05:00:00Z"


def test_an_unreadable_observation_instant_leaves_the_projection_unavailable() -> None:
    reading = codex.codex_headroom_reading(
        credential_identity="cred",
        observed_at="not an instant",
        response={
            "rate_limit": {
                "allowed": True,
                "limit_reached": False,
                "primary_window": {"used_percent": 60, "limit_window_seconds": _FIVE_HOURS},
            }
        },
    )

    assessed = _assessed(reading, baselines={_FIVE_HOURS: _baseline(used=30.0)})

    assert _only(assessed).reason == projection.UNREADABLE_INSTANT_REASON


@pytest.mark.parametrize(
    ("limits", "floor", "reason"),
    [
        ({}, 0, projection.FLOOR_ZERO_REASON),
        ({"limit_reached": True}, 20, projection.CODEX_LIMIT_REASON),
        ({"allowed": False}, 20, projection.CODEX_LIMIT_REASON),
        ({}, 50, projection.FLOOR_SKIP_REASON),
    ],
)
def test_a_settled_reading_carries_one_not_projected_result_per_window(
    limits: dict[str, object], floor: int, reason: str
) -> None:
    reading = _reading(primary=60.0, secondary=70.0, **limits)

    assessed = _assessed(reading, floor=floor, baselines={_FIVE_HOURS: _baseline(used=30.0)})

    results = [window.projection for window in assessed.windows]
    assert len(results) == 2
    for result in results:
        assert result is not None
        assert result.result == projection.NOT_PROJECTED
        assert result.reason == reason
        assert result.horizon_minutes == 180
        assert result.drain_percent_per_hour is None
    assert assessed.projection is None
    assert projection.codex_projection_attempted(reading=reading, floor_percent=floor) is False


def test_an_unobservable_reading_carries_one_windowless_not_projected_result() -> None:
    reading = codex.unobservable_codex_headroom(
        credential_identity="cred", observed_at=_NOW, reason="timed-out"
    )

    assessed = _assessed(reading)

    assert assessed.projection is not None
    assert assessed.projection.result == projection.NOT_PROJECTED
    assert assessed.projection.reason == projection.UNOBSERVABLE_REASON
    assert assessed.windows == ()


def test_a_floor_of_zero_outranks_the_unobservable_reason() -> None:
    reading = codex.unobservable_codex_headroom(
        credential_identity="cred", observed_at=_NOW, reason="timed-out"
    )

    assessed = _assessed(reading, floor=0)

    assert assessed.projection is not None
    assert assessed.projection.reason == projection.FLOOR_ZERO_REASON


def test_not_projected_and_unavailable_are_distinct_values() -> None:
    assert projection.NOT_PROJECTED != projection.UNAVAILABLE
    assert projection.codex_projection_attempted(reading=_reading(), floor_percent=20) is True
