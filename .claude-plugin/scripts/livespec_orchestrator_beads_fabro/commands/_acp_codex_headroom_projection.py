"""Projecting each Codex usage window's exhaustion from a journaled baseline.

`SPECIFICATION/contracts.md` paragraph "Admission filters Codex candidates by
projected usage-window headroom": a passing reading is projected per window,
"using exactly the baseline, drain-rate, unavailable-projection, and horizon
rules of the Claude clause, applied per opaque credential identity AND per
window length, so a reading of one window is never a baseline for another."

THE BASELINES ARRIVE AS A MAPPING KEYED ON WINDOW LENGTH, already read from the
journal for this credential, which is what keeps one window's history from
serving another. A window with no entry has no baseline for ITS length, however
many baselines other lengths hold.

A PROJECTION IS ATTEMPTED ONLY FOR A VALID READING THAT PASSES THE FLOOR AND
REPORTS THE ACCOUNT ALLOWED. Every other reading carries an explicit
`not-projected` result -- once per window, or once for the reading when no
window is valid -- whose reason names what settled it. `not-projected` is never
`unavailable`: the first says nobody tried, the second says the history could
not support an answer.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime, timedelta

from livespec_orchestrator_beads_fabro.commands._acp_codex_headroom import (
    CodexHeadroomReading,
    CodexWindowProjection,
    CodexWindowReading,
)
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom_drain import (
    SessionHeadroomBaseline,
    parse_session_headroom_instant,
)

__all__: list[str] = [
    "CODEX_LIMIT_REASON",
    "FLOOR_SKIP_REASON",
    "FLOOR_ZERO_REASON",
    "NOT_PROJECTED",
    "NO_BASELINE_REASON",
    "PROJECTED",
    "UNAVAILABLE",
    "UNOBSERVABLE_REASON",
    "UNREADABLE_INSTANT_REASON",
    "UTILIZATION_NOT_HIGHER_REASON",
    "assessed_codex_reading",
    "codex_projection_attempted",
]

PROJECTED = "projected"
UNAVAILABLE = "unavailable"
NOT_PROJECTED = "not-projected"

FLOOR_ZERO_REASON = "floor-zero"
FLOOR_SKIP_REASON = "floor-skip"
UNOBSERVABLE_REASON = "unobservable"
CODEX_LIMIT_REASON = "codex-limit"

NO_BASELINE_REASON = "no-baseline"
UTILIZATION_NOT_HIGHER_REASON = "utilization-not-higher"
UNREADABLE_INSTANT_REASON = "unreadable-observation-instant"

_INSTANT_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def codex_projection_attempted(*, reading: CodexHeadroomReading, floor_percent: int) -> bool:
    """Whether this reading is projected at all."""
    return _settled_reason(reading=reading, floor_percent=floor_percent) is None


def assessed_codex_reading(
    *,
    reading: CodexHeadroomReading,
    baselines: Mapping[int, SessionHeadroomBaseline],
    floor_percent: int,
    horizon_minutes: int,
) -> CodexHeadroomReading:
    """This reading carrying its drain rates and its projection results.

    THE RESULT IS ALWAYS ATTACHED, including on the arms that compute no rate:
    `not-projected` is a result, and the clause requires one per assessed window.
    """
    reason = _settled_reason(reading=reading, floor_percent=floor_percent)
    if not reading.observable:
        return replace(reading, projection=_not_projected(reason=reason, horizon=horizon_minutes))
    if reason is not None:
        settled = _not_projected(reason=reason, horizon=horizon_minutes)
        return replace(
            reading,
            windows=tuple(replace(window, projection=settled) for window in reading.windows),
        )
    windows = tuple(
        _projected_window(
            window=window,
            observed_at=reading.observed_at,
            baseline=baselines.get(window.limit_window_seconds),
            horizon=horizon_minutes,
        )
        for window in reading.windows
    )
    return replace(reading, windows=windows)


def _settled_reason(*, reading: CodexHeadroomReading, floor_percent: int) -> str | None:
    if floor_percent <= 0:
        return FLOOR_ZERO_REASON
    if not reading.observable:
        return UNOBSERVABLE_REASON
    if reading.limit_governs:
        return CODEX_LIMIT_REASON
    remaining = reading.governing_remaining_percent
    if remaining is not None and remaining < floor_percent:
        return FLOOR_SKIP_REASON
    return None


def _not_projected(*, reason: str | None, horizon: int) -> CodexWindowProjection:
    return CodexWindowProjection(result=NOT_PROJECTED, reason=reason, horizon_minutes=horizon)


def _projected_window(
    *,
    window: CodexWindowReading,
    observed_at: str,
    baseline: SessionHeadroomBaseline | None,
    horizon: int,
) -> CodexWindowReading:
    observed = parse_session_headroom_instant(text=observed_at)
    rate = _drain_rate(window=window, baseline=baseline)
    if baseline is None or rate is None or observed is None:
        unavailable = CodexWindowProjection(
            result=UNAVAILABLE,
            reason=_unavailable_reason(baseline=baseline, observed=observed),
            drain_percent_per_hour=rate,
            baseline_observed_at=None if baseline is None else baseline.observed_at,
            horizon_minutes=horizon,
        )
        return replace(window, drain_percent_per_hour=rate, projection=unavailable)
    exhaustion = observed + timedelta(hours=window.remaining_percent / rate)
    projected = CodexWindowProjection(
        result=PROJECTED,
        drain_percent_per_hour=rate,
        baseline_observed_at=baseline.observed_at,
        projected_exhaustion_at=exhaustion.strftime(_INSTANT_FORMAT),
        horizon_minutes=horizon,
        skip_applied=_exhausts_inside_horizon(
            observed=observed, exhaustion=exhaustion, horizon=horizon
        ),
    )
    return replace(window, drain_percent_per_hour=rate, projection=projected)


def _drain_rate(
    *, window: CodexWindowReading, baseline: SessionHeadroomBaseline | None
) -> float | None:
    if baseline is None or window.used_percent <= baseline.utilization_percent:
        return None
    return (window.used_percent - baseline.utilization_percent) / baseline.elapsed_hours


def _exhausts_inside_horizon(*, observed: datetime, exhaustion: datetime, horizon: int) -> bool:
    if horizon <= 0:
        return False
    return exhaustion < observed + timedelta(minutes=horizon)


def _unavailable_reason(
    *, baseline: SessionHeadroomBaseline | None, observed: datetime | None
) -> str:
    if observed is None:
        return UNREADABLE_INSTANT_REASON
    if baseline is None:
        return NO_BASELINE_REASON
    return UTILIZATION_NOT_HIGHER_REASON
