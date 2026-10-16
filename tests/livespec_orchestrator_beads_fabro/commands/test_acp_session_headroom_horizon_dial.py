"""The committed admission horizon a projected exhaustion is measured against.

Binds the horizon sentence of `SPECIFICATION/contracts.md` section "Dispatcher
admission, WIP cap, and post-merge acceptance", paragraph "Admission filters
candidates by projected Claude session headroom": "The admission horizon is a
committed-only `dispatcher.session_headroom_horizon_minutes` (integer from 0
through 1440 inclusive, default **180**). It is NOT declared API-configurable,
and is therefore committed-only."

THREE THINGS, AND THE THIRD IS THE ONE NOTHING ELSE WOULD CATCH. The default
and the inclusive range are ordinary dial assertions. "Committed-only" is a
statement about a DIFFERENT surface: the key must be absent from the
API-configurable key manifest, because that manifest is what makes a setting
reachable over the `drive --action set-config` write surface. A dial that
behaved perfectly and was also listed there would satisfy every other
assertion here while being editable by the very automation whose admission it
governs.

AN OUT-OF-RANGE DIAL RESOLVES TO THE RATIFIED DEFAULT, exactly as its floor
sibling does, and the refusal stays available to a caller that wants to report
the malformed value. Asserting both halves is what keeps a build from
"honouring" 4000 minutes -- a horizon no projection could ever fall outside, so
every covered candidate with a measurable drain would be refused forever.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _acp_session_headroom as headroom
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_session_headroom_gate as headroom_gate,
)
from livespec_orchestrator_beads_fabro.commands import _drive_config_schema as config_schema
from livespec_orchestrator_beads_fabro.commands._dispatcher_claude_credential import (
    CLAUDE_OAUTH_TOKEN_ENV,
)
from returns.pipeline import is_successful

_NOW = "2026-10-16T12:00:00Z"
_TOKEN = "projected-token"


def _read(*, token: str | None, observed_at: str) -> headroom.SessionHeadroomReading:
    """A reading seam that spends no request; this file's subject is the dial."""
    assert token == _TOKEN
    return headroom.session_headroom_reading(
        credential_identity="cred-1", observed_at=observed_at, utilization=10
    )


def _write_horizon(*, root: Path, value: str) -> None:
    _ = (root / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"dispatcher": '
        f'{{"session_headroom_horizon_minutes": {value}}}}}}}',
        encoding="utf-8",
    )


def _policy(*, root: Path) -> headroom.SessionHeadroomPolicy:
    return headroom_gate.session_headroom_policy(
        repo=root,
        now_iso=_NOW,
        journal_path=None,
        read=_read,
    )


def test_the_horizon_defaults_to_the_ratified_one_eighty_and_is_committed_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ratified default reaches the policy, and no write surface exposes it."""
    monkeypatch.setenv(CLAUDE_OAUTH_TOKEN_ENV, _TOKEN)
    assert hasattr(headroom, "DEFAULT_SESSION_HEADROOM_HORIZON_MINUTES")
    assert headroom.DEFAULT_SESSION_HEADROOM_HORIZON_MINUTES == 180

    policy = _policy(root=tmp_path)

    assert policy.horizon_minutes == headroom.DEFAULT_SESSION_HEADROOM_HORIZON_MINUTES
    assert (
        config_schema.config_key_by_name(key=headroom_gate.SESSION_HEADROOM_HORIZON_MINUTES_KEY)
        is None
    )
    # Resolving a SECOND dial must not disturb the one reading the policy's memo
    # exists to guarantee: the seam still sees the projected token once and
    # answers at this evaluation's own observation time.
    assert policy.read().observed_at == _NOW


@pytest.mark.parametrize(("configured", "expected"), [("0", 0), ("1440", 1440), ("45", 45)])
def test_a_committed_horizon_inside_the_inclusive_range_is_honoured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, configured: str, expected: int
) -> None:
    """Both ends of the clause's inclusive range are valid settings."""
    monkeypatch.setenv(CLAUDE_OAUTH_TOKEN_ENV, _TOKEN)
    _write_horizon(root=tmp_path, value=configured)

    assert _policy(root=tmp_path).horizon_minutes == expected


@pytest.mark.parametrize("configured", ["1441", "-1", '"180"', "true", "180.5"])
def test_a_horizon_outside_the_declared_range_is_refused_rather_than_clamped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, configured: str
) -> None:
    """An unreadable dial resolves to the RATIFIED default, never to a guess."""
    monkeypatch.setenv(CLAUDE_OAUTH_TOKEN_ENV, _TOKEN)
    _write_horizon(root=tmp_path, value=configured)

    resolved = headroom_gate.resolve_session_headroom_horizon_minutes(cwd=tmp_path)

    assert is_successful(resolved) is False
    assert (
        _policy(root=tmp_path).horizon_minutes == headroom.DEFAULT_SESSION_HEADROOM_HORIZON_MINUTES
    )
