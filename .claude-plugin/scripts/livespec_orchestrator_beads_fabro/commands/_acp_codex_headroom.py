"""ONE projected Codex credential's usage-window headroom, as a value.

`SPECIFICATION/contracts.md` paragraph "Admission filters Codex candidates by
projected usage-window headroom": the usage response carries
`rate_limit.allowed`, `rate_limit.limit_reached` and up to two windows, each
with a `used_percent` and a `limit_window_seconds`. A window's remaining
headroom is 100 minus its `used_percent`, and the governing headroom of a
reading is the smallest remaining headroom among its windows.

NOTHING HERE READS A CREDENTIAL, A FILE OR A NETWORK. The response arrives as a
decoded value, which is what lets every state the clause distinguishes be graded
without a provider.

VALIDITY IS DECIDED FOR THE WHOLE READING, never window by window. A reading
carrying one valid window beside a malformed one is unobservable, because
admitting it on its valid part would let a broken response look like headroom.
An unobservable reading is its own field and never a number: every numeric
sentinel is also a plausible genuine reading.

THIS MODULE DOES NOT IMPORT THE CLAUDE HEADROOM MODULE, and the direction is
load-bearing: the Claude admission policy carries the Codex read seam, so the
Codex values must be importable from it without a cycle. The few tokens both
providers spell the same way are therefore restated here.

COVERAGE FOLLOWS RESOLVED PROVENANCE: a candidate is covered only when it
resolved through the `codex-acp` agent entry, never by display text, a model
prefix, or a spelling inferred from an opaque key.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import cast

from livespec_orchestrator_beads_fabro.commands._acp_agent_catalog import CODEX_AGENT_ID
from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidate

__all__: list[str] = [
    "CODEX_FLOOR_SKIP_KIND",
    "CODEX_HEADROOM_STAGE",
    "CODEX_LIMIT_SKIP_KIND",
    "CODEX_PROJECTION_SKIP_KIND",
    "CODEX_PROVIDER",
    "UNREADABLE_CODEX_RESPONSE",
    "CodexHeadroomReading",
    "CodexWindowProjection",
    "CodexWindowReading",
    "codex_headroom_covers_candidate",
    "codex_headroom_reading",
    "codex_headroom_skip_kind",
    "unobservable_codex_headroom",
]

CODEX_PROVIDER = "codex"

# The journal stage Codex assessments are recorded under, beside and distinct
# from the Claude stage: the baseline reader of one provider must never read the
# other's rows.
CODEX_HEADROOM_STAGE = "acp-codex-session-headroom"

# The three skip kinds the clause distinguishes. The floor and projection
# spellings equal the Claude kinds on purpose, so one reader names both.
CODEX_LIMIT_SKIP_KIND = "codex-limit"
CODEX_FLOOR_SKIP_KIND = "floor"
CODEX_PROJECTION_SKIP_KIND = "projection"

# The one unobservable reason this module can reach: a decoded response that is
# not a valid whole reading. Transport reasons belong to whoever issued the read.
UNREADABLE_CODEX_RESPONSE = "unreadable-response"

_FULL_ALLOWANCE_PERCENT = 100.0
_WINDOW_NAMES = (("primary", "primary_window"), ("secondary", "secondary_window"))


@dataclass(frozen=True, kw_only=True)
class CodexWindowProjection:
    """What one window's projected exhaustion came to, as one closed result.

    The result kind is a field, not an absence, so `not-projected` (nobody
    attempted it) stays distinct from `unavailable` (attempted, no usable
    baseline). `skip_applied` is decided where the horizon is in hand.
    """

    result: str
    reason: str | None = None
    drain_percent_per_hour: float | None = None
    baseline_observed_at: str | None = None
    projected_exhaustion_at: str | None = None
    horizon_minutes: int | None = None
    skip_applied: bool = False


@dataclass(frozen=True, kw_only=True)
class CodexWindowReading:
    """One valid usage window of one reading, with its own projection result."""

    name: str
    used_percent: float
    limit_window_seconds: int
    remaining_percent: float
    drain_percent_per_hour: float | None = None
    projection: CodexWindowProjection | None = None


@dataclass(frozen=True, kw_only=True)
class CodexHeadroomReading:
    """One assessment of one projected Codex credential at one observation time.

    Every field is an opaque identity, a percentage, an instant or a closed
    result; no field can carry a credential value, the account email or a raw
    provider response. `projection` is the single windowless result an
    unobservable reading carries.
    """

    credential_identity: str
    observed_at: str
    allowed: bool | None = None
    limit_reached: bool | None = None
    windows: tuple[CodexWindowReading, ...] = ()
    unobservable: str | None = None
    projection: CodexWindowProjection | None = None

    @property
    def observable(self) -> bool:
        """Whether this reading is a valid whole reading."""
        return self.unobservable is None

    @property
    def limit_governs(self) -> bool:
        """Whether the provider itself reports the account refused."""
        return self.allowed is False or self.limit_reached is True

    @property
    def governing_remaining_percent(self) -> float | None:
        """The smallest remaining headroom among the windows, or `None`."""
        if not self.windows:
            return None
        return min(window.remaining_percent for window in self.windows)


def unobservable_codex_headroom(
    *, credential_identity: str, observed_at: str, reason: str
) -> CodexHeadroomReading:
    """The explicit unobservable result, naming the measurement that failed."""
    return CodexHeadroomReading(
        credential_identity=credential_identity, observed_at=observed_at, unobservable=reason
    )


def codex_headroom_reading(
    *, credential_identity: str, observed_at: str, response: object
) -> CodexHeadroomReading:
    """Grade one decoded usage response into a reading, or an unobservable.

    `response` is typed `object` because it arrives from a decoded provider
    document, so every validity rule is a question about a value of unknown
    shape. Anything short of a valid whole reading is unobservable.
    """
    unreadable = unobservable_codex_headroom(
        credential_identity=credential_identity,
        observed_at=observed_at,
        reason=UNREADABLE_CODEX_RESPONSE,
    )
    limits = _mapping(value=_mapping(value=response).get("rate_limit"))
    allowed = limits.get("allowed")
    limit_reached = limits.get("limit_reached")
    if not isinstance(allowed, bool) or not isinstance(limit_reached, bool):
        return unreadable
    windows: list[CodexWindowReading] = []
    for name, key in _WINDOW_NAMES:
        raw = limits.get(key)
        if raw is None:
            continue
        window = _window(name=name, raw=raw)
        if window is None:
            return unreadable
        windows.append(window)
    if not windows:
        return unreadable
    return CodexHeadroomReading(
        credential_identity=credential_identity,
        observed_at=observed_at,
        allowed=allowed,
        limit_reached=limit_reached,
        windows=tuple(windows),
    )


def codex_headroom_covers_candidate(*, candidate: AcpCandidate) -> bool:
    """Whether the Codex clause assesses this candidate at all."""
    return candidate.agent_id == CODEX_AGENT_ID


def codex_headroom_skip_kind(*, reading: CodexHeadroomReading, floor_percent: int) -> str | None:
    """Which skip, if any, stops this covered candidate for this evaluation.

    A NON-POSITIVE FLOOR DISABLES EVERY SKIP while the reading is still taken
    and journaled, and the unobservable arm is the one that needs the guard.
    EQUALITY PASSES the floor. A credit balance is not headroom: only
    `rate_limit` fields are ever read, so credits cannot prevent a skip.
    """
    if floor_percent <= 0:
        return None
    if not reading.observable:
        return CODEX_FLOOR_SKIP_KIND
    if reading.limit_governs:
        return CODEX_LIMIT_SKIP_KIND
    remaining = reading.governing_remaining_percent
    if remaining is not None and remaining < floor_percent:
        return CODEX_FLOOR_SKIP_KIND
    if any(
        window.projection is not None and window.projection.skip_applied
        for window in reading.windows
    ):
        return CODEX_PROJECTION_SKIP_KIND
    return None


def _mapping(*, value: object) -> dict[object, object]:
    if not isinstance(value, dict):
        return {}
    return cast("dict[object, object]", value)


def _window(*, name: str, raw: object) -> CodexWindowReading | None:
    fields = _mapping(value=raw)
    used = fields.get("used_percent")
    seconds = fields.get("limit_window_seconds")
    if isinstance(used, bool) or not isinstance(used, int | float):
        return None
    percent = float(used)
    if not math.isfinite(percent) or percent < 0.0 or percent > _FULL_ALLOWANCE_PERCENT:
        return None
    if isinstance(seconds, bool) or not isinstance(seconds, int) or seconds <= 0:
        return None
    return CodexWindowReading(
        name=name,
        used_percent=percent,
        limit_window_seconds=seconds,
        remaining_percent=_FULL_ALLOWANCE_PERCENT - percent,
    )
