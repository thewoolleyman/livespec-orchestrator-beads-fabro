"""Resolving one evaluation's Codex reading: at most once, from the right history.

Binds "For each distinct projected Codex credential per admission evaluation, the
Dispatcher MUST issue exactly one bounded usage read ... and MUST reuse that one
reading across every node and candidate sharing the credential" and "applied per
opaque credential identity AND per window length" in `SPECIFICATION/contracts.md`.

The baseline reader is controlled against the three ways a journal read can
return a wrong baseline: another credential's row, another window length's row,
and a row of the OTHER provider's stage.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands import _acp_codex_headroom as codex
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_codex_headroom_gate as codex_gate,
)

_NOW = "2026-10-28T06:00:00Z"
_THEN = "2026-10-28T05:00:00Z"
_FIVE_HOURS = 18000
_WEEK = 604800


def _row(
    *,
    stage: str = codex.CODEX_HEADROOM_STAGE,
    identity: str = "cred",
    seconds: object = _FIVE_HOURS,
    used: object = 30.0,
    observed_at: object = _THEN,
) -> dict[str, object]:
    return {
        "stage": stage,
        "assessments": [
            {
                "credential_identity": identity,
                "observed_at": observed_at,
                "windows": [{"limit_window_seconds": seconds, "used_percent": used}],
            }
        ],
    }


def _journal(tmp_path: Path, *rows: object, extra: tuple[str, ...] = ()) -> Path:
    path = tmp_path / "journal.jsonl"
    lines = [json.dumps(row) for row in rows] + list(extra)
    _ = path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _baseline(path: Path | None, *, identity: str = "cred", seconds: int = _FIVE_HOURS) -> Any:
    return codex_gate.codex_window_baseline(
        journal_path=path, credential_identity=identity, window_seconds=seconds, now_iso=_NOW
    )


def test_the_baseline_is_the_earliest_in_window_row_of_this_credential_and_window(
    tmp_path: Path,
) -> None:
    path = _journal(
        tmp_path,
        _row(used=50.0, observed_at="2026-10-28T05:30:00Z"),
        _row(used=30.0, observed_at=_THEN),
    )

    baseline = _baseline(path)

    assert baseline is not None
    assert baseline.utilization_percent == 30.0
    assert baseline.observed_at == _THEN
    assert baseline.elapsed_hours == 1.0


def test_a_row_of_another_credential_window_length_or_stage_is_never_a_baseline(
    tmp_path: Path,
) -> None:
    path = _journal(
        tmp_path,
        _row(identity="someone-else"),
        _row(seconds=_WEEK),
        _row(stage="acp-session-headroom"),
    )

    assert _baseline(path) is None
    assert _baseline(path, identity="someone-else") is not None
    assert _baseline(path, seconds=_WEEK) is not None


def test_a_missing_or_absent_journal_yields_no_baseline(tmp_path: Path) -> None:
    assert _baseline(None) is None
    assert _baseline(tmp_path / "does-not-exist.jsonl") is None


def test_unreadable_rows_are_skipped_rather_than_read_as_a_baseline(tmp_path: Path) -> None:
    path = _journal(
        tmp_path,
        {"stage": codex.CODEX_HEADROOM_STAGE, "assessments": "nope"},
        {
            "stage": codex.CODEX_HEADROOM_STAGE,
            "assessments": ["nope", {"credential_identity": "cred", "windows": 3}],
        },
        _row(used="thirty"),
        _row(used=True),
        _row(observed_at=12),
        _row(seconds="18000"),
        ["not", "a", "record"],
        extra=("not json at all", ""),
    )

    assert _baseline(path) is None


def _reading(*, used: float = 40.0) -> codex.CodexHeadroomReading:
    return codex.codex_headroom_reading(
        credential_identity="cred",
        observed_at=_NOW,
        response={
            "rate_limit": {
                "allowed": True,
                "limit_reached": False,
                "primary_window": {"used_percent": used, "limit_window_seconds": _FIVE_HOURS},
            }
        },
    )


def _fixed_reading(*, used: float) -> Any:
    def _read(*, auth_json: str | None, observed_at: str) -> codex.CodexHeadroomReading:
        assert (auth_json, observed_at) == (None, _NOW)
        return _reading(used=used)

    return _read


def test_the_source_reads_the_credential_and_the_provider_exactly_once(tmp_path: Path) -> None:
    reads: list[str | None] = []
    auths: list[str] = []

    def _read(*, auth_json: str | None, observed_at: str) -> codex.CodexHeadroomReading:
        assert observed_at == _NOW
        reads.append(auth_json)
        return _reading(used=60.0)

    def _auth() -> str:
        auths.append("read")
        return "snapshot"

    source = codex_gate.codex_headroom_source(
        now_iso=_NOW,
        journal_path=_journal(tmp_path, _row(used=30.0)),
        floor_percent=20,
        horizon_minutes=180,
        read=_read,
        auth=_auth,
    )
    assert reads == []

    first = source()
    second = source()

    assert first is second
    assert reads == ["snapshot"]
    assert auths == ["read"]
    window_projection = first.windows[0].projection
    assert window_projection is not None
    assert window_projection.skip_applied is True


def test_a_settled_reading_does_not_read_the_journal(tmp_path: Path) -> None:
    missing = tmp_path / "never-written.jsonl"

    source = codex_gate.codex_headroom_source(
        now_iso=_NOW,
        journal_path=missing,
        floor_percent=0,
        horizon_minutes=180,
        read=_fixed_reading(used=99.0),
        auth=lambda: None,
    )

    window_projection = source().windows[0].projection
    assert window_projection is not None
    assert window_projection.result == "not-projected"
    assert window_projection.reason == "floor-zero"


def test_with_no_journal_a_passing_window_is_unavailable_not_skipped() -> None:
    source = codex_gate.codex_headroom_source(
        now_iso=_NOW,
        journal_path=None,
        floor_percent=20,
        horizon_minutes=180,
        read=_fixed_reading(used=60.0),
        auth=lambda: None,
    )

    window_projection = source().windows[0].projection
    assert window_projection is not None
    assert window_projection.result == "unavailable"
    assert window_projection.reason == "no-baseline"
    assert window_projection.skip_applied is False
