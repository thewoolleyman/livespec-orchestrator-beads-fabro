"""Every UNMEASURABLE INPUT that leaves the five-hour drain rate null.

Covers the inputs-unmeasurable arms of `_acp_session_headroom_drain`
(work-item `bd-ib-rszkjc`): the rate is null "when no such baseline exists, or
when the current utilization is not higher than the baseline's". The two arms
that turn on the FLOOR rather than on the inputs -- a floor of 0, and a reading
the floor skipped -- are the sibling
`test_acp_session_headroom_drain_not_projected.py`'s subject, because the floor
lives in the gate and not in this pure decision.

WHY NULL AND NOT ZERO, which is the substitution a reader is most likely to
find harmless. A drain of 0.0 is a perfectly plausible GENUINE reading -- it is
what a credential nobody is spending looks like -- so a coerced zero is
indistinguishable at the record from a measurement, and an operator comparing
the figure against a floor's adequacy would be reading a number nobody took.
That is the same argument the reading's own `unobservable` field rests on, one
level down.

THESE CASES CALL THE PURE FUNCTIONS DIRECTLY, because the baseline arrives here
already selected: `baseline_assessment` has parsed both instants and measured
the span by the time `reading_with_drain_rate` sees one, so a fixture built
through the Dispatcher could not present a baseline independently of the
history that produced it.
"""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro.commands import _acp_session_headroom as headroom
from livespec_orchestrator_beads_fabro.commands import _acp_session_headroom_drain as drain

_NOW = "2026-10-15T12:00:00Z"
_THIRTY_MINUTES_AGO = "2026-10-15T11:30:00Z"
_HALF_AN_HOUR = 0.5
_IDENTITY = "cred-1"


def _baseline(*, utilization: float = 10.0) -> drain.SessionHeadroomBaseline:
    return drain.SessionHeadroomBaseline(
        utilization_percent=utilization,
        observed_at=_THIRTY_MINUTES_AGO,
        elapsed_hours=_HALF_AN_HOUR,
    )


def _reading(*, utilization: object = 25.0) -> headroom.SessionHeadroomReading:
    return headroom.session_headroom_reading(
        credential_identity=_IDENTITY, observed_at=_NOW, utilization=utilization
    )


def test_a_measurable_pair_is_the_positive_control() -> None:
    """Without this, a function that NEVER attached a rate would pass every case."""
    attached = drain.reading_with_drain_rate(reading=_reading(), baseline=_baseline())

    assert attached.five_hour_drain_percent_per_hour == 30.0


def test_no_baseline_leaves_the_rate_null() -> None:
    """A checkout with no history in the window has nothing to measure from."""
    attached = drain.reading_with_drain_rate(reading=_reading(), baseline=None)

    assert attached.five_hour_drain_percent_per_hour is None


def test_an_unobservable_current_reading_leaves_the_rate_null() -> None:
    """There is no current utilization to subtract the baseline's from.

    The reading's own unobservable reason SURVIVES, which is the half a
    coercion would destroy: a rate attached here would report a measurement
    taken from a window that was never read.
    """
    unobservable = headroom.unobservable_session_headroom(
        credential_identity=_IDENTITY, observed_at=_NOW, reason="timed-out"
    )

    attached = drain.reading_with_drain_rate(reading=unobservable, baseline=_baseline())

    assert attached.five_hour_drain_percent_per_hour is None
    assert attached.unobservable == "timed-out"


@pytest.mark.parametrize("utilization", [10.0, 9.9, 4.0, 0.0])
def test_a_window_that_did_not_rise_has_no_drain(utilization: float) -> None:
    """EQUALITY IS INCLUDED: "not higher than the baseline's" is the wording.

    An unmoved window has nothing to divide, and reporting 0.0 there would
    claim a MEASURED rate of zero -- which is exactly what an unspent
    credential genuinely reads as, so the two would be indistinguishable at the
    record.

    A DECREASE is null rather than negative, and it is a REAL state rather than
    a defensive one: the five-hour window ROLLS, so an earlier spend ageing out
    of it lowers utilization between two readings taken 40 minutes apart. A
    negative rate would report a credential REFILLING at a measured pace, which
    an operator judging a floor's adequacy would read as headroom arriving.
    """
    attached = drain.reading_with_drain_rate(
        reading=_reading(utilization=utilization), baseline=_baseline()
    )

    assert attached.five_hour_drain_percent_per_hour is None


def test_a_window_that_rose_by_the_smallest_amount_still_has_a_drain() -> None:
    """The boundary from the other side, so "not higher" cannot creep upward.

    Without this, a guard written as "not higher by some margin" -- or one that
    rounded -- would satisfy every case above while silently discarding the
    slow drains the figure exists to make visible.
    """
    attached = drain.reading_with_drain_rate(
        reading=_reading(utilization=10.5), baseline=_baseline()
    )

    assert attached.five_hour_drain_percent_per_hour == 1.0


def test_no_prior_reading_at_all_is_no_baseline() -> None:
    """The empty history, which is what a journal holding no assessment gives."""
    assert drain.baseline_assessment(priors=(), now_iso=_NOW) is None
