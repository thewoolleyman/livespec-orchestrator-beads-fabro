"""How fast the five-hour window is emptying, as a JOURNAL-ONLY figure.

Work-item `bd-ib-rszkjc`: the drain rate is "the increase in utilization
percentage points divided by the elapsed hours since a baseline, where the
baseline is the earliest valid assessment of the same credential identity in
the same repository's dispatch journal, for any work-item, observed no less
than 15 minutes and no more than 90 minutes earlier", and it is null "when no
such baseline exists, or when the current utilization is not higher than the
baseline's".

WHY A RATE AT ALL, GIVEN THE FLOOR ALREADY HAS A LEVEL. A dispatch keeps its
dispatch-time credential to the end of the run, so the reading taken at
admission is the only guard an in-flight run has -- and a LEVEL cannot say
whether that guard will still hold an hour from now. The `caam-anthropic-loop`
runner (`livespec-overseer-07`) measured `anthropic-3` draining about 15 points
of its five-hour window per 30-minute tick, faster than the loop's own rotation
cadence. The same 20 percent floor is ample against a 2-point-per-hour drain
and useless against a 30-point one, and nothing in the journal could tell an
operator which it was facing. This figure is what makes the floor's adequacy
JUDGEABLE; gating on it would be a specification change, so it gates nothing.

PURE, AND THE WINDOW IS NAMED ONCE. `_dispatcher_session_headroom_baseline`
reads the dispatch journal and projects candidates; everything that DECIDES --
which candidate is the baseline, and what the rate is -- lives here, so the
whole decision is exercisable across every state without a journal on disk.

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

THE BASELINE IS THE EARLIEST IN-WINDOW CANDIDATE, NOT THE NEWEST, and the two
are not interchangeable. The earliest gives the longest span the window
supports, so one unusually cheap or expensive pass moves it least; the newest
makes the rate a report about the last few minutes, which is the quantity the
level already tells you. Selection is by OBSERVATION INSTANT and never by
journal position: the dispatch journal is appended to by concurrent passes and
`_dispatcher_io.JournalFile` stamps its envelope `at` at APPEND time, so a
record's place in the file is not evidence about when its reading was taken.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from livespec_orchestrator_beads_fabro.commands._acp_session_headroom import (
    SessionHeadroomReading,
)
from livespec_orchestrator_beads_fabro.effects import IsoDatetimeParseFailure, parse_iso_datetime

__all__: list[str] = [
    "SESSION_HEADROOM_BASELINE_MAXIMUM_MINUTES",
    "SESSION_HEADROOM_BASELINE_MINIMUM_MINUTES",
    "SessionHeadroomBaseline",
    "baseline_assessment",
    "parse_session_headroom_instant",
    "reading_with_drain_rate",
]

# The inclusive age window a prior assessment must fall inside to serve as a
# baseline, in minutes, per the clause's own figures.
SESSION_HEADROOM_BASELINE_MINIMUM_MINUTES = 15
SESSION_HEADROOM_BASELINE_MAXIMUM_MINUTES = 90

_SECONDS_PER_MINUTE = 60.0
_SECONDS_PER_HOUR = 3600.0


@dataclass(frozen=True, kw_only=True)
class SessionHeadroomBaseline:
    """One earlier VALID assessment of one credential, as a rate's starting point.

    Only a reading that carried a utilization can be one, which is why the
    field is a plain `float` rather than an optional: an unobservable prior has
    no figure to subtract, so excluding it is a property of this type rather
    than a test each caller repeats.
    """

    utilization_percent: float
    observed_at: str


def baseline_assessment(
    *, candidates: tuple[SessionHeadroomBaseline, ...], now_iso: str
) -> SessionHeadroomBaseline | None:
    """The EARLIEST candidate whose age falls inside the inclusive window.

    A candidate whose instant cannot be read is passed over rather than
    treated as infinitely old: an unreadable instant is a failure to measure
    the age, and the window is a question about an age.

    "Earliest" is decided on the PARSED instant and never on the recorded text.
    Two instants naming one moment can be spelled differently, and a string
    comparison would order them by spelling -- which reads as a correct answer
    for every fixture that happens to use one spelling.
    """
    now = parse_session_headroom_instant(text=now_iso)
    if now is None:
        return None
    in_window = [
        (instant, candidate)
        for instant, candidate in _dated(candidates=candidates)
        if _within_window(minutes=(now - instant).total_seconds() / _SECONDS_PER_MINUTE)
    ]
    if not in_window:
        return None
    _, earliest = min(in_window, key=lambda pair: pair[0])
    return earliest


def reading_with_drain_rate(
    *,
    reading: SessionHeadroomReading,
    baseline: SessionHeadroomBaseline | None,
    now_iso: str,
) -> SessionHeadroomReading:
    """This reading, carrying its drain rate when its inputs support one.

    Every null condition is kept in ONE place because they are
    indistinguishable at the record and a reader must not have to guess which
    applied: no baseline to measure from, no current utilization to compare,
    and no readable span between the two.
    """
    utilization = reading.utilization_percent
    if baseline is None or utilization is None:
        return reading
    hours = _elapsed_hours(baseline=baseline, now_iso=now_iso)
    if hours is None:
        return reading
    return replace(
        reading,
        five_hour_drain_percent_per_hour=(utilization - baseline.utilization_percent) / hours,
    )


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


def _dated(
    *, candidates: tuple[SessionHeadroomBaseline, ...]
) -> list[tuple[datetime, SessionHeadroomBaseline]]:
    """Every candidate whose recorded instant is readable, paired with it."""
    dated: list[tuple[datetime, SessionHeadroomBaseline]] = []
    for candidate in candidates:
        observed = parse_session_headroom_instant(text=candidate.observed_at)
        if observed is not None:
            dated.append((observed, candidate))
    return dated


def _within_window(*, minutes: float) -> bool:
    return (
        SESSION_HEADROOM_BASELINE_MINIMUM_MINUTES
        <= minutes
        <= SESSION_HEADROOM_BASELINE_MAXIMUM_MINUTES
    )


def _elapsed_hours(*, baseline: SessionHeadroomBaseline, now_iso: str) -> float | None:
    """The hours between the baseline's observation and now, when both are readable.

    A span that is not strictly POSITIVE yields `None` rather than a division:
    `baseline_assessment` cannot produce one, but this function is public
    surface and a zero span would raise from inside an admission evaluation,
    which is a bug-class escape rather than a reading.
    """
    observed = parse_session_headroom_instant(text=baseline.observed_at)
    now = parse_session_headroom_instant(text=now_iso)
    if observed is None or now is None:
        return None
    hours = (now - observed).total_seconds() / _SECONDS_PER_HOUR
    if hours <= 0.0:
        return None
    return hours
