"""What a Codex usage-window assessment looks like in the dispatch journal.

`SPECIFICATION/contracts.md` section "Provider spend containment", the
paragraph "Admission filters Codex candidates by projected usage-window
headroom": "For each affected work-item and assessed Codex credential, the
Dispatcher MUST journal under section "Control surface and audit" the opaque
non-secret credential identity, `rate_limit.allowed` and
`rate_limit.limit_reached`, each window's `used_percent`,
`limit_window_seconds` and remaining headroom, or an explicit unobservable
result, the local observation time, and exactly one projection result per
window in the Claude clause's form. ... The journal MUST NOT contain credential
values, the account email, or raw provider responses."

PURE, AND THE ONE PLACE THESE KEYS ARE NAMED. The reading projection is shared
by the per-item assessment record, by the per-node selection record and by the
headroom-governed refusal record, so a second spelling of these keys is how one
surface comes to report `used_percent` while another reports `used` and no
reader can join them.

EVERY KEY IS WRITTEN ON EVERY READING, NULLS INCLUDED, for the reason its
Claude sibling gives: an omitted key is what a record from a build predating
this clause looks like, so a reader could not tell "this reading was
unobservable" from "this record was never asked". That is why `allowed` and
`limit_reached` are written as explicit nulls on an unobservable reading rather
than being dropped -- neither `false` nor `true` is available as a sentinel,
because both are perfectly good provider answers.

THE WINDOWS ARE A LIST AND THE PROJECTIONS ARE A SECOND LIST, JOINED BY
`limit_window_seconds`. The clause asks for "exactly one projection result per
window", and the per-window key is what lets a reader pair them -- which is the
same key the baseline rule is scoped by, so a reader grading one window's
projection reads the same identity the projection was taken against. A
projection carrying a NULL key is the clause's "or once, when no window is
valid", which is the only shape a reading with no window can carry.

THE DRAIN RATE IS RENDERED UNDER A PROVIDER-NEUTRAL KEY. The shared projection
VALUE spells its rate field for the Claude clause's five-hour window, because
that is the only window that clause has; a Codex window may span five hours, a
week, or whatever the provider reports. Rendering it as `five_hour_...` here
would name a window this record's own sibling key contradicts, so the record
reads `drain_percent_per_hour` beside the `limit_window_seconds` that says which
window the rate is about.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._acp_codex_headroom import (
    CodexUsageReading,
    CodexUsageWindow,
    CodexWindowProjection,
)

__all__: list[str] = [
    "CODEX_ASSESSMENTS_KEY",
    "codex_usage_reading_fields",
    "codex_window_fields",
    "codex_window_projection_fields",
]

# The key the per-item assessment record carries this clause's readings under,
# BESIDE the Claude clause's own `assessments`. One record per work-item per
# evaluation carries both, which is what lets a reader see every provider this
# evaluation assessed at one instant without a join -- and what keeps the two
# baseline reads, each of which must see only its own provider's history, from
# having to tell two record stages apart.
CODEX_ASSESSMENTS_KEY = "codex_assessments"


def codex_usage_reading_fields(*, reading: CodexUsageReading) -> dict[str, object]:
    """One Codex reading's journaled facts, with nulls written rather than omitted.

    `unverified_provider_reset_claim` is the ONE field the provider itself
    asserted rather than the one this build measured, and its name says so. The
    clause permits journaling "a reset instant the response carries" as "an
    unverified provider claim" and forbids it from changing any skip; nothing
    reads it, and a key spelled `resets_at` would sit beside measured drain
    rates with nothing to tell a reader which of them anybody checked.
    """
    return {
        "credential_identity": reading.credential_identity,
        "observed_at": reading.observed_at,
        "allowed": reading.allowed,
        "limit_reached": reading.limit_reached,
        "unobservable": reading.unobservable,
        "governing_remaining_percent": reading.governing_remaining_percent,
        "windows": [codex_window_fields(window=window) for window in reading.windows],
        "projections": [
            codex_window_projection_fields(entry=entry) for entry in reading.projections
        ],
        "unverified_provider_reset_claim": reading.provider_reset_claim,
    }


def codex_window_fields(*, window: CodexUsageWindow) -> dict[str, object]:
    """One window's three journaled facts, as the clause enumerates them.

    The REMAINING headroom is written beside the `used_percent` it is derived
    from, even though either determines the other. An operator reading a
    refusal is comparing against a floor measured in REMAINING points, and a
    record carrying only the spend makes that the reader's arithmetic -- which
    is the one arithmetic a record exists to have already done.
    """
    return {
        "used_percent": window.used_percent,
        "limit_window_seconds": window.limit_window_seconds,
        "remaining_percent": window.remaining_percent,
    }


def codex_window_projection_fields(*, entry: CodexWindowProjection) -> dict[str, object]:
    """ONE window's projection result, under ONE key set, naming its window.

    EXACTLY ONE RESULT, with the result KIND as a field inside it, which is the
    Claude clause's own requirement applied per window: three parallel optional
    blocks would let one window carry two results, and a reader joining on
    whichever it found first would report the wrong one with no way to notice.
    The figures that do not apply to a given kind are written as nulls beside
    it.
    """
    projection = entry.projection
    return {
        "limit_window_seconds": entry.limit_window_seconds,
        "result": projection.result,
        "reason": projection.reason,
        "drain_percent_per_hour": projection.five_hour_drain_percent_per_hour,
        "baseline_observed_at": projection.baseline_observed_at,
        "projected_exhaustion_at": projection.projected_exhaustion_at,
        "session_headroom_horizon_minutes": projection.horizon_minutes,
        "projection_skip_applied": projection.skip_applied,
    }
