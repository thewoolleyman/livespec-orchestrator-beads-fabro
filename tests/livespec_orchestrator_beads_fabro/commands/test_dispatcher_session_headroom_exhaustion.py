"""A provider-exhaustion record naming no credential identity skips no pool slot.

Binds the identity-less control beside bd-ib-wx4yha's slot skip. A record minted
before records carried an account, or for a dispatch whose admission journaled no
identity, names no slot, so it cannot say which slot to pass over. It keeps its
vendor-wide coverage through the existing exhaustion refusal, and the pool
ranking is exactly what it was without it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _acp_session_headroom as headroom
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_session_headroom_gate as headroom_gate,
)

_NOW = "2026-11-14T07:30:00Z"
_IDENTITY_BY_TOKEN = {"token-0": "identity-0", "token-1": "identity-1"}
_RESET_BY_TOKEN = {"token-0": "1700000000", "token-1": "1800000000"}


def _read(*, token: str | None, observed_at: str) -> headroom.SessionHeadroomReading:
    key = token or ""
    return headroom.session_headroom_reading(
        credential_identity=_IDENTITY_BY_TOKEN.get(key, "unnumbered"),
        observed_at=observed_at,
        utilization=10,
        provider_reset_claim=_RESET_BY_TOKEN.get(key),
    )


def test_an_identityless_exhaustion_record_leaves_the_soonest_reset_slot_chosen(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    journal = tmp_path / "fabro-dispatch-journal.jsonl"
    record = {
        "at": "2026-11-14T07:29:00Z",
        "stage": "provider-exhaustion-observed",
        "provider": "anthropic",
        "governing_condition": "provider_usage_limit",
        "record_expires_at": "2026-11-14T07:44:00Z",
        "work_item_id": "bd-ib-yw7yot",
    }
    _ = journal.write_text(json.dumps(record) + "\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_0", "token-0")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_1", "token-1")
    policy = headroom_gate.session_headroom_policy(
        repo=tmp_path, now_iso=_NOW, journal_path=journal, read=_read
    )
    chosen = policy.read()
    assert policy.pool_read is not None
    expiries = [reading.provider_exhaustion_expires_at for reading in policy.pool_read()]
    assert (chosen.credential_identity, expiries) == ("identity-0", [None, None])
