"""Integration-tier acceptance for worker credential projection.

Binds SPECIFICATION/contracts.md "Worker credential projection" plus
SPECIFICATION/scenarios.md Scenario 18 and Scenario 19. These tests drive the
Dispatcher's run-config overlay materialization boundary with injected host
credential and clock inputs: a fresh Codex credential projects into the sandbox
alongside the existing Claude OAuth env, while a stale credential refuses before
writing an overlay.

The live clause that the Codex worker authenticates from the projected
`$CODEX_HOME/auth.json` remains a provisioned-environment acceptance check; this
hermetic tier proves the Dispatcher assembles exactly the file/env projection
that the live adapter reads.
"""

from __future__ import annotations

import base64
import json
import stat
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import dispatcher
from livespec_orchestrator_beads_fabro.commands.dispatcher import (
    _materialize_overlay,  # pyright: ignore[reportPrivateUsage]
)

_COMMITTED_WORKFLOW_TOML = (
    "_version = 1\n"
    "\n"
    "[workflow]\n"
    'graph = "workflow.fabro"\n'
    "\n"
    "[run.environment]\n"
    'id = "livespec-ci"\n'
)

_FLEET_MANIFEST_TEXT = (
    "{\n"
    '  "owner": "thewoolleyman",\n'
    '  "members": [{ "repo": "livespec", "class": "core" }]\n'
    "}\n"
)

_FAKE_CLAUDE_TOKEN = "test-oauth-token"
_FAKE_GITHUB_TOKEN = "test-github-token"
_HOST_REFRESH_TOKEN = "host-refresh-token"


def _auth_json_with_exp(*, exp: int) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    access_token = f"header.{payload}.sig"
    return json.dumps(
        {
            "auth_mode": "chatgpt",
            "tokens": {
                "access_token": access_token,
                "refresh_token": _HOST_REFRESH_TOKEN,
                "id_token": "id-token-value",
                "account_id": "acct-123",
            },
        }
    )


def _workflow_toml(*, tmp_path: Path) -> Path:
    committed = tmp_path / "workflow.toml"
    _ = committed.write_text(_COMMITTED_WORKFLOW_TOML, encoding="utf-8")
    return committed


@pytest.fixture(autouse=True)
def _dispatcher_projection_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", _FAKE_CLAUDE_TOKEN)
    monkeypatch.setenv("GH_TOKEN", _FAKE_GITHUB_TOKEN)
    monkeypatch.setattr(dispatcher, "_fetch_fleet_manifest_text", lambda: _FLEET_MANIFEST_TEXT)


def test_scenario18_dispatch_overlay_projects_dual_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = 1_700_000_000
    far_future = now + 100 * 365 * 24 * 3600
    overlay = tmp_path / "overlay.toml"
    monkeypatch.setattr(dispatcher.time, "time", lambda: now)
    monkeypatch.setattr(
        dispatcher, "_read_host_codex_auth", lambda: _auth_json_with_exp(exp=far_future)
    )

    error = _materialize_overlay(
        committed=_workflow_toml(tmp_path=tmp_path),
        overlay=overlay,
        repo=tmp_path / "repo",
        work_item_id="bd-ib-webwai",
        dispatch_id="dispatch-1",
    )

    assert error is None
    rendered = overlay.read_text(encoding="utf-8")
    assert stat.S_IMODE(overlay.stat().st_mode) == 0o600
    assert f'CLAUDE_CODE_OAUTH_TOKEN = "{_FAKE_CLAUDE_TOKEN}"' in rendered
    assert 'CODEX_HOME = "/workspace/.codex"' in rendered
    assert "CODEX_AUTH_JSON = " in rendered
    assert (
        'mkdir -p \\"$CODEX_HOME\\" && printf %s \\"$CODEX_AUTH_JSON\\" > '
        '\\"$CODEX_HOME/auth.json\\" && chmod 600 \\"$CODEX_HOME/auth.json\\"'
    ) in rendered
    assert _HOST_REFRESH_TOKEN not in rendered


def test_scenario19_stale_codex_credential_refuses_before_overlay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    overlay = tmp_path / "overlay.toml"
    monkeypatch.setattr(dispatcher.time, "time", lambda: 32_000_000_000)
    monkeypatch.setattr(
        dispatcher, "_read_host_codex_auth", lambda: _auth_json_with_exp(exp=1_700_000_000)
    )

    error = _materialize_overlay(
        committed=_workflow_toml(tmp_path=tmp_path),
        overlay=overlay,
        repo=tmp_path / "repo",
        work_item_id="bd-ib-webwai",
        dispatch_id="dispatch-1",
    )

    assert error is not None
    assert "codex login" in error
    assert not overlay.exists()
