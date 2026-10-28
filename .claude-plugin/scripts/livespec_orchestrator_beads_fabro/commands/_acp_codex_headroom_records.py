"""What a Codex headroom assessment and skip look like in the journal and records.

`SPECIFICATION/contracts.md` paragraph "Admission filters Codex candidates by
projected usage-window headroom": "The per-node selection record and any
headroom-governed refusal record MUST name each skip by its kind, distinguishing a
Codex limit skip, a floor skip, and a projection skip, and MUST name the provider
as `codex`." And, for the journal, the opaque non-secret credential identity,
`rate_limit.allowed` and `rate_limit.limit_reached`, each window's `used_percent`,
`limit_window_seconds` and remaining headroom, or an explicit unobservable
result, the observation time, and exactly one projection result per window. The
journal MUST NOT contain credential values, the account email or raw provider
responses.

PURE, AND THE ONE PLACE THESE KEYS ARE NAMED. The selection record, the refusal
record and the per-work-item journal row all render a reading through
`codex_headroom_reading_fields`, so a second spelling of a key cannot make one
surface report `remaining_percent` while another reports `remaining`.

EVERY KEY IS WRITTEN ON EVERY READING, NULLS INCLUDED. An omitted key is what a
record from a build predating this clause looks like, so a reader could not tell
"this window carried no projection" from "this record was never asked". A reading
with no valid window renders an empty `windows` list and carries its single
windowless projection result at the top level; a reading with windows renders one
result per window.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._acp_codex_headroom import (
    CODEX_PROJECTION_SKIP_KIND,
    CODEX_PROVIDER,
    CodexHeadroomReading,
    CodexWindowProjection,
    CodexWindowReading,
)
from livespec_orchestrator_beads_fabro.commands._acp_preflight_skips import SkippedCandidate

__all__: list[str] = [
    "codex_headroom_projection_fields",
    "codex_headroom_reading_fields",
    "codex_headroom_skip_fields",
]


def codex_headroom_skip_fields(
    *, skip: SkippedCandidate, reading: CodexHeadroomReading
) -> dict[str, object]:
    """One Codex-skipped candidate: who it was, the provider, the kind and the reading.

    THE PROVIDER IS WRITTEN AS A KEY OF ITS OWN, and a projection skip names the
    window whose projection stopped the candidate: with two windows of different
    lengths, the kind alone cannot say which one fired.
    """
    return {
        "availability_key": skip.availability_key,
        "candidate_key": skip.candidate_key,
        "headroom_provider": CODEX_PROVIDER,
        "session_headroom_floor_percent": skip.headroom_floor_percent,
        "session_headroom_horizon_minutes": skip.headroom_horizon_minutes,
        "headroom_skip_kind": skip.headroom_skip_kind,
        "projection_window_seconds": (
            _projecting_window_seconds(reading=reading)
            if skip.headroom_skip_kind == CODEX_PROJECTION_SKIP_KIND
            else None
        ),
        "codex_headroom": codex_headroom_reading_fields(reading=reading),
    }


def codex_headroom_reading_fields(*, reading: CodexHeadroomReading) -> dict[str, object]:
    """One reading's journaled facts, with nulls written rather than omitted."""
    return {
        "credential_identity": reading.credential_identity,
        "observed_at": reading.observed_at,
        "allowed": reading.allowed,
        "limit_reached": reading.limit_reached,
        "unobservable": reading.unobservable,
        "windows": [_window_fields(window=window) for window in reading.windows],
        "projection": codex_headroom_projection_fields(projection=reading.projection),
    }


def codex_headroom_projection_fields(
    *, projection: CodexWindowProjection | None
) -> dict[str, object] | None:
    """The ONE projection result a window or reading carries, or an explicit null.

    EXACTLY ONE RESULT UNDER ONE KEY, with the kind a field inside it, so a record
    cannot carry two parallel results a reader would join on the wrong one of. A
    `None` is a different claim from every result: it says nothing was projected
    at all, which is what a record from a build predating this clause looks like.
    """
    if projection is None:
        return None
    return {
        "result": projection.result,
        "reason": projection.reason,
        "drain_percent_per_hour": projection.drain_percent_per_hour,
        "baseline_observed_at": projection.baseline_observed_at,
        "projected_exhaustion_at": projection.projected_exhaustion_at,
        "session_headroom_horizon_minutes": projection.horizon_minutes,
        "projection_skip_applied": projection.skip_applied,
    }


def _window_fields(*, window: CodexWindowReading) -> dict[str, object]:
    return {
        "name": window.name,
        "used_percent": window.used_percent,
        "limit_window_seconds": window.limit_window_seconds,
        "remaining_percent": window.remaining_percent,
        "drain_percent_per_hour": window.drain_percent_per_hour,
        "projection": codex_headroom_projection_fields(projection=window.projection),
    }


def _projecting_window_seconds(*, reading: CodexHeadroomReading) -> int | None:
    for window in reading.windows:
        if window.projection is not None and window.projection.skip_applied:
            return window.limit_window_seconds
    return None
