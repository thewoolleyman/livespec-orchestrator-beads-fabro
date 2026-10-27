"""Admission assesses a `codex-acp` candidate's usage window before it selects.

Binds the first assertion of work-item `bd-ib-4jdgcw`'s Definition of Done, and
through it `SPECIFICATION/contracts.md` section "Provider spend containment",
paragraph "Admission filters Codex candidates by projected usage-window
headroom": "Before claim and final per-node selection, the Dispatcher MUST
assess every otherwise-selectable covered candidate on an admission-required ACP
node, including covered fallbacks"; "The governing remaining headroom of a valid
reading is the smallest remaining headroom among its windows"; "Validity is
decided for the WHOLE reading, never window by window"; and "The candidate MUST
be skipped by a projection skip when any valid window's projected exhaustion
instant is strictly earlier than the observation time plus the horizon."

`SPECIFICATION/scenarios.md` Scenario 243 is the governing scenario.

WHY THE WHOLE-READING VALIDITY RULE IS ASSERTED AS ITS OWN LEG. A response
carrying one healthy window beside one malformed window is the shape an
implementation admits by accident: grading window by window produces a
well-formed reading with a plausible governing headroom, and nothing downstream
announces that half the response was discarded. The clause forbids it in as many
words -- "never window by window ... MUST NOT ... be admitted on its valid part"
-- so the discriminating case is asserted directly rather than left to the shape
of a loop.

WHY COVERAGE IS ASSERTED ON PROVENANCE AND NOT ON SPELLING. The clause says
coverage "MUST follow resolved agent provenance and actual credential
projection, never display text, a model-name prefix, or a spelling inferred from
an opaque availability or candidate key", so a candidate whose availability key
spells the vendor is NOT covered while one whose resolved agent id is `codex-acp`
is. Both directions are asserted, because a predicate reading the key passes the
first leg alone.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._acp_agent_catalog import (
    CLAUDE_AGENT_ID,
    CODEX_AGENT_ID,
)
from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import (
    AcpCandidate,
    AcpCandidateIdentity,
)
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import AcpAdapter

_COMMANDS = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)

_OBSERVED_AT = "2026-10-27T12:00:00Z"
_BASELINE_AT = "2026-10-27T11:00:00Z"
_FIVE_HOURS = 18000
_WEEK = 604800


def _module(name: str) -> Any:
    return importlib.import_module(f"livespec_orchestrator_beads_fabro.commands.{name}")


def _candidate(*, agent_id: str | None, key: str) -> AcpCandidate:
    return AcpCandidate(
        adapter=AcpAdapter(command="/usr/bin/true"),
        identity=AcpCandidateIdentity(display_name=key, candidate_key=key, availability_key=key),
        agent_id=agent_id,
    )


def _rate_limit(
    *,
    allowed: object = True,
    limit_reached: object = False,
    primary: object | None = None,
    secondary: object | None = None,
) -> dict[str, object]:
    block: dict[str, object] = {"allowed": allowed, "limit_reached": limit_reached}
    if primary is not None:
        block["primary_window"] = primary
    if secondary is not None:
        block["secondary_window"] = secondary
    return block


def _window(*, used: object, seconds: object = _FIVE_HOURS) -> dict[str, object]:
    return {"used_percent": used, "limit_window_seconds": seconds}


def test_the_codex_headroom_modules_exist() -> None:
    """The reading value and its projection decision are shipped modules."""
    assert (_COMMANDS / "_acp_codex_headroom.py").is_file()
    assert (_COMMANDS / "_acp_codex_headroom_projection.py").is_file()


def test_coverage_follows_resolved_agent_provenance() -> None:
    """Only a candidate resolved through `codex-acp` is covered by this clause."""
    codex = _module("_acp_codex_headroom")
    assert codex.CODEX_PROVIDER == "codex"
    assert codex.codex_headroom_covers_candidate(
        candidate=_candidate(agent_id=CODEX_AGENT_ID, key="pool")
    )
    assert not codex.codex_headroom_covers_candidate(
        candidate=_candidate(agent_id=CLAUDE_AGENT_ID, key="codex-sounding-key")
    )
    assert not codex.codex_headroom_covers_candidate(
        candidate=_candidate(agent_id=None, key="codex")
    )


def test_a_valid_reading_governs_on_its_smallest_remaining_window() -> None:
    """Two valid windows: the governing headroom is the smaller remainder."""
    codex = _module("_acp_codex_headroom")
    reading = codex.codex_usage_reading(
        credential_identity="abc",
        observed_at=_OBSERVED_AT,
        rate_limit=_rate_limit(primary=_window(used=10), secondary=_window(used=85, seconds=_WEEK)),
    )
    assert reading.observable
    assert reading.allowed is True
    assert reading.limit_reached is False
    assert reading.governing_remaining_percent == 15.0
    assert tuple(window.limit_window_seconds for window in reading.windows) == (
        _FIVE_HOURS,
        _WEEK,
    )
    assert not reading.limit_refused


def test_a_limit_reached_or_not_allowed_reading_is_a_codex_limit_refusal() -> None:
    """`allowed` false or `limit_reached` true refuses whatever the windows say."""
    codex = _module("_acp_codex_headroom")
    reached = codex.codex_usage_reading(
        credential_identity="abc",
        observed_at=_OBSERVED_AT,
        rate_limit=_rate_limit(limit_reached=True, primary=_window(used=1)),
    )
    refused = codex.codex_usage_reading(
        credential_identity="abc",
        observed_at=_OBSERVED_AT,
        rate_limit=_rate_limit(allowed=False, primary=_window(used=10)),
    )
    assert reached.limit_refused
    assert refused.limit_refused


def test_every_reading_that_is_not_wholly_valid_is_unobservable() -> None:
    """A valid window beside a malformed one does not admit the reading."""
    codex = _module("_acp_codex_headroom")

    def graded(block: object) -> Any:
        return codex.codex_usage_reading(
            credential_identity="abc", observed_at=_OBSERVED_AT, rate_limit=block
        )

    assert graded("not-a-mapping").unobservable == codex.UNREADABLE_USAGE_RESPONSE
    assert graded(_rate_limit(allowed="yes", primary=_window(used=10))).unobservable is not None
    assert (
        graded(_rate_limit(limit_reached=None, primary=_window(used=10))).unobservable is not None
    )
    assert graded(_rate_limit()).unobservable is not None
    mixed = graded(
        _rate_limit(primary=_window(used=10), secondary=_window(used="high", seconds=_WEEK))
    )
    assert mixed.unobservable is not None
    assert mixed.windows == ()
    assert mixed.governing_remaining_percent is None
    assert not mixed.limit_refused
    assert graded(_rate_limit(primary=_window(used=10, seconds=0))).unobservable is not None
    assert graded(_rate_limit(primary=_window(used=101))).unobservable is not None
    assert graded(_rate_limit(primary=_window(used=True))).unobservable is not None
    assert graded(_rate_limit(primary="window")).unobservable is not None
    assert graded(_rate_limit(primary=_window(used=10, seconds=True))).unobservable is not None


def test_an_explicitly_null_window_is_absent_rather_than_malformed() -> None:
    """`secondary_window: null` leaves one valid window and a valid reading."""
    codex = _module("_acp_codex_headroom")
    reading = codex.codex_usage_reading(
        credential_identity="abc",
        observed_at=_OBSERVED_AT,
        rate_limit={
            "allowed": True,
            "limit_reached": False,
            "primary_window": _window(used=10),
            "secondary_window": None,
        },
    )
    assert reading.observable
    assert reading.governing_remaining_percent == 90.0


def test_an_unobservable_reading_carries_its_reason_and_no_windows() -> None:
    """The explicit unobservable result names the measurement that failed."""
    codex = _module("_acp_codex_headroom")
    reading = codex.unobservable_codex_usage(
        credential_identity="abc", observed_at=_OBSERVED_AT, reason="timed-out"
    )
    assert reading.unobservable == "timed-out"
    assert not reading.observable
    assert reading.windows == ()
    assert reading.projections == ()


def _projected(
    *,
    used: float,
    baseline_used: float,
    floor: int = 20,
    horizon: int = 180,
    seconds: int = _FIVE_HOURS,
    baseline_seconds: int | None = None,
) -> Any:
    codex = _module("_acp_codex_headroom")
    projection = _module("_acp_codex_headroom_projection")
    drain = _module("_acp_session_headroom_drain")
    reading = codex.codex_usage_reading(
        credential_identity="abc",
        observed_at=_OBSERVED_AT,
        rate_limit=_rate_limit(primary=_window(used=used, seconds=seconds)),
    )
    key = seconds if baseline_seconds is None else baseline_seconds
    baselines = {
        key: drain.SessionHeadroomBaseline(
            utilization_percent=baseline_used, observed_at=_BASELINE_AT, elapsed_hours=1.0
        )
    }
    return reading, projection.codex_window_projections(
        reading=reading, baselines=baselines, floor_percent=floor, horizon_minutes=horizon
    )


def test_a_projected_exhaustion_inside_the_horizon_skips_the_candidate() -> None:
    """40 points left draining 30 points an hour empties inside 180 minutes."""
    projection = _module("_acp_codex_headroom_projection")
    headroom = _module("_acp_session_headroom")
    reading, projections = _projected(used=60, baseline_used=30)
    assert len(projections) == 1
    entry = projections[0]
    assert entry.limit_window_seconds == _FIVE_HOURS
    assert entry.projection.result == headroom.PROJECTED_RESULT
    assert entry.projection.skip_applied
    assert entry.projection.five_hour_drain_percent_per_hour == 30.0
    assert entry.projection.baseline_observed_at == _BASELINE_AT
    assert entry.projection.projected_exhaustion_at == "2026-10-27T13:20:00Z"
    skipping = reading.__class__(
        credential_identity=reading.credential_identity,
        observed_at=reading.observed_at,
        allowed=reading.allowed,
        limit_reached=reading.limit_reached,
        windows=reading.windows,
        projections=projections,
    )
    assert (
        projection.codex_headroom_skip_kind(reading=skipping, floor_percent=20)
        == projection.PROJECTION_SKIP_KIND
    )


def test_a_projection_outside_the_horizon_does_not_skip() -> None:
    """A 2-point-per-hour drain on 40 points left empties 20 hours out."""
    headroom = _module("_acp_session_headroom")
    _, projections = _projected(used=60, baseline_used=58)
    assert projections[0].projection.result == headroom.PROJECTED_RESULT
    assert not projections[0].projection.skip_applied


def test_a_baseline_of_one_window_length_is_never_used_for_another() -> None:
    """The only in-window baseline was recorded for a different window length."""
    headroom = _module("_acp_session_headroom")
    projection = _module("_acp_codex_headroom_projection")
    _, projections = _projected(used=60, baseline_used=30, baseline_seconds=_WEEK)
    entry = projections[0]
    assert entry.projection.result == headroom.UNAVAILABLE_RESULT
    assert entry.projection.reason == projection.NO_BASELINE_REASON
    assert not entry.projection.skip_applied


def test_a_window_that_did_not_rise_is_unavailable_rather_than_zero() -> None:
    """An unmoved or falling window has no rate, and never a measured zero."""
    headroom = _module("_acp_session_headroom")
    projection = _module("_acp_codex_headroom_projection")
    _, flat = _projected(used=60, baseline_used=60)
    _, fell = _projected(used=60, baseline_used=70)
    for projections in (flat, fell):
        assert projections[0].projection.result == headroom.UNAVAILABLE_RESULT
        assert projections[0].projection.reason == projection.UTILIZATION_NOT_HIGHER_REASON
        assert projections[0].projection.five_hour_drain_percent_per_hour is None


def test_an_unreadable_observation_instant_is_its_own_unavailable_reason() -> None:
    """A journaled instant nothing can parse cannot render an exhaustion."""
    codex = _module("_acp_codex_headroom")
    headroom = _module("_acp_session_headroom")
    projection = _module("_acp_codex_headroom_projection")
    drain = _module("_acp_session_headroom_drain")
    reading = codex.codex_usage_reading(
        credential_identity="abc",
        observed_at="not-an-instant",
        rate_limit=_rate_limit(primary=_window(used=60)),
    )
    projections = projection.codex_window_projections(
        reading=reading,
        baselines={
            _FIVE_HOURS: drain.SessionHeadroomBaseline(
                utilization_percent=30.0, observed_at=_BASELINE_AT, elapsed_hours=1.0
            )
        },
        floor_percent=20,
        horizon_minutes=180,
    )
    assert projections[0].projection.result == headroom.UNAVAILABLE_RESULT
    assert projections[0].projection.reason == projection.UNREADABLE_OBSERVATION_REASON


def test_every_reading_the_floor_settles_carries_a_not_projected_result() -> None:
    """The four not-projected reasons, one per condition the clause enumerates."""
    codex = _module("_acp_codex_headroom")
    headroom = _module("_acp_session_headroom")
    projection = _module("_acp_codex_headroom_projection")

    def reasons(*, rate_limit: object, floor: int) -> list[Any]:
        reading = codex.codex_usage_reading(
            credential_identity="abc", observed_at=_OBSERVED_AT, rate_limit=rate_limit
        )
        entries = projection.codex_window_projections(
            reading=reading, baselines={}, floor_percent=floor, horizon_minutes=180
        )
        assert all(one.projection.result == headroom.NOT_PROJECTED_RESULT for one in entries)
        assert not any(one.projection.skip_applied for one in entries)
        return [one.projection.reason for one in entries]

    assert reasons(rate_limit=_rate_limit(primary=_window(used=10)), floor=0) == [
        projection.FLOOR_ZERO_REASON
    ]
    assert reasons(
        rate_limit=_rate_limit(limit_reached=True, primary=_window(used=10)), floor=20
    ) == [projection.CODEX_LIMIT_REASON]
    assert reasons(rate_limit=_rate_limit(primary=_window(used=85)), floor=20) == [
        projection.FLOOR_SKIP_REASON
    ]
    assert reasons(rate_limit="broken", floor=20) == [projection.UNOBSERVABLE_REASON]


def test_a_reading_with_no_valid_window_carries_one_not_projected_result() -> None:
    """ "Or once, when no window is valid" -- never an empty projection list."""
    codex = _module("_acp_codex_headroom")
    projection = _module("_acp_codex_headroom_projection")
    reading = codex.unobservable_codex_usage(
        credential_identity="abc", observed_at=_OBSERVED_AT, reason="timed-out"
    )
    entries = projection.codex_window_projections(
        reading=reading, baselines={}, floor_percent=20, horizon_minutes=180
    )
    assert len(entries) == 1
    assert entries[0].limit_window_seconds is None
    assert entries[0].projection.reason == projection.UNOBSERVABLE_REASON


def test_the_skip_kinds_are_the_three_this_clause_defines() -> None:
    """A Codex limit skip, a floor skip and an unobservable floor skip."""
    codex = _module("_acp_codex_headroom")
    projection = _module("_acp_codex_headroom_projection")

    def kind(*, rate_limit: object, floor: int = 20) -> str | None:
        reading = codex.codex_usage_reading(
            credential_identity="abc", observed_at=_OBSERVED_AT, rate_limit=rate_limit
        )
        return projection.codex_headroom_skip_kind(reading=reading, floor_percent=floor)

    assert (
        kind(rate_limit=_rate_limit(limit_reached=True, primary=_window(used=1)))
        == projection.CODEX_LIMIT_SKIP_KIND
    )
    assert (
        kind(rate_limit=_rate_limit(allowed=False, primary=_window(used=1)))
        == projection.CODEX_LIMIT_SKIP_KIND
    )
    assert kind(rate_limit=_rate_limit(primary=_window(used=85))) == projection.FLOOR_SKIP_KIND
    assert kind(rate_limit="broken") == projection.FLOOR_SKIP_KIND
    assert kind(rate_limit=_rate_limit(primary=_window(used=80))) is None
    assert (
        kind(rate_limit=_rate_limit(limit_reached=True, primary=_window(used=99)), floor=0) is None
    )
