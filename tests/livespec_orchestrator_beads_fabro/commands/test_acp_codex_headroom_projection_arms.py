"""The two Codex headroom arms a skip-kind reading cannot reach on its own.

Sibling of `test_acp_codex_headroom_admission_skip.py`, which binds the first
assertion of work-item `bd-ib-4jdgcw` through the skip decision. Two of the
decision's own surfaces are unreachable from there, and each is unreachable for
its own reason rather than by accident:

THE DISABLED FLOOR IS SHADOWED BY TWO EARLIER GUARDS. `codex_headroom_skip_kind`
and `codex_projections_attempted` both return before the floor predicate when
the dial is 0, so the predicate's own non-positive arm is reachable only by
calling it. It is nonetheless the arm that matters most: the clause says "a
floor of 0 disables every skip this clause defines", and the UNOBSERVABLE arm
below it is the only one a numeric test cannot reach -- no remaining headroom is
strictly below zero, so a predicate written without the guard passes every
numeric case at a floor of 0 and still refuses on every unreadable response.
That is an operator switching the brake off and finding their dispatches skipped
whenever the usage endpoint times out.

THE ATTACHMENT IS WHAT THE GATE SPENDS ITS JOURNAL READ ON. The reading is
graded before any history is consulted, so the per-window projections are
attached afterwards; the attachment therefore has no caller inside the skip
decision at all. It is asserted to preserve every other field, because a
rebuilt reading that dropped its unobservable result, its provider claim or one
of its two booleans would make the gate's own record disagree with the reading
the filter decided on.

EQUALITY PASSES THE FLOOR, and it is asserted here beside the disabled dial
because the two are the clause's two stated boundaries and an almost-correct
implementation moves either.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands import _acp_codex_headroom as codex
from livespec_orchestrator_beads_fabro.commands import (
    _acp_codex_headroom_projection as projection,
)
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom import (
    NOT_PROJECTED_RESULT,
    SessionHeadroomProjection,
)

_OBSERVED_AT = "2026-10-27T12:00:00Z"
_FIVE_HOURS = 18000


def _reading(*, used: float) -> codex.CodexUsageReading:
    return codex.codex_usage_reading(
        credential_identity="abc",
        observed_at=_OBSERVED_AT,
        rate_limit={
            "allowed": True,
            "limit_reached": False,
            "primary_window": {
                "used_percent": used,
                "limit_window_seconds": _FIVE_HOURS,
            },
        },
    )


def test_a_floor_of_zero_disables_the_floor_predicate_itself() -> None:
    """Both a spent window and an unreadable response pass at a floor of 0."""
    assert not projection.codex_floor_skips_candidate(reading=_reading(used=99), floor_percent=0)
    unreadable = codex.unobservable_codex_usage(
        credential_identity="abc", observed_at=_OBSERVED_AT, reason="timed-out"
    )
    assert not projection.codex_floor_skips_candidate(reading=unreadable, floor_percent=0)


def test_remaining_headroom_equal_to_the_floor_passes() -> None:
    """80 percent used leaves exactly 20 points, which the clause admits."""
    assert not projection.codex_floor_skips_candidate(reading=_reading(used=80), floor_percent=20)
    assert projection.codex_floor_skips_candidate(reading=_reading(used=80.5), floor_percent=20)


def test_an_unreadable_response_is_a_floor_skip_under_a_positive_floor() -> None:
    """The arm the numeric test cannot reach, with the dial switched on."""
    unreadable = codex.unobservable_codex_usage(
        credential_identity="abc", observed_at=_OBSERVED_AT, reason="timed-out"
    )
    assert projection.codex_floor_skips_candidate(reading=unreadable, floor_percent=20)


def test_attaching_projections_preserves_every_other_recorded_fact() -> None:
    """The attachment rebuilds the reading and changes exactly one field."""
    unreadable = codex.unobservable_codex_usage(
        credential_identity="abc",
        observed_at=_OBSERVED_AT,
        reason="timed-out",
        provider_reset_claim="2026-10-27T17:00:00Z",
    )
    attached = projection.reading_with_codex_projections(
        reading=unreadable,
        projections=(
            codex.CodexWindowProjection(
                projection=SessionHeadroomProjection(
                    result=NOT_PROJECTED_RESULT, reason=projection.UNOBSERVABLE_REASON
                )
            ),
        ),
    )
    assert attached.credential_identity == "abc"
    assert attached.observed_at == _OBSERVED_AT
    assert attached.unobservable == "timed-out"
    assert attached.provider_reset_claim == "2026-10-27T17:00:00Z"
    assert attached.allowed is None
    assert attached.limit_reached is None
    assert attached.windows == ()
    assert len(attached.projections) == 1
    assert attached.projections[0].projection.reason == projection.UNOBSERVABLE_REASON


def test_attaching_projections_keeps_a_valid_readings_windows_and_booleans() -> None:
    """The observable arm, so neither branch of the rebuild is unexercised."""
    reading = _reading(used=10)
    attached = projection.reading_with_codex_projections(
        reading=reading,
        projections=projection.codex_window_projections(
            reading=reading, baselines={}, floor_percent=20, horizon_minutes=180
        ),
    )
    assert attached.allowed is True
    assert attached.limit_reached is False
    assert attached.unobservable is None
    assert tuple(window.used_percent for window in attached.windows) == (10.0,)
    assert attached.projections[0].limit_window_seconds == _FIVE_HOURS
