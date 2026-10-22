"""WHEN one credential's five-hour window is projected to empty, as a decision.

`SPECIFICATION/contracts.md` section "Dispatcher admission, WIP cap, and
post-merge acceptance", the paragraph "Admission filters candidates by
projected Claude session headroom": "When the projection is available, the
projected exhaustion instant is the observation time plus the remaining
headroom divided by the rate, in hours. ... The candidate MUST be skipped for
this admission evaluation when its projected exhaustion instant is strictly
earlier than the observation time plus the horizon. ... For each assessed
credential, the journal record MUST additionally carry exactly one projection
result: the drain rate, the baseline's observation time, the projected
exhaustion instant, the governing horizon, and whether a projection skip
applied; or an explicit `unavailable` result with its reason; or an explicit
`not-projected` result when no projection was attempted because the floor is 0,
the reading was skipped by the floor, or the reading was unobservable."

WHY A HORIZON AT ALL, GIVEN THE RATE IS ALREADY JOURNALED. The rate is a FIGURE
an operator reads afterwards; the horizon is what makes it decide something
before a claim. A dispatch keeps its dispatch-time credential to the end of the
run, so a credential with 40 points remaining and a 30-point-per-hour drain
passes any sane floor and is spent eighty minutes later -- mid-implement, where
the only remedy left is a provider-limit failure and a re-dispatch.

PURE, AND HANDED NO JOURNAL. `_dispatcher_session_headroom_baseline` reads the
history and `_acp_session_headroom_drain` turns it into a rate; this module
decides what that rate implies. So "A projection creates NO observed
availability record and retires none" holds STRUCTURALLY rather than carefully:
there is no parameter a ledger could arrive through, and nothing imported here
could write one.

THE THREE RESULTS ARE NOT INTERCHANGEABLE AND EACH IS EARNED ON ITS OWN ARM.
`not-projected` is returned where no projection was ATTEMPTED, and the three
conditions for that are the clause's own -- a floor of 0, a reading the floor
skipped, an unobservable reading -- all of which `drain_rate_attempted` already
answers, so asking it is what keeps this from becoming a second account of the
filter. `unavailable` is returned where a projection WAS attempted and an input
could not be measured, and it names which one. Collapsing the two would report
an operator's disabled dial and a fresh checkout's missing history as one state.

EVERY UNAVAILABLE ARM FAILS OPEN, which is the clause in as many words: "An
unavailable projection MUST be journaled with its reason and MUST NOT skip the
candidate." That direction is chosen rather than incidental. The floor already
governs the LEVEL of an unprojected reading, so the projection has nothing to
add there; a projection that refused when it could not measure would refuse
every first dispatch on every credential in every fresh checkout, which is the
common case rather than an edge.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

from livespec_orchestrator_beads_fabro.commands._acp_session_headroom import (
    NOT_PROJECTED_RESULT,
    PROJECTED_RESULT,
    UNAVAILABLE_RESULT,
    SessionHeadroomProjection,
    SessionHeadroomReading,
    headroom_skips_candidate,
    seven_day_skips_candidate,
)
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom_drain import (
    SessionHeadroomBaseline,
    drain_rate_attempted,
    parse_session_headroom_instant,
)

__all__: list[str] = [
    "FLOOR_DISABLED_REASON",
    "FLOOR_SKIPPED_READING_REASON",
    "FLOOR_SKIP_KIND",
    "NO_BASELINE_REASON",
    "PROJECTION_SKIP_KIND",
    "SEVEN_DAY_SKIP_KIND",
    "UNOBSERVABLE_READING_REASON",
    "UNREADABLE_OBSERVATION_REASON",
    "UTILIZATION_NOT_HIGHER_REASON",
    "headroom_skip_kind",
    "projection_skips_candidate",
    "reading_with_projection",
    "session_headroom_projection",
]

# The three reasons NO projection was attempted, one per condition the clause
# enumerates. They are distinct values rather than one token because their
# remedies differ completely: the first is an operator's committed dial, the
# second is a credential the floor already refused, and the third is a reading
# that never came back.
FLOOR_DISABLED_REASON = "floor-disabled"
FLOOR_SKIPPED_READING_REASON = "floor-skipped-reading"
UNOBSERVABLE_READING_REASON = "unobservable-reading"

# The three reasons an ATTEMPTED projection could not be measured, one per
# input. `no-baseline` is the clause's "no such baseline exists", which covers
# a credential unassessed in this checkout for 90 minutes, a removed journal,
# and a dispatch from another worktree alike. `utilization-not-higher` is its
# "a window reset or a provider correction occurred between them". The third is
# this module's own: an observation instant that cannot be read is an
# exhaustion instant that cannot be rendered.
NO_BASELINE_REASON = "no-baseline"
UTILIZATION_NOT_HIGHER_REASON = "utilization-not-higher"
UNREADABLE_OBSERVATION_REASON = "unreadable-observation-instant"

# The one spelling of a journaled instant, matching the form every other
# session-headroom instant is written in -- and the form
# `parse_session_headroom_instant` reads back, so a projected exhaustion this
# module renders is one a later pass can parse.
_INSTANT_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

_FLOOR_DISABLED_PERCENT = 0
_HORIZON_DISABLED_MINUTES = 0

# WHICH of the two headroom shortfalls decided one `HEADROOM_SKIP`. They are a
# second field rather than a second skip reason because the clause gives a
# projection skip "exactly the semantics of a floor skip" -- every surface
# keying on the reason must treat them alike -- while also requiring the
# records to "name a projection skip as a projection skip, distinct from a
# floor skip". A reason-level split would have satisfied the second at the cost
# of the first.
FLOOR_SKIP_KIND = "floor"
PROJECTION_SKIP_KIND = "projection"
SEVEN_DAY_SKIP_KIND = "seven-day"


def headroom_skip_kind(*, reading: SessionHeadroomReading, floor_percent: int) -> str | None:
    """Which headroom shortfall stops this candidate, or `None` for none of them.

    The floor is tested first, followed by a provider-rejected weekly allowance,
    then this dispatcher's five-hour projection. A provider rejection is more
    authoritative than an extrapolation, while the floor remains the operator
    dial that governs every shortfall. A zero floor disables the weekly arm via
    `seven_day_skips_candidate`.
    """
    if headroom_skips_candidate(reading=reading, floor_percent=floor_percent):
        return FLOOR_SKIP_KIND
    if seven_day_skips_candidate(reading=reading, floor_percent=floor_percent):
        return SEVEN_DAY_SKIP_KIND
    if projection_skips_candidate(reading=reading):
        return PROJECTION_SKIP_KIND
    return None


def session_headroom_projection(
    *,
    reading: SessionHeadroomReading,
    baseline: SessionHeadroomBaseline | None,
    floor_percent: int,
    horizon_minutes: int,
) -> SessionHeadroomProjection:
    """The ONE projection result this reading carries, whichever kind it is.

    The not-attempted test runs FIRST and is delegated to the same predicate
    the drain rate uses, so the three `not-projected` conditions cannot drift
    apart from the three the rate is withheld for -- they are the same three,
    stated once.

    The governing horizon rides EVERY result, including the two that measured
    nothing. A reader asking why a credential was not refused needs the dial
    that was in force, and a horizon written only onto the measured result
    would make a 0 nobody configured indistinguishable from a projection that
    was never taken.
    """
    if not drain_rate_attempted(reading=reading, floor_percent=floor_percent):
        return SessionHeadroomProjection(
            result=NOT_PROJECTED_RESULT,
            reason=_not_attempted_reason(reading=reading, floor_percent=floor_percent),
            horizon_minutes=horizon_minutes,
        )
    return _attempted_projection(
        reading=reading, baseline=baseline, horizon_minutes=horizon_minutes
    )


def reading_with_projection(
    *, reading: SessionHeadroomReading, projection: SessionHeadroomProjection
) -> SessionHeadroomReading:
    """This reading, carrying the projection taken from it.

    A separate function rather than a constructor argument, for the same reason
    the drain rate is attached rather than passed: the projection needs a
    journal history the reading's own grader has no business reading, so a
    reading carries none until an evaluation holding that history attaches one.
    """
    return replace(reading, projection=projection)


def _not_attempted_reason(*, reading: SessionHeadroomReading, floor_percent: int) -> str:
    """Which of the clause's three not-attempted conditions applied.

    The DIAL is tested first because it outranks the reading: with the floor at
    0 no reading is skipped at all, so reporting a skipped-reading cause there
    would name a skip that did not happen.
    """
    if floor_percent <= _FLOOR_DISABLED_PERCENT:
        return FLOOR_DISABLED_REASON
    if not reading.observable:
        return UNOBSERVABLE_READING_REASON
    return FLOOR_SKIPPED_READING_REASON


def _attempted_projection(
    *,
    reading: SessionHeadroomReading,
    baseline: SessionHeadroomBaseline | None,
    horizon_minutes: int,
) -> SessionHeadroomProjection:
    """The projection a reading the floor passed supports, or why it does not.

    EVERY UNMEASURABLE INPUT IS TESTED IN ONE CONDITION, because they are
    indistinguishable at the record and a reader must not have to guess which
    applied -- the reason names it instead. That guard is also what makes the
    measured branch total: past it the baseline, the rate, the remaining
    headroom and the instant are all in hand, so the exhaustion instant is
    computed without an arm no dispatch could enter.
    """
    rate = reading.five_hour_drain_percent_per_hour
    remaining = reading.remaining_percent
    observed = parse_session_headroom_instant(text=reading.observed_at)
    if baseline is None or rate is None or remaining is None or observed is None:
        return SessionHeadroomProjection(
            result=UNAVAILABLE_RESULT,
            reason=_unavailable_reason(baseline=baseline, observed=observed),
            five_hour_drain_percent_per_hour=rate,
            baseline_observed_at=None if baseline is None else baseline.observed_at,
            horizon_minutes=horizon_minutes,
        )
    exhaustion = observed + timedelta(hours=remaining / rate)
    return SessionHeadroomProjection(
        result=PROJECTED_RESULT,
        five_hour_drain_percent_per_hour=rate,
        baseline_observed_at=baseline.observed_at,
        projected_exhaustion_at=exhaustion.strftime(_INSTANT_FORMAT),
        horizon_minutes=horizon_minutes,
        skip_applied=_exhausts_inside_horizon(
            observed=observed, exhaustion=exhaustion, horizon_minutes=horizon_minutes
        ),
    )


def _exhausts_inside_horizon(
    *, observed: datetime, exhaustion: datetime, horizon_minutes: int
) -> bool:
    """Whether the exhaustion is STRICTLY earlier than the observation plus horizon.

    THE DISABLED-DIAL TEST IS A GUARD AND NOT AN ARITHMETIC ACCIDENT. With a
    horizon of 0 the comparison instant IS the observation instant, and an
    exhaustion computed from a positive rate is never before the observation it
    was computed from -- so the inequality alone happens to skip nobody today.
    The clause RATIFIES that disable, so it is written as something a reader can
    see rather than left to a property of a division nobody states; the measured
    case it catches is a rate reaching here negative, which the drain
    measurement cannot produce but a caller constructing a reading can.

    STRICTNESS IS THE CLAUSE'S OWN WORD, and it is the boundary an almost-correct
    implementation moves: an exhaustion landing exactly ON the horizon is outside
    it, exactly as a remaining headroom equal to the floor passes the floor.
    """
    if horizon_minutes <= _HORIZON_DISABLED_MINUTES:
        return False
    return exhaustion < observed + timedelta(minutes=horizon_minutes)


def projection_skips_candidate(*, reading: SessionHeadroomReading) -> bool:
    """Whether this reading's PROJECTION leaves a covered candidate selectable.

    The comparison was decided where the horizon was in hand, so this only
    READS it. The filter runs once per candidate against one shared reading, so
    a filter that re-derived the inequality would re-derive it per candidate
    against a horizon it would have to be handed anyway -- and two derivations
    of one comparison are how a refusal record comes to disagree with the
    refusal it explains.

    A reading carrying NO projection skips nothing, which is the honest answer
    for every surface that composes a verdict without a policy: wait attention
    and idle-factory take no reading at all, so there is no projection for them
    to be refused by.
    """
    projection = reading.projection
    if projection is None:
        return False
    return projection.skip_applied


def _unavailable_reason(
    *, baseline: SessionHeadroomBaseline | None, observed: datetime | None
) -> str:
    """Which input an attempted projection could not measure.

    The OBSERVATION is reported first because it is the input whose failure
    says least about the credential: a baseline that is present and a rate that
    was computed are both perfectly good, and the thing that stopped the
    projection is a journaled instant nothing can read -- a defect in the
    record rather than a fact about the window.
    """
    if observed is None:
        return UNREADABLE_OBSERVATION_REASON
    if baseline is None:
        return NO_BASELINE_REASON
    return UTILIZATION_NOT_HIGHER_REASON
