"""Tests for the dispatch-time dual-credential projection (Slice B).

The Dispatcher reads the host Codex `auth.json`, freshness-gates it, and
projects a NON-rotatable snapshot into the sandbox at `$CODEX_HOME/auth.json`
alongside the existing Claude OAuth env, then flips the implementer nodes
to the Codex ACP adapter (scenarios.md Scenario 18 / Scenario 19). These
tests exercise the PURE overlay surface (`render_run_config_overlay`,
`fabro_run_argv`) plus the host-read + projection helpers in `dispatcher`:
no real `~/.codex` read, no real fabro run, no real clock dependence — the
host-read and the freshness clock are injected so every assertion is
hermetic and deterministic.
"""

from __future__ import annotations

import base64
import json
import stat
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_codex_auth,
    _dispatcher_credentials,
    _dispatcher_sibling_clones,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_auth import (
    CodexProjectionRefusal,
    project_codex_auth,
    read_host_codex_auth,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credentials import (
    materialize_overlay,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    CODEX_IMPLEMENTER_ADAPTER,
    build_plan,
    fabro_run_argv,
    render_run_config_overlay,
)

# A canned fleet manifest so `resolve_sibling_clones` (which runs before
# the codex projection inside `materialize_overlay`) never shells out to a
# real `gh api` in the hermetic tier.
_FLEET_MANIFEST_TEXT = (
    "{\n"
    '  "owner": "thewoolleyman",\n'
    '  "members": [{ "repo": "livespec", "class": "core" }]\n'
    "}\n"
)

# A committed workflow config with the canonical [workflow] graph + the
# [run.environment] id the overlay rewrites/targets (mirrors the shape
# the other overlay tests use).
_COMMITTED_WORKFLOW_TOML = (
    "_version = 1\n"
    "\n"
    "[workflow]\n"
    'graph = "workflow.fabro"\n'
    "\n"
    "[run.environment]\n"
    'id = "livespec-ci"\n'
)

# Bound to locals before passing as `token=` / `github_token=` so ruff's
# S106 (hardcoded password) does not flag the literals.
_FAKE_TOKEN = "test-oauth-token"
_FAKE_GITHUB_TOKEN = "test-github-token"

# A small fake auth.json snapshot string — the projection input. Multi-line
# so the test proves the env-table encoding survives newlines (json.dumps
# single-line-encodes them with \n escapes, which is valid TOML).
_FAKE_SNAPSHOT = json.dumps(
    {"auth_mode": "chatgpt", "tokens": {"access_token": "a", "refresh_token": "sentinel"}},
    indent=2,
)


def _auth_json_with_exp(*, exp: int) -> str:
    """Build a fake Codex auth.json whose access-token JWT carries `exp`."""
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    access_token = f"header.{payload}.sig"
    return json.dumps(
        {
            "auth_mode": "chatgpt",
            "tokens": {
                "access_token": access_token,
                "refresh_token": "host-refresh-token",
                "id_token": "id-token-value",
                "account_id": "acct-123",
            },
        }
    )


# ---------------------------------------------------------------------------
# render_run_config_overlay — the codex_auth_snapshot projection
# ---------------------------------------------------------------------------


def test_render_overlay_projects_codex_auth_snapshot(tmp_path: Path) -> None:
    """A non-None snapshot adds the prepare step + the two env-table lines."""
    rendered = render_run_config_overlay(
        committed_text=_COMMITTED_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=_FAKE_TOKEN,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=None,
        codex_auth_snapshot=_FAKE_SNAPSHOT,
    )
    assert rendered is not None
    # The prepare step writes the file the codex-acp adapter reads, before
    # the agent nodes start. It renders in the prepare-steps region (before
    # the env table header).
    prepare_region, env_table = rendered.split("[environments.livespec-ci.env]", 1)
    assert (
        'mkdir -p \\"$CODEX_HOME\\" && printf %s \\"$CODEX_AUTH_JSON\\" > '
        '\\"$CODEX_HOME/auth.json\\" && chmod 600 \\"$CODEX_HOME/auth.json\\"'
    ) in prepare_region
    assert "[[run.prepare.steps]]" in prepare_region
    # The container-level env table carries CODEX_HOME + CODEX_AUTH_JSON so
    # both the prepare-step shell and the codex-acp child inherit them.
    assert 'CODEX_HOME = "/workspace/.codex"' in env_table
    # The CODEX_AUTH_JSON value round-trips back to the snapshot (it was
    # json.dumps-encoded, single-lining the multi-line JSON with \n escapes).
    auth_line = next(
        line for line in env_table.splitlines() if line.startswith("CODEX_AUTH_JSON = ")
    )
    decoded = json.loads(auth_line[len("CODEX_AUTH_JSON = ") :])
    assert decoded == _FAKE_SNAPSHOT


def test_render_overlay_without_codex_snapshot_is_unchanged(tmp_path: Path) -> None:
    """Omitting the snapshot keeps the overlay byte-identical (backward compat)."""
    rendered = render_run_config_overlay(
        committed_text=_COMMITTED_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=_FAKE_TOKEN,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=None,
    )
    assert rendered is not None
    assert "CODEX_HOME" not in rendered
    assert "CODEX_AUTH_JSON" not in rendered
    assert "auth.json" not in rendered


# ---------------------------------------------------------------------------
# fabro_run_argv — the static Codex implementer-adapter routing
# ---------------------------------------------------------------------------


def test_fabro_run_argv_routes_implementer_to_codex_adapter(tmp_path: Path) -> None:
    """`--input acp_adapter=<codex>` is present, before --no-upgrade-check."""
    plan = build_plan(
        repo=tmp_path,
        work_item_id="x-1",
        workflow_toml=tmp_path / "wf.toml",
        goal_file=tmp_path / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=tmp_path / "janitor-co",
    )
    argv = fabro_run_argv(plan=plan)
    assert "--input" in argv
    input_value = argv[argv.index("--input") + 1]
    assert input_value == f"acp_adapter={CODEX_IMPLEMENTER_ADAPTER}"
    assert CODEX_IMPLEMENTER_ADAPTER == "npx -y @zed-industries/codex-acp@0.16.0"
    # The routing input precedes --no-upgrade-check.
    assert argv.index("--input") < argv.index("--no-upgrade-check")


# ---------------------------------------------------------------------------
# read_host_codex_auth — the DIRECT host-file read
# ---------------------------------------------------------------------------


def test_read_host_codex_auth_returns_file_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With CODEX_HOME pointed at a tmp dir, the auth.json text is returned."""
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    _ = (tmp_path / "auth.json").write_text(_FAKE_SNAPSHOT, encoding="utf-8")
    assert read_host_codex_auth() == _FAKE_SNAPSHOT


def test_read_host_codex_auth_returns_none_when_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing auth.json reads as None (never raises, never touches ~/.codex)."""
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "empty"))
    assert read_host_codex_auth() is None


# ---------------------------------------------------------------------------
# project_codex_auth — missing / stale / fresh
# ---------------------------------------------------------------------------


def test_project_codex_auth_refuses_when_host_credential_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing host credential refuses with an actionable `codex login` message."""
    monkeypatch.setattr(_dispatcher_codex_auth, "read_host_codex_auth", lambda: None)
    result = project_codex_auth(now_epoch=1_000_000)
    assert isinstance(result, CodexProjectionRefusal)
    assert "codex login" in result.message


def test_project_codex_auth_refuses_when_credential_is_stale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A too-short-lived credential refuses with the renewal message (Scenario 19)."""
    now = 1_000_000
    # An access token whose exp is in the past relative to `now` cannot
    # outlive the run budget plus margin, so the freshness gate refuses.
    monkeypatch.setattr(
        _dispatcher_codex_auth, "read_host_codex_auth", lambda: _auth_json_with_exp(exp=now - 10)
    )
    result = project_codex_auth(now_epoch=now)
    assert isinstance(result, CodexProjectionRefusal)
    assert "codex login" in result.message


def test_project_codex_auth_projects_snapshot_when_fresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fresh credential projects the non-rotatable snapshot (Scenario 18)."""
    now = 1_000_000
    far_future = now + 100 * 365 * 24 * 3600
    monkeypatch.setattr(
        _dispatcher_codex_auth, "read_host_codex_auth", lambda: _auth_json_with_exp(exp=far_future)
    )
    result = project_codex_auth(now_epoch=now)
    assert isinstance(result, str)
    projected = json.loads(result)
    # The refresh token was replaced with the inert sentinel; the real
    # host refresh token never reaches the snapshot.
    assert projected["tokens"]["refresh_token"] != "host-refresh-token"
    assert "host-refresh-token" not in result


def test_project_codex_auth_accepts_token_outliving_a_realistic_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A credential good for hours past any realistic run is NOT refused.

    Regression for the freshness gate wiring the 15h `_FABRO_TIMEOUT_SECONDS`
    subprocess CEILING in as the run budget: that demanded the token outlive
    ~16h (15h + the 1h margin), so it refused nearly every host Codex token
    (minted ~18h, dropping below 16h within ~2h) even though a real dispatch
    runs ~30-45min. The gate must size against a REALISTIC run budget, so a
    token with 6h of life left — far more than any real run needs — projects
    the snapshot (Scenario 18) instead of refusing it (Scenario 19).
    """
    now = 1_000_000
    six_hours = 6 * 3600
    monkeypatch.setattr(
        _dispatcher_codex_auth,
        "read_host_codex_auth",
        lambda: _auth_json_with_exp(exp=now + six_hours),
    )
    result = project_codex_auth(now_epoch=now)
    assert isinstance(result, str)


# ---------------------------------------------------------------------------
# materialize_overlay — the wired codex projection
# ---------------------------------------------------------------------------


def test_materialize_overlay_refuses_on_stale_host_credential(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stale host credential refuses the overlay at the codex-projection step."""
    committed = tmp_path / "workflow.toml"
    _ = committed.write_text(_COMMITTED_WORKFLOW_TOML, encoding="utf-8")
    overlay = tmp_path / "overlay.toml"
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", _FAKE_TOKEN)
    monkeypatch.setattr(
        _dispatcher_sibling_clones, "fetch_fleet_manifest_text", lambda: _FLEET_MANIFEST_TEXT
    )
    # Far-future clock makes any real-world `exp` look stale.
    far_future = 32_000_000_000
    monkeypatch.setattr(_dispatcher_credentials.time, "time", lambda: far_future)
    monkeypatch.setattr(
        _dispatcher_codex_auth,
        "read_host_codex_auth",
        lambda: _auth_json_with_exp(exp=1_700_000_000),
    )
    error = materialize_overlay(
        committed=committed,
        overlay=overlay,
        repo=tmp_path / "repo",
        work_item_id="wi-1",
        dispatch_id="disp-1",
        token=lambda: _FAKE_GITHUB_TOKEN,
    )
    assert error is not None
    assert "codex login" in error
    assert not overlay.exists()


def test_materialize_overlay_refuses_on_missing_host_credential(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing host credential refuses the overlay (names `codex login`)."""
    committed = tmp_path / "workflow.toml"
    _ = committed.write_text(_COMMITTED_WORKFLOW_TOML, encoding="utf-8")
    overlay = tmp_path / "overlay.toml"
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", _FAKE_TOKEN)
    monkeypatch.setattr(
        _dispatcher_sibling_clones, "fetch_fleet_manifest_text", lambda: _FLEET_MANIFEST_TEXT
    )
    monkeypatch.setattr(_dispatcher_codex_auth, "read_host_codex_auth", lambda: None)
    error = materialize_overlay(
        committed=committed,
        overlay=overlay,
        repo=tmp_path / "repo",
        work_item_id="wi-1",
        dispatch_id="disp-1",
        token=lambda: _FAKE_GITHUB_TOKEN,
    )
    assert error is not None
    assert "codex login" in error
    assert not overlay.exists()


def test_materialize_overlay_writes_codex_projection_when_fresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fresh host credential writes an overlay carrying the codex projection."""
    committed = tmp_path / "workflow.toml"
    _ = committed.write_text(_COMMITTED_WORKFLOW_TOML, encoding="utf-8")
    overlay = tmp_path / "overlay.toml"
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", _FAKE_TOKEN)
    monkeypatch.setattr(
        _dispatcher_sibling_clones, "fetch_fleet_manifest_text", lambda: _FLEET_MANIFEST_TEXT
    )
    now = 1_700_000_000
    far_future = now + 100 * 365 * 24 * 3600
    monkeypatch.setattr(_dispatcher_credentials.time, "time", lambda: now)
    monkeypatch.setattr(
        _dispatcher_codex_auth, "read_host_codex_auth", lambda: _auth_json_with_exp(exp=far_future)
    )
    error = materialize_overlay(
        committed=committed,
        overlay=overlay,
        repo=tmp_path / "repo",
        work_item_id="wi-1",
        dispatch_id="disp-1",
        token=lambda: _FAKE_GITHUB_TOKEN,
    )
    assert error is None
    rendered = overlay.read_text(encoding="utf-8")
    assert 'CODEX_HOME = "/workspace/.codex"' in rendered
    assert "CODEX_AUTH_JSON = " in rendered
    assert "[[run.prepare.steps]]" in rendered
    # The overlay stays mode-600 (the run-scoped credential projection).
    assert stat.S_IMODE(overlay.stat().st_mode) == 0o600
