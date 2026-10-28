"""The Codex usage reading: how a decoded response is graded, and which skip it earns.

Binds "Admission filters Codex candidates by projected usage-window headroom" in
`SPECIFICATION/contracts.md` and the Scenario 243 cases that govern grading:
validity is decided for the WHOLE reading, a credit balance is never headroom,
equality passes the floor, and a floor of 0 disables every skip while the reading
is still graded.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import _acp_codex_headroom as codex
from livespec_orchestrator_beads_fabro.commands._acp_agent_catalog import (
    CLAUDE_AGENT_ID,
    CODEX_AGENT_ID,
)
from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidate
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import AcpAdapter

_NOW = "2026-10-28T06:00:00Z"


def _window(*, used: object = 10, seconds: object = 18000) -> dict[str, object]:
    return {"used_percent": used, "limit_window_seconds": seconds}


def _response(**overrides: object) -> dict[str, Any]:
    limits: dict[str, object] = {
        "allowed": True,
        "limit_reached": False,
        "primary_window": _window(),
        "secondary_window": None,
    }
    limits.update(overrides)
    return {"rate_limit": limits, "credits": {"has_credits": True, "balance": "900"}}


def _graded(response: object) -> codex.CodexHeadroomReading:
    return codex.codex_headroom_reading(
        credential_identity="cred", observed_at=_NOW, response=response
    )


def test_a_valid_two_window_response_is_graded_with_each_windows_headroom() -> None:
    reading = _graded(
        _response(
            primary_window=_window(used=85.5), secondary_window=_window(used=10, seconds=604800)
        )
    )

    assert reading.observable is True
    assert reading.allowed is True
    assert reading.limit_reached is False
    assert [(w.name, w.used_percent, w.limit_window_seconds) for w in reading.windows] == [
        ("primary", 85.5, 18000),
        ("secondary", 10.0, 604800),
    ]
    assert [w.remaining_percent for w in reading.windows] == [14.5, 90.0]
    assert reading.governing_remaining_percent == 14.5


def test_a_single_secondary_window_alone_is_a_valid_reading() -> None:
    reading = _graded(_response(primary_window=None, secondary_window=_window(used=40)))

    assert reading.observable is True
    assert [w.name for w in reading.windows] == ["secondary"]


@pytest.mark.parametrize(
    "response",
    [
        None,
        "text",
        {},
        {"rate_limit": None},
        {"rate_limit": {"allowed": True, "limit_reached": False}},
        _response(primary_window=None, secondary_window=None),
        _response(allowed="yes"),
        _response(limit_reached=None),
        _response(allowed=1),
        {"rate_limit": {"limit_reached": False, "primary_window": _window()}},
        _response(primary_window=_window(used="ten")),
        _response(primary_window=_window(used=True)),
        _response(primary_window=_window(used=-1)),
        _response(primary_window=_window(used=100.5)),
        _response(primary_window=_window(used=float("nan"))),
        _response(primary_window=_window(seconds=0)),
        _response(primary_window=_window(seconds=-5)),
        _response(primary_window=_window(seconds=18000.0)),
        _response(primary_window=_window(seconds=True)),
        _response(primary_window="not-a-window"),
        _response(primary_window=_window(used=10), secondary_window=_window(used="x")),
    ],
)
def test_anything_short_of_a_valid_whole_reading_is_unobservable(response: object) -> None:
    reading = _graded(response)

    assert reading.observable is False
    assert reading.unobservable == codex.UNREADABLE_CODEX_RESPONSE
    assert reading.windows == ()
    assert reading.governing_remaining_percent is None
    assert reading.allowed is None


def test_a_valid_window_beside_a_malformed_one_is_never_used_to_admit() -> None:
    reading = _graded(
        _response(primary_window=_window(used=10), secondary_window=_window(used="not a number"))
    )

    assert reading.observable is False
    assert codex.codex_headroom_skip_kind(reading=reading, floor_percent=20) == "floor"


def test_the_inclusive_bounds_of_a_window_are_valid() -> None:
    assert _graded(_response(primary_window=_window(used=0))).observable is True
    assert _graded(_response(primary_window=_window(used=100))).observable is True


@pytest.mark.parametrize(
    ("agent_id", "covered"),
    [(CODEX_AGENT_ID, True), (CLAUDE_AGENT_ID, False), (None, False)],
)
def test_coverage_follows_the_resolved_agent_id_and_nothing_else(
    *, agent_id: str | None, covered: bool
) -> None:
    candidate = AcpCandidate(
        adapter=AcpAdapter(command="codex-acp", env={}, args=()), agent_id=agent_id
    )

    assert codex.codex_headroom_covers_candidate(candidate=candidate) is covered


def _skip_kind(*, floor: int = 20, **overrides: object) -> str | None:
    return codex.codex_headroom_skip_kind(
        reading=_graded(_response(**overrides)), floor_percent=floor
    )


def test_a_healthy_reading_is_not_skipped() -> None:
    assert _skip_kind(primary_window=_window(used=10)) is None


def test_a_window_below_the_floor_is_a_floor_skip() -> None:
    assert _skip_kind(primary_window=_window(used=85)) == codex.CODEX_FLOOR_SKIP_KIND


def test_equality_passes_the_floor() -> None:
    assert _skip_kind(primary_window=_window(used=80)) is None
    assert _skip_kind(primary_window=_window(used=80.5)) == "floor"


def test_the_smallest_remaining_window_governs() -> None:
    kind = _skip_kind(primary_window=_window(used=10), secondary_window=_window(used=95, seconds=1))

    assert kind == "floor"


def test_limit_reached_is_a_codex_limit_skip_even_with_credits() -> None:
    kind = _skip_kind(limit_reached=True, primary_window=_window(used=1))

    assert kind == codex.CODEX_LIMIT_SKIP_KIND


def test_a_not_allowed_account_is_a_codex_limit_skip() -> None:
    assert _skip_kind(allowed=False, primary_window=_window(used=10)) == "codex-limit"


def test_the_limit_skip_outranks_the_floor_skip() -> None:
    assert _skip_kind(allowed=False, primary_window=_window(used=99)) == "codex-limit"


def test_an_unobservable_reading_is_a_floor_skip() -> None:
    assert _skip_kind(allowed="maybe") == codex.CODEX_FLOOR_SKIP_KIND


@pytest.mark.parametrize("floor", [0, -1])
def test_a_non_positive_floor_disables_every_skip(floor: int) -> None:
    assert _skip_kind(floor=floor, limit_reached=True) is None
    assert _skip_kind(floor=floor, primary_window=_window(used=100)) is None
    assert _skip_kind(floor=floor, allowed="maybe") is None


def test_a_projected_exhaustion_inside_the_horizon_is_a_projection_skip() -> None:
    reading = _graded(_response())
    skipping = codex.CodexWindowProjection(
        result="projected", skip_applied=True, horizon_minutes=180
    )
    window = replace(reading.windows[0], projection=skipping)

    projected = replace(reading, windows=(window,))

    assert codex.codex_headroom_skip_kind(reading=projected, floor_percent=20) == "projection"


def test_a_window_whose_projection_applies_no_skip_is_not_skipped() -> None:
    reading = _graded(_response())
    quiet = codex.CodexWindowProjection(result="projected", skip_applied=False)
    quiet_reading = replace(reading, windows=(replace(reading.windows[0], projection=quiet),))

    assert codex.codex_headroom_skip_kind(reading=quiet_reading, floor_percent=20) is None


def test_the_unobservable_constructor_names_the_failed_measurement() -> None:
    reading = codex.unobservable_codex_headroom(
        credential_identity="cred", observed_at=_NOW, reason="timed-out"
    )

    assert reading.unobservable == "timed-out"
    assert reading.observable is False
    assert reading.limit_governs is False
