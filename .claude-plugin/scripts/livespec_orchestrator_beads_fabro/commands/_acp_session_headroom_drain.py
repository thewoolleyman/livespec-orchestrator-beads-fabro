"""How fast the five-hour window is emptying, as a rate on one reading.

`SPECIFICATION/contracts.md` section "Dispatcher admission, WIP cap, and
post-merge acceptance", the paragraph "Admission filters candidates by
projected Claude session headroom": "The five-hour drain rate MUST be computed
from this reading and a baseline. The baseline is the EARLIEST assessment
carrying a valid reading journaled under this clause for the same opaque
credential identity in the dispatching checkout's dispatch journal, read
regardless of the work-item it was journaled for, whose observation time is no
less than 15 minutes and no more than 90 minutes earlier. The rate is the
increase in utilization percentage points divided by the elapsed hours between
the baseline's observation time and this one. The projection is unavailable
when no such baseline exists, or when this reading's utilization is not higher
than the baseline's."

WHY A RATE AT ALL, GIVEN THE FLOOR ALREADY HAS A LEVEL. A dispatch keeps its
dispatch-time credential to the end of the run, so the reading taken at
admission is the only guard an in-flight run has -- and a LEVEL cannot say
whether that guard will still hold an hour from now. The `caam-anthropic-loop`
runner (`livespec-overseer-07`) measured `anthropic-3` draining about 15 points
of its five-hour window per 30-minute tick, faster than the loop's own rotation
cadence. The same 20 percent floor is ample against a 2-point-per-hour drain
and useless against a 30-point one, and nothing in the journal could tell an
operator which it was facing.

PURE, AND THE WINDOW IS NAMED ONCE. `_dispatcher_session_headroom_baseline`
reads the dispatch journal and projects prior readings; everything that
DECIDES -- which prior is the baseline, and what the rate is -- lives here, so
the whole decision is exercisable across every state without a journal on disk.

A PRIOR READING AND A BASELINE ARE DIFFERENT TYPES, and the difference is the
SPAN. A prior reading is a journal row: a utilization and the instant it was
observed at. A baseline is the one prior this evaluation selected, carrying the
elapsed hours MEASURED between that instant and this reading's. Selecting the
prior is the only place both instants are in hand, so measuring the span there
is what keeps the rate from re-parsing two instants it has already parsed --
and what makes a zero or inverted span structurally unreachable rather than a
defensive arm no dispatch can reach: the window's lower bound is 15 minutes, so
every baseline this module can produce carries a span of at least a quarter of
an hour.

EVERY ARM THAT CANNOT MEASURE RETURNS THE READING UNCHANGED, carrying null.
There is no sentinel available: a drain of 0.0 is a perfectly plausible genuine
reading -- it is what a credential nobody is spending looks like -- so a
coerced zero would be indistinguishable downstream from a measured one. That is
the same reason `unobservable` is its own field on the reading rather than a
number, one level down.

THE BOUNDS ARE INCLUSIVE AT BOTH ENDS, which is the clause's own wording and
the boundary an almost-correct implementation moves. The LOWER bound exists
because a rate taken over a few seconds is dominated by whatever one request
happened to cost, and the UPPER bound because the five-hour window ROLLS: a
baseline older than the window's own span is a measurement of a different
window, reported as a rate within this one.

THE BASELINE IS THE EARLIEST IN-WINDOW PRIOR, NOT THE NEWEST, and the two are
not interchangeable. The earliest gives the longest span the window supports,
so one unusually cheap or expensive pass moves it least; the newest makes the
rate a report about the last few minutes, which is the quantity the level
already tells you. Selection is by OBSERVATION INSTANT and never by journal
position: the dispatch journal is appended to by concurrent passes and
`_dispatcher_io.JournalFile` stamps its envelope `at` at APPEND time, so a
record's place in the file is not evidence about when its reading was taken.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from livespec_orchestrator_beads_fabro.commands._acp_session_headroom import (
    SessionHeadroomReading,
    headroom_skips_candidate,
)
from livespec_orchestrator_beads_fabro.effects import IsoDatetimeParseFailure, parse_iso_datetime

__all__: list[str] = [
    "SESSION_HEADROOM_BASELINE_MAXIMUM_MINUTES",
    "SESSION_HEADROOM_BASELINE_MINIMUM_MINUTES",
    "SessionHeadroomBaseline",
    "SessionHeadroomPriorReading",
    "baseline_assessment",
    "drain_rate_attempted",
    "parse_session_headroom_instant",
    "reading_with_drain_rate",
]

# The inclusive age window a prior reading must fall inside to serve as a
# baseline, in minutes, per the clause's own figures.
SESSION_HEADROOM_BASELINE_MINIMUM_MINUTES = 15
SESSION_HEADROOM_BASELINE_MAXIMUM_MINUTES = 90

_SECONDS_PER_MINUTE = 60.0
_MINUTES_PER_HOUR = 60.0


@dataclass(frozen=True, kw_only=True)
class SessionHeadroomPriorReading:
    """One earlier VALID assessment of one credential, as the journal recorded it.

    Only a reading that carried a utilization can be one, which is why the
    field is a plain `float` rather than an optional: an unobservable prior has
    no figure to subtract, so excluding it is a property of this type rather
    than a test each caller repeats.
    """

    utilization_percent: float
    observed_at: str


@dataclass(frozen=True, kw_only=True)
class SessionHeadroomBaseline:
    """The selected prior, plus the span measured between it and this reading.

    `elapsed_hours` is carried rather than recomputed because the selection
    already parsed both instants to apply the age window, and it is a plain
    `float` for the same reason the utilization is: the window's lower bound
    makes a non-positive span unreachable, so the rate divides by it without
    an arm no dispatch could ever enter.
    """

    utilization_percent: float
    observed_at: str
    elapsed_hours: float


def drain_rate_attempted(*, reading: SessionHeadroomReading, floor_percent: int) -> bool:
    """Whether a drain rate is computed for this reading AT ALL.

    The clause names three conditions under which no projection is attempted --
    "the floor is 0, the reading was skipped by the floor, or the reading was
    unobservable" -- and the last two collapse into `headroom_skips_candidate`,
    which is exactly the predicate that decided the skip. Asking it rather than
    re-deriving either condition is what keeps this from becoming a second
    account of the filter: a reading whose remaining headroom sits below the
    floor and a reading that failed to measure are the SAME skip there, and
    they are the same not-attempted answer here.

    THE FLOOR TEST CANNOT BE DELEGATED TO THAT PREDICATE, and the asymmetry is
    the whole reason this is a separate function. A non-positive floor makes
    `headroom_skips_candidate` answer `False` -- the dial disables every kind
    of skip -- so a predicate written as "attempted unless skipped" would
    attempt a projection on precisely the dial setting that switched the clause
    off, which is the one setting with no admission question left to inform.

    NOTHING HERE DECIDES AN ADMISSION OUTCOME. This answers whether a figure is
    MEASURED, and the skip it reads was already decided by the filter; a
    candidate's fate is unchanged by what this returns.
    """
    if floor_percent <= 0:
        return False
    return not headroom_skips_candidate(reading=reading, floor_percent=floor_percent)


def baseline_assessment(
    *, priors: tuple[SessionHeadroomPriorReading, ...], now_iso: str
) -> SessionHeadroomBaseline | None:
    """The EARLIEST prior whose age falls inside the inclusive window.

    A prior whose instant cannot be read is passed over rather than treated as
    infinitely old: an unreadable instant is a failure to measure the age, and
    the window is a question about an age. An unreadable `now` is no baseline
    at all, for the same reason -- there is nothing to measure the age against.

    "Earliest" is decided on the PARSED instant and never on the recorded text.
    Two instants naming one moment can be spelled differently, and a string
    comparison would order them by spelling -- which reads as a correct answer
    for every fixture that happens to use one spelling.
    """
    now = parse_session_headroom_instant(text=now_iso)
    if now is None:
        return None
    in_window: list[tuple[datetime, SessionHeadroomBaseline]] = []
    for instant, prior in _dated(priors=priors):
        minutes = (now - instant).total_seconds() / _SECONDS_PER_MINUTE
        if _within_window(minutes=minutes):
            in_window.append((instant, _baseline(prior=prior, minutes=minutes)))
    if not in_window:
        return None
    _, earliest = min(in_window, key=lambda pair: pair[0])
    return earliest


def reading_with_drain_rate(
    *, reading: SessionHeadroomReading, baseline: SessionHeadroomBaseline | None
) -> SessionHeadroomReading:
    """This reading, carrying its drain rate when its inputs support one.

    Every unmeasurable-input condition is kept in ONE place because they are
    indistinguishable at the record and a reader must not have to guess which
    applied: no baseline to measure from, no current utilization to compare,
    and a window that did not RISE.

    "NOT HIGHER" INCLUDES EQUALITY, which is the clause's own wording. An
    unmoved window has nothing to divide, and reporting 0.0 there would claim a
    MEASURED rate of zero -- which is exactly what an unspent credential
    genuinely reads as, so the two would be indistinguishable at the record.

    A DECREASE is null rather than negative, and it is a REAL state rather than
    a defensive one: the five-hour window ROLLS, so an earlier spend ageing out
    of it lowers utilization between two readings taken 40 minutes apart. A
    negative rate would report a credential REFILLING at a measured pace, which
    an operator judging a floor's adequacy would read as headroom arriving.
    """
    utilization = reading.utilization_percent
    if baseline is None or utilization is None or utilization <= baseline.utilization_percent:
        return reading
    risen = utilization - baseline.utilization_percent
    return replace(reading, five_hour_drain_percent_per_hour=risen / baseline.elapsed_hours)


def parse_session_headroom_instant(*, text: str) -> datetime | None:
    """One journal instant as a datetime, or `None` when it cannot be read.

    The journal writes the `%Y-%m-%dT%H:%M:%SZ` form and this runtime's
    `fromisoformat` does not accept the trailing `Z`, so the suffix is
    rewritten to the explicit offset it means rather than stripped -- a naive
    datetime would compare unequal against the aware ones every other instant
    here produces.
    """
    parsed = parse_iso_datetime(text=text.removesuffix("Z") + "+00:00")
    if isinstance(parsed, IsoDatetimeParseFailure):
        return None
    return parsed


def _baseline(*, prior: SessionHeadroomPriorReading, minutes: float) -> SessionHeadroomBaseline:
    """One in-window prior promoted to a baseline, carrying its measured span."""
    return SessionHeadroomBaseline(
        utilization_percent=prior.utilization_percent,
        observed_at=prior.observed_at,
        elapsed_hours=minutes / _MINUTES_PER_HOUR,
    )


def _dated(
    *, priors: tuple[SessionHeadroomPriorReading, ...]
) -> list[tuple[datetime, SessionHeadroomPriorReading]]:
    """Every prior whose recorded instant is readable, paired with it."""
    dated: list[tuple[datetime, SessionHeadroomPriorReading]] = []
    for prior in priors:
        observed = parse_session_headroom_instant(text=prior.observed_at)
        if observed is not None:
            dated.append((observed, prior))
    return dated


def _within_window(*, minutes: float) -> bool:
    return (
        SESSION_HEADROOM_BASELINE_MINIMUM_MINUTES
        <= minutes
        <= SESSION_HEADROOM_BASELINE_MAXIMUM_MINUTES
    )
