"""Hermetic tests for the Codex credential projection transform.

`project_codex_auth_snapshot` is the non-rotatable-snapshot core of the
`Worker credential projection` contract (scenarios.md Scenario 18): it
replaces `tokens.refresh_token` with an inert sentinel while preserving
every other field, so a worker sandbox cannot rotate the shared
credential.
"""

from __future__ import annotations

import json

from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    CODEX_NON_ROTATABLE_REFRESH_SENTINEL,
    project_codex_auth_snapshot,
)

_SOURCE_AUTH = json.dumps(
    {
        "auth_mode": "chatgpt",
        "tokens": {
            "id_token": "id-token-value",
            "access_token": "access-token-value",
            "refresh_token": "REAL-host-refresh-token-must-not-leak",
            "account_id": "acct-123",
        },
        "last_refresh": "2026-06-18T23:58:53Z",
    }
)


def test_projection_replaces_refresh_token_with_sentinel() -> None:
    projected = json.loads(project_codex_auth_snapshot(source_auth_json=_SOURCE_AUTH))
    assert projected["tokens"]["refresh_token"] == CODEX_NON_ROTATABLE_REFRESH_SENTINEL


def test_projection_does_not_leak_the_real_refresh_token() -> None:
    out = project_codex_auth_snapshot(source_auth_json=_SOURCE_AUTH)
    assert "REAL-host-refresh-token-must-not-leak" not in out


def test_projection_preserves_all_non_refresh_fields() -> None:
    projected = json.loads(project_codex_auth_snapshot(source_auth_json=_SOURCE_AUTH))
    assert projected["auth_mode"] == "chatgpt"
    assert projected["last_refresh"] == "2026-06-18T23:58:53Z"
    tokens = projected["tokens"]
    assert tokens["id_token"] == "id-token-value"
    assert tokens["access_token"] == "access-token-value"
    assert tokens["account_id"] == "acct-123"
