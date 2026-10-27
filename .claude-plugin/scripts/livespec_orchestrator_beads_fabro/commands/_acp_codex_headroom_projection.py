"""WHICH Codex shortfall stops a candidate, and WHEN each window empties.

`SPECIFICATION/contracts.md` section "Provider spend containment", the
paragraph "Admission filters Codex candidates by projected usage-window
headroom": "With a positive floor, a covered candidate MUST be skipped for this
admission evaluation when: `rate_limit.allowed` is `false` or
`rate_limit.limit_reached` is `true` (a Codex limit skip); or the governing
remaining headroom is strictly below the floor (a floor skip); or the reading is
unobservable (a floor skip on an unobservable reading). Equality passes the
floor. ... MUST additionally be assessed for projected exhaustion per window,
using exactly the baseline, drain-rate, unavailable-projection, and horizon
rules of the Claude clause, applied per opaque credential identity AND per
window length, so a reading of one window is never a baseline for another. The
candidate MUST be skipped by a projection skip when any valid window's projected
exhaustion instant is strictly earlier than the observation time plus the
horizon."

PURE, AND HANDED NO JOURNAL. The baselines arrive as a mapping keyed on window
length; `_dispatcher_codex_headroom_baseline` reads the history. So "A reading
creates NO observed availability record and retires none" holds STRUCTURALLY
rather than carefully: there is no parameter a ledger could arrive through.

THE CLAUDE CLAUSE'S RULES ARE REUSED RATHER THAN RESTATED, which is what the
words "exactly the ... rules of the Claude clause" ask for. The three
`SessionHeadroomProjection` results, the inclusive age window, the
earliest-in-window baseline selection, the strict horizon comparison and the
instant format are all imported. A second account of any of them is how two
clauses written from one paragraph come to disagree about whether an exhaustion
landing exactly ON the horizon is inside it.

THE SKIP KINDS ARE THREE AND THE ORDER BETWEEN THEM IS THE CLAUSE'S OWN. A
provider that has REFUSED the allowance outranks a dial and an extrapolation
alike, so a Codex limit is reported first; the floor is the operator dial that
governs every shortfall, so it comes next; and this build's own projection comes
last, because it is the only one of the three nobody can check against the
account. All three share the single `HEADROOM_SKIP` reason, because the clause
gives each of them "exactly the semantics of a Claude floor skip" -- every
surface downstream keys on that reason, and a second token would leave a
Codex-emptied chain unnamed by all of them.

PER WINDOW, AND NEVER ONCE PER READING. The clause's own worked case is a
healthy primary window beside a secondary window whose drain projects
exhaustion inside the horizon, so a projection taken on the governing window
alone answers correctly only while the governing window happens to be the one
draining. `codex_window_projections` therefore returns one result per window and
`codex_projection_skips_candidate` asks ANY of them.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from livespec_orchestrator_beads_fabro.commands._acp_codex_headroom import (
    CodexUsageReading,
    CodexUsageWindow,
    CodexWindowProjection,
)
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom import (
    NOT_PROJECTED_RESULT,
    PROJECTED_RESULT,
    UNAVAILABLE_RESULT,
    SessionHeadroomProjection,
)
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom_drain import (
    SessionHeadroomBaseline,
    parse_session_headroom_instant,
)
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom_projection import (
    FLOOR_SKIP_KIND,
    NO_BASELINE_REASON,
    PROJECTION_SKIP_KIND,
    UNREADABLE_OBSERVATION_REASON,
    UTILIZATION_NOT_HIGHER_REASON,
    exhausts_inside_horizon,
    render_session_headroom_instant,
    unavailable_projection_reason,
)

__all__: list[str] = [
    "CODEX_LIMIT_REASON",
    "CODEX_LIMIT_SKIP_KIND",
    "FLOOR_SKIP_KIND",
    "FLOOR_SKIP_REASON",
    "FLOOR_ZERO_REASON",
    "NO_BASELINE_REASON",
    "PROJECTION_SKIP_KIND",
    "UNOBSERVABLE_REASON",
    "UNREADABLE_OBSERVATION_REASON",
    "UTILIZATION_NOT_HIGHER_REASON",
    "codex_floor_skips_candidate",
    "codex_headroom_skip_kind",
    "codex_projection_skips_candidate",
    "codex_projections_attempted",
    "codex_window_projections",
    "reading_with_codex_projections",
]

# The THIRD skip kind this clause adds beside the Claude clause's floor and
# projection kinds, which the clause requires the records to distinguish:
# "distinguishing a Codex limit skip, a floor skip, and a projection skip". It
# is a kind rather than a reason because every consumer keys on the shared
# headroom REASON; see the module docstring.
CODEX_LIMIT_SKIP_KIND = "codex-limit"

# The four `not-projected` reasons the clause CLOSES by name. They are spelled
# as the clause spells them rather than borrowed from the Claude clause's own
# three, because the sets are not the same: this clause adds `codex-limit`,
# which has no Claude counterpart, and a reader joining two vocabularies could
# not tell which clause a record came from.
FLOOR_ZERO_REASON = "floor-zero"
FLOOR_SKIP_REASON = "floor-skip"
UNOBSERVABLE_REASON = "unobservable"
CODEX_LIMIT_REASON = "codex-limit"

_FLOOR_DISABLED_PERCENT = 0


def codex_floor_skips_candidate(*, reading: CodexUsageReading, floor_percent: int) -> bool:
    """Whether the FLOOR alone stops this covered candidate.

    TWO boundaries, and an almost-correct implementation inverts either.

    EQUALITY PASSES, which is the clause's own word: a governing remaining
    headroom equal to the floor is admitted.

    A NON-POSITIVE FLOOR DISABLES THIS SKIP, and the UNOBSERVABLE arm is the
    only one that needs the guard -- no remaining headroom is strictly below
    zero, so a predicate written without it passes every numeric case at a floor
    of 0 and still refuses on every unreadable response. An operator who set the
    dial to 0 to switch the brake OFF would then find their dispatches skipped
    whenever the usage endpoint timed out.
    """
    if floor_percent <= _FLOOR_DISABLED_PERCENT:
        return False
    remaining = reading.governing_remaining_percent
    if remaining is None:
        return True
    return remaining < floor_percent


def codex_projection_skips_candidate(*, reading: CodexUsageReading) -> bool:
    """Whether ANY of this reading's window projections refuses the candidate.

    ANY, not the governing window's, because the clause says "any valid
    window's projected exhaustion instant". A reading whose five-hour window is
    ample while its weekly window empties this afternoon is exactly the case the
    per-window rule exists for, and the governing-window reading admits it.

    A reading carrying NO projection skips nothing, which is the honest answer
    for every surface that composes a verdict without a policy.
    """
    return any(entry.projection.skip_applied for entry in reading.projections)


def codex_headroom_skip_kind(*, reading: CodexUsageReading, floor_percent: int) -> str | None:
    """Which Codex shortfall stops this candidate, or `None` for none of them.

    The dial is tested FIRST and disables every kind this clause defines, which
    the clause states in as many words: "a floor of 0 disables every skip this
    clause defines while retaining the bounded read and its journal record". A
    build that tested the provider's own refusal above the dial would refuse a
    limit-reached account for an operator who had switched the brake off.

    Then a provider refusal, then the floor, then this build's projection -- the
    ordering argued in the module docstring.
    """
    if floor_percent <= _FLOOR_DISABLED_PERCENT:
        return None
    if reading.limit_refused:
        return CODEX_LIMIT_SKIP_KIND
    if codex_floor_skips_candidate(reading=reading, floor_percent=floor_percent):
        return FLOOR_SKIP_KIND
    if codex_projection_skips_candidate(reading=reading):
        return PROJECTION_SKIP_KIND
    return None


def codex_projections_attempted(*, reading: CodexUsageReading, floor_percent: int) -> bool:
    """Whether a projection is attempted for this reading AT ALL.

    The clause's own four conditions, stated once: "A projection is attempted
    only for a valid reading that passes the floor and reports
    `rate_limit.allowed` true and `rate_limit.limit_reached` false". It is
    asked by the baseline read as well as by the projection, so the history is
    touched no more often than a projection is taken -- and the two cannot drift
    apart into two accounts of one condition.
    """
    if floor_percent <= _FLOOR_DISABLED_PERCENT:
        return False
    if not reading.observable or reading.limit_refused:
        return False
    return not codex_floor_skips_candidate(reading=reading, floor_percent=floor_percent)


def codex_window_projections(
    *,
    reading: CodexUsageReading,
    baselines: dict[int, SessionHeadroomBaseline],
    floor_percent: int,
    horizon_minutes: int,
) -> tuple[CodexWindowProjection, ...]:
    """EXACTLY ONE projection result per window, whichever kind each one is.

    `baselines` is keyed on `limit_window_seconds`, which is what makes "a
    reading of one window is never a baseline for another" a property of the
    lookup rather than a test the caller remembers: a window whose length the
    mapping does not carry finds nothing and reports an unavailable projection
    naming the absent baseline.

    A reading with NO valid window carries ONE result rather than none, which is
    the clause's "or once, when no window is valid". An empty tuple would read
    downstream as a reading nobody projected, which is what a record from a build
    predating this clause looks like.
    """
    if not codex_projections_attempted(reading=reading, floor_percent=floor_percent):
        settled = SessionHeadroomProjection(
            result=NOT_PROJECTED_RESULT,
            reason=_not_attempted_reason(reading=reading, floor_percent=floor_percent),
            horizon_minutes=horizon_minutes,
        )
        if not reading.windows:
            return (CodexWindowProjection(projection=settled),)
        return tuple(
            CodexWindowProjection(
                limit_window_seconds=window.limit_window_seconds, projection=settled
            )
            for window in reading.windows
        )
    return tuple(
        CodexWindowProjection(
            limit_window_seconds=window.limit_window_seconds,
            projection=_window_projection(
                reading=reading,
                window=window,
                baseline=baselines.get(window.limit_window_seconds),
                horizon_minutes=horizon_minutes,
            ),
        )
        for window in reading.windows
    )


def reading_with_codex_projections(
    *, reading: CodexUsageReading, projections: tuple[CodexWindowProjection, ...]
) -> CodexUsageReading:
    """This reading, carrying the per-window projections taken from it.

    A separate function rather than a constructor argument, for the reason the
    Claude reading attaches its own: the projection needs a journal history the
    reading's own grader has no business reading, so a reading carries none
    until an evaluation holding that history attaches them.
    """
    return CodexUsageReading(
        credential_identity=reading.credential_identity,
        observed_at=reading.observed_at,
        allowed=reading.allowed,
        limit_reached=reading.limit_reached,
        windows=reading.windows,
        unobservable=reading.unobservable,
        projections=projections,
        provider_reset_claim=reading.provider_reset_claim,
    )


def _not_attempted_reason(*, reading: CodexUsageReading, floor_percent: int) -> str:
    """Which of the clause's four not-attempted conditions applied.

    The DIAL is tested first because it outranks every reading: with the floor
    at 0 nothing is skipped at all, so reporting a floor skip or a Codex limit
    there would name a skip that did not happen. The provider's own refusal then
    outranks the floor and the unreadable response alike, because an account the
    provider has refused is refused whatever its windows report.
    """
    if floor_percent <= _FLOOR_DISABLED_PERCENT:
        return FLOOR_ZERO_REASON
    if reading.limit_refused:
        return CODEX_LIMIT_REASON
    if not reading.observable:
        return UNOBSERVABLE_REASON
    return FLOOR_SKIP_REASON


def _window_projection(
    *,
    reading: CodexUsageReading,
    window: CodexUsageWindow,
    baseline: SessionHeadroomBaseline | None,
    horizon_minutes: int,
) -> SessionHeadroomProjection:
    """One window's projection, or the reason its inputs could not support one.

    EVERY UNMEASURABLE INPUT IS TESTED IN ONE CONDITION, because they are
    indistinguishable at the record and a reader must not have to guess which
    applied -- the shared reason ladder names it instead. That guard is also what
    makes the measured branch total: past it the baseline, the rate, the
    remaining headroom and the instant are all in hand.
    """
    observed = parse_session_headroom_instant(text=reading.observed_at)
    rate = None if baseline is None else _drain_rate(window=window, baseline=baseline)
    if baseline is None or rate is None or observed is None:
        return SessionHeadroomProjection(
            result=UNAVAILABLE_RESULT,
            reason=unavailable_projection_reason(
                baseline_present=baseline is not None, observed=observed
            ),
            five_hour_drain_percent_per_hour=rate,
            baseline_observed_at=None if baseline is None else baseline.observed_at,
            horizon_minutes=horizon_minutes,
        )
    exhaustion = observed + timedelta(hours=window.remaining_percent / rate)
    return SessionHeadroomProjection(
        result=PROJECTED_RESULT,
        five_hour_drain_percent_per_hour=rate,
        baseline_observed_at=baseline.observed_at,
        projected_exhaustion_at=render_session_headroom_instant(instant=exhaustion),
        horizon_minutes=horizon_minutes,
        skip_applied=_inside_horizon(
            observed=observed, exhaustion=exhaustion, horizon_minutes=horizon_minutes
        ),
    )


def _drain_rate(*, window: CodexUsageWindow, baseline: SessionHeadroomBaseline) -> float | None:
    """This window's drain in percentage points per hour, when it rose at all.

    "NOT HIGHER" INCLUDES EQUALITY, which is the Claude clause's own wording
    applied here unchanged. An unmoved window has nothing to divide, and
    reporting 0.0 would claim a MEASURED rate of zero -- which is exactly what
    an unspent credential genuinely reads as, so the two would be
    indistinguishable at the record.

    A DECREASE is null rather than negative, and it is a REAL state rather than
    a defensive one: a usage window ROLLS, so an earlier spend ageing out of it
    lowers `used_percent` between two readings taken 40 minutes apart. A
    negative rate would report a credential REFILLING at a measured pace.
    """
    if window.used_percent <= baseline.utilization_percent:
        return None
    return (window.used_percent - baseline.utilization_percent) / baseline.elapsed_hours


def _inside_horizon(*, observed: datetime, exhaustion: datetime, horizon_minutes: int) -> bool:
    """The Claude clause's own strict horizon comparison, reused verbatim.

    A thin pass-through rather than an inlined call, so this module's one
    comparison has a name a reader can find -- and so the strictness boundary
    the clause states twice lives in exactly one place for both clauses.
    """
    return exhausts_inside_horizon(
        observed=observed, exhaustion=exhaustion, horizon_minutes=horizon_minutes
    )
