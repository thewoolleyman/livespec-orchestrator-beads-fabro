"""Every way the five-hour drain rate is NULL rather than a number.

Covers the unmeasurable-input arms of `_acp_session_headroom_drain`
(work-item `bd-ib-rszkjc`): "the five_hour_drain_percent_per_hour is null when
no such baseline exists", and the record "carries null for that field rather
than a coerced number".

WHY NULL AND NOT ZERO, which is the substitution a reader is most likely to
find harmless. A drain of 0.0 is a perfectly plausible GENUINE reading -- it is
what a credential nobody is spending looks like -- so a coerced zero is
indistinguishable at the record from a measurement, and an operator comparing
the figure against a floor's adequacy would be reading a number nobody took.
That is the same argument the reading's own `unobservable` field rests on, one
level down.

THESE CASES CALL THE PURE FUNCTIONS DIRECTLY, because two of the arms cannot be
reached through the Dispatcher at all: `baseline_assessment` has already parsed
a candidate's instant by the time `reading_with_drain_rate` sees it, and the
Dispatcher stamps `now` from `utc_now_iso`. They are covered because the
functions are public surface and because the alternative to answering `None` in
each is dividing by a span that could not be read -- a bug-class escape from
inside an admission evaluation rather than a reading.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands import _acp_session_headroom as headroom
from livespec_orchestrator_beads_fabro.commands import _acp_session_headroom_drain as drain

_NOW = "2026-10-15T12:00:00Z"
_THIRTY_MINUTES_AGO = "2026-10-15T11:30:00Z"
_IDENTITY = "cred-1"


def _baseline(
    *, utilization: float = 10.0, observed_at: str = _THIRTY_MINUTES_AGO
) -> drain.SessionHeadroomBaseline:
    return drain.SessionHeadroomBaseline(utilization_percent=utilization, observed_at=observed_at)


def _reading(*, utilization: object = 25.0) -> headroom.SessionHeadroomReading:
    return headroom.session_headroom_reading(
        credential_identity=_IDENTITY, observed_at=_NOW, utilization=utilization
    )


def test_a_measurable_pair_is_the_positive_control() -> None:
    """Without this, a function that NEVER attached a rate would pass every case."""
    attached = drain.reading_with_drain_rate(reading=_reading(), baseline=_baseline(), now_iso=_NOW)

    assert attached.five_hour_drain_percent_per_hour == 30.0


def test_no_baseline_leaves_the_rate_null() -> None:
    """A repository with no history in the window has nothing to measure from."""
    attached = drain.reading_with_drain_rate(reading=_reading(), baseline=None, now_iso=_NOW)

    assert attached.five_hour_drain_percent_per_hour is None


def test_an_unobservable_current_reading_leaves_the_rate_null() -> None:
    """There is no current utilization to subtract the baseline's from."""
    unobservable = headroom.unobservable_session_headroom(
        credential_identity=_IDENTITY, observed_at=_NOW, reason="timed-out"
    )

    attached = drain.reading_with_drain_rate(
        reading=unobservable, baseline=_baseline(), now_iso=_NOW
    )

    assert attached.five_hour_drain_percent_per_hour is None
    assert attached.unobservable == "timed-out"


def test_a_baseline_whose_instant_cannot_be_read_leaves_the_rate_null() -> None:
    attached = drain.reading_with_drain_rate(
        reading=_reading(), baseline=_baseline(observed_at="some while back"), now_iso=_NOW
    )

    assert attached.five_hour_drain_percent_per_hour is None


def test_an_unreadable_clock_leaves_the_rate_null() -> None:
    attached = drain.reading_with_drain_rate(
        reading=_reading(), baseline=_baseline(), now_iso="no clock here"
    )

    assert attached.five_hour_drain_percent_per_hour is None


def test_a_span_that_is_not_positive_is_not_divided_by() -> None:
    """A zero or inverted span would raise or invert the sign, not report a rate.

    `baseline_assessment` cannot hand one over -- its window starts at 15
    minutes -- so this guards the public entry point rather than the
    Dispatcher's path through it.
    """
    attached = drain.reading_with_drain_rate(
        reading=_reading(), baseline=_baseline(observed_at=_NOW), now_iso=_NOW
    )
    inverted = drain.reading_with_drain_rate(
        reading=_reading(), baseline=_baseline(observed_at="2026-10-15T12:30:00Z"), now_iso=_NOW
    )

    assert attached.five_hour_drain_percent_per_hour is None
    assert inverted.five_hour_drain_percent_per_hour is None


def test_no_candidate_at_all_is_no_baseline() -> None:
    assert drain.baseline_assessment(candidates=(), now_iso=_NOW) is None
