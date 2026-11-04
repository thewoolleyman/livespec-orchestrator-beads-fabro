"""The admission verdict the pre-dispatch session-headroom screen hands the valve.

A leaf split out of `_dispatcher_admission` by cohesion: that module SEQUENCES an
admission pass, while this one owns only the VALUE the screen leaves behind and
the rule for when the valve may still stand on it. Only the PUBLIC names cross
the boundary, and `_dispatcher_admission` keeps the verdict RESOLUTION itself
(`admission_acp_verdict`) because the hermetic test fixture and the policy
builder it patches live there.

The valve reuses the reading only while it is younger than
`SCREENED_VERDICT_REUSE_SECONDS`. The clause requires the assessment "before
claim", and the pre-dispatch rows between the screen and the claim can run for
minutes, so an older reading is repeated rather than trusted; a younger one is
reused because Scenario 231 counts the provider requests of ONE dispatch.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._acp_preflight_verdict import AcpPreflightVerdict

__all__: list[str] = [
    "SCREENED_VERDICT_ARG",
    "SCREENED_VERDICT_REUSE_SECONDS",
    "ScreenedVerdict",
    "reusable_verdict",
    "screened_verdict_of",
    "stamp_screened_verdict",
]

# The `argparse.Namespace` attribute the screen leaves its verdict on, so the
# valve a few rows later can reuse the reading instead of spending a second
# provider request on the same dispatch.
SCREENED_VERDICT_ARG = "session_headroom_screened_verdict"

SCREENED_VERDICT_REUSE_SECONDS = 60.0


@dataclass(frozen=True, kw_only=True)
class ScreenedVerdict:
    """One admission evaluation's verdict, taken ahead of the valve, and when.

    `taken_at` is a MONOTONIC reading so the age test cannot be moved by a wall
    clock step between the screen and the valve.
    """

    verdict: AcpPreflightVerdict
    taken_at: float


def stamp_screened_verdict(*, verdict: AcpPreflightVerdict) -> ScreenedVerdict:
    """Date one verdict now, for the screen to hand on."""
    return ScreenedVerdict(verdict=verdict, taken_at=time.monotonic())


def reusable_verdict(*, screened: ScreenedVerdict | None) -> AcpPreflightVerdict | None:
    """The screened verdict if it is still fresh enough to stand as the valve's own."""
    if screened is None or time.monotonic() - screened.taken_at >= SCREENED_VERDICT_REUSE_SECONDS:
        return None
    return screened.verdict


def screened_verdict_of(*, args: object) -> ScreenedVerdict | None:
    """The screen's verdict as the invocation's arguments carry it, or `None`.

    Read DEFENSIVELY, as the resume attributes are: only the screen sets it, and
    an invocation that never reached the screen simply has none, which the valve
    answers by assessing for itself.
    """
    value = getattr(args, SCREENED_VERDICT_ARG, None)
    return value if isinstance(value, ScreenedVerdict) else None
