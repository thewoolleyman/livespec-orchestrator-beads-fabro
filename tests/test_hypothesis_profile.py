"""The suite's hypothesis profile: no per-example wall-clock deadline.

WHY THIS IS BOUND BY A TEST RATHER THAN LEFT TO THE CONFTEST. Hypothesis's
default 200ms deadline is a PERFORMANCE assertion about the host, and under
`just check` — 7000+ tests, four xdist workers, branch coverage tracing every
statement, on a shared factory host at load — one example stalling past it is a
scheduler hiccup reported as `FlakyFailure: Unreliable test timings!`. That is a
red gate whose only remedy is to run the suite again, and it fires on whichever
property test happens to be scheduled during the stall rather than on the one
that is wrong. `tests/conftest.py` disarms it; without a test, a later edit
restores the default silently and the flake comes back as a mystery.

WHY TWO ASSERTIONS AND NOT ONE. The first reads the CONFIGURATION, which is the
cheap half and the half that cannot distinguish a profile that was registered
from one that was also loaded. The second is the BEHAVIOURAL half: a property
whose body genuinely outruns the retired ceiling, which passes only because no
deadline is enforcing one. A configuration assertion alone would still pass if
some later plugin re-armed the deadline after the profile loaded.

WHAT THIS DOES NOT WEAKEN. The deadline is the only thing turned off. Every
property test still runs its full example budget and every assertion in it still
holds; what is gone is a verdict on how fast the host executed them.
"""

from __future__ import annotations

import time

from hypothesis import given, settings
from hypothesis import strategies as st

# Comfortably past hypothesis's 200ms default, so the stall cannot be mistaken
# for noise, and small enough that one example costs the suite a quarter second.
_PAST_THE_RETIRED_DEADLINE_SECONDS = 0.25


def test_the_loaded_profile_enforces_no_wall_clock_deadline() -> None:
    """The configuration half: the active profile carries no deadline at all."""
    assert settings().deadline is None


@settings(max_examples=1)
@given(size=st.integers(min_value=0, max_value=10**12))
def test_an_example_slower_than_the_retired_deadline_still_passes(*, size: int) -> None:
    """The behavioural half: a stalled example is not a failing example.

    This is the janitor's own failure condition, reproduced deliberately. With the
    default deadline in force this body raises `DeadlineExceeded` and the test
    reports as `FlakyFailure`; it passes here because the profile retired the
    timing verdict, not because the stall got faster.

    THE REAL SLEEP IS THE SUBJECT, so `check-tests-no-real-time` is stood down
    here rather than satisfied. What is asserted is that a body which genuinely
    outruns hypothesis's retired 200ms ceiling still passes, and hypothesis
    measures that ceiling on the host clock: an injected clock would leave
    nothing for the retired deadline to have declined to enforce.
    """
    # real-time-required: the retired wall-clock deadline IS what this asserts
    time.sleep(_PAST_THE_RETIRED_DEADLINE_SECONDS)

    assert str(size).isdigit()
