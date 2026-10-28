"""How a Codex reading and skip are rendered into the records.

Binds the record rules of "Admission filters Codex candidates by projected
usage-window headroom" in `SPECIFICATION/contracts.md`: every key is written on
every reading with nulls rather than omissions, an unobservable reading is
rendered as an explicit unobservable result and never as a number, exactly one
projection result is carried per window (or once for a reading with no valid
window), a projection skip names its window, and no record carries a credential
value, the account email or a raw provider response.
"""

from __future__ import annotations

import json
from typing import Any

from livespec_orchestrator_beads_fabro.commands import _acp_codex_headroom as codex
from livespec_orchestrator_beads_fabro.commands import _acp_codex_headroom_projection as projection
from livespec_orchestrator_beads_fabro.commands import _acp_codex_headroom_records as records
from livespec_orchestrator_beads_fabro.commands import (
    _acp_session_headroom_records as claude_records,
)
from livespec_orchestrator_beads_fabro.commands._acp_agent_catalog import CODEX_AGENT_ID
from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import (
    AcpCandidate,
    AcpCandidateIdentity,
)
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import AcpAdapter
from livespec_orchestrator_beads_fabro.commands._acp_preflight_skips import (
    CodexHeadroomShortfall,
    SkippedCandidate,
    codex_headroom_skip,
)
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom_drain import (
    SessionHeadroomBaseline,
)

_NOW = "2026-10-28T06:00:00Z"
_WEEK = 604800


def _graded(*, secondary: float | None = None) -> codex.CodexHeadroomReading:
    return codex.codex_headroom_reading(
        credential_identity="codex-cred",
        observed_at=_NOW,
        response={
            "rate_limit": {
                "allowed": True,
                "limit_reached": False,
                "primary_window": {"used_percent": 10, "limit_window_seconds": 18000},
                "secondary_window": (
                    None
                    if secondary is None
                    else {"used_percent": secondary, "limit_window_seconds": _WEEK}
                ),
            },
            "email": "operator@example.com",
            "credits": {"balance": "900"},
        },
    )


def _baseline() -> SessionHeadroomBaseline:
    return SessionHeadroomBaseline(
        utilization_percent=30.0, observed_at="2026-10-28T05:00:00Z", elapsed_hours=1.0
    )


def _skip(*, reading: codex.CodexHeadroomReading, kind: str) -> SkippedCandidate:
    return codex_headroom_skip(
        candidate=_candidate(),
        shortfall=CodexHeadroomShortfall(
            reading=reading, floor_percent=20, horizon_minutes=180, kind=kind
        ),
    )


def _candidate() -> AcpCandidate:
    return AcpCandidate(
        adapter=AcpAdapter(command="codex-acp", env={}, args=()),
        identity=AcpCandidateIdentity(
            display_name="gpt", candidate_key="gpt-5.5", availability_key="openai"
        ),
        agent_id=CODEX_AGENT_ID,
    )


def test_a_projected_two_window_reading_renders_one_result_per_window() -> None:
    assessed = projection.assessed_codex_reading(
        reading=_graded(secondary=60.0),
        baselines={_WEEK: _baseline()},
        floor_percent=20,
        horizon_minutes=180,
    )

    fields = records.codex_headroom_reading_fields(reading=assessed)

    assert fields["credential_identity"] == "codex-cred"
    assert fields["observed_at"] == _NOW
    assert fields["allowed"] is True
    assert fields["limit_reached"] is False
    assert fields["unobservable"] is None
    assert fields["projection"] is None
    windows: Any = fields["windows"]
    primary, secondary = windows
    assert (primary["name"], primary["used_percent"], primary["limit_window_seconds"]) == (
        "primary",
        10.0,
        18000,
    )
    assert primary["remaining_percent"] == 90.0
    assert primary["projection"]["result"] == "unavailable"
    assert primary["projection"]["reason"] == "no-baseline"
    assert secondary["limit_window_seconds"] == _WEEK
    assert secondary["drain_percent_per_hour"] == 30.0
    assert secondary["projection"]["result"] == "projected"
    assert secondary["projection"]["projection_skip_applied"] is True
    assert secondary["projection"]["projected_exhaustion_at"] == "2026-10-28T07:20:00Z"


def test_an_unobservable_reading_renders_an_explicit_result_and_no_window() -> None:
    reading = codex.unobservable_codex_headroom(
        credential_identity="codex-cred", observed_at=_NOW, reason="timed-out"
    )
    assessed = projection.assessed_codex_reading(
        reading=reading, baselines={}, floor_percent=20, horizon_minutes=180
    )

    fields = records.codex_headroom_reading_fields(reading=assessed)

    assert fields["unobservable"] == "timed-out"
    assert fields["windows"] == []
    assert fields["allowed"] is None
    assert fields["limit_reached"] is None
    result: Any = fields["projection"]
    assert (result["result"], result["reason"]) == ("not-projected", "unobservable")


def test_a_reading_that_was_never_projected_renders_an_explicit_null() -> None:
    fields = records.codex_headroom_reading_fields(reading=_graded())

    assert fields["projection"] is None
    windows: Any = fields["windows"]
    window = windows[0]
    assert window["projection"] is None
    assert records.codex_headroom_projection_fields(projection=None) is None


def test_no_credential_email_or_raw_response_reaches_a_record() -> None:
    fields = records.codex_headroom_reading_fields(reading=_graded(secondary=5.0))

    text = json.dumps(fields)
    assert "operator@example.com" not in text
    assert "900" not in text
    assert "credits" not in text


def test_a_projection_skip_names_the_window_whose_projection_fired() -> None:
    assessed = projection.assessed_codex_reading(
        reading=_graded(secondary=60.0),
        baselines={_WEEK: _baseline()},
        floor_percent=20,
        horizon_minutes=180,
    )

    fields = records.codex_headroom_skip_fields(
        skip=_skip(reading=assessed, kind=codex.CODEX_PROJECTION_SKIP_KIND), reading=assessed
    )

    assert fields["headroom_provider"] == "codex"
    assert fields["headroom_skip_kind"] == "projection"
    assert fields["projection_window_seconds"] == _WEEK
    assert fields["availability_key"] == "openai"
    assert fields["candidate_key"] == "gpt-5.5"
    assert fields["session_headroom_floor_percent"] == 20
    assert fields["session_headroom_horizon_minutes"] == 180
    assert "hold_key" not in fields
    assert "cause" not in fields


def test_a_projection_skip_whose_windows_applied_no_skip_names_no_window() -> None:
    reading = _graded()

    fields = records.codex_headroom_skip_fields(
        skip=_skip(reading=reading, kind=codex.CODEX_PROJECTION_SKIP_KIND), reading=reading
    )

    assert fields["projection_window_seconds"] is None


def test_a_non_projection_skip_names_no_window() -> None:
    reading = _graded()

    fields = records.codex_headroom_skip_fields(
        skip=_skip(reading=reading, kind=codex.CODEX_LIMIT_SKIP_KIND), reading=reading
    )

    assert fields["headroom_skip_kind"] == "codex-limit"
    assert fields["projection_window_seconds"] is None
    nested: Any = fields["codex_headroom"]
    assert nested["credential_identity"] == "codex-cred"


def test_the_shared_skip_projection_routes_a_codex_skip_to_the_codex_fields() -> None:
    reading = _graded()
    skip = _skip(reading=reading, kind=codex.CODEX_FLOOR_SKIP_KIND)

    fields = claude_records.session_headroom_skip_fields(skip=skip)

    assert fields["headroom_provider"] == "codex"
    assert "headroom" not in fields
