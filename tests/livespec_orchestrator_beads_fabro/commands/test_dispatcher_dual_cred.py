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

import argparse
import base64
import json
import os
import stat
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_codex_auth,
    _dispatcher_credentials,
    _dispatcher_loop,
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    CODEX_IMPLEMENTER_ADAPTER,
    build_plan,
    fabro_run_argv,
    render_run_config_overlay,
)
from livespec_orchestrator_beads_fabro.errors import BeadsCommandError
from livespec_orchestrator_beads_fabro.types import WorkItem

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


def test_render_overlay_contains_the_refresh_sentinel_to_a_closed_loopback_port(
    tmp_path: Path,
) -> None:
    """The projection MUST also pin codex-core's refresh/revoke endpoint in-container.

    The projected snapshot carries a deliberately non-rotatable
    `tokens.refresh_token` sentinel. codex-core POSTs that refresh_token to its
    refresh endpoint on ANY HTTP 401 WITHOUT checking whether the access token
    actually expired, so the freshness gate does not protect it: a spurious 401,
    or container clock skew (codex compares the JWT `exp` against the CONTAINER
    clock, while the gate evaluates on the HOST clock), sends the sentinel to
    OpenAI. codex-core reads the endpoint from CODEX_REFRESH_TOKEN_URL_OVERRIDE
    when set, so pinning it at a closed loopback port keeps the sentinel INSIDE
    the container -- the POST fails locally instead of presenting a bogus
    credential to the auth service.
    """
    rendered = render_run_config_overlay(
        committed_text=_COMMITTED_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=_FAKE_TOKEN,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=None,
        codex_auth_snapshot=_FAKE_SNAPSHOT,
    )
    assert rendered is not None
    _, env_table = rendered.split("[environments.livespec-ci.env]", 1)
    override_line = next(
        (
            line
            for line in env_table.splitlines()
            if line.startswith("CODEX_REFRESH_TOKEN_URL_OVERRIDE = ")
        ),
        None,
    )
    assert override_line is not None, "the refresh/revoke endpoint override MUST be projected"
    endpoint = json.loads(override_line[len("CODEX_REFRESH_TOKEN_URL_OVERRIDE = ") :])
    # Loopback: unreachable from inside the sandbox, so the sentinel cannot
    # egress. Never the real auth service.
    assert endpoint.startswith("http://127.0.0.1:")
    assert "openai.com" not in endpoint


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
    assert "CODEX_REFRESH_TOKEN_URL_OVERRIDE" not in rendered
    assert "auth.json" not in rendered


def test_render_overlay_projects_tmux_tmpdir_into_sandbox_env(tmp_path: Path) -> None:
    rendered = render_run_config_overlay(
        committed_text=_COMMITTED_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=_FAKE_TOKEN,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=None,
    )
    assert rendered is not None
    assert "[environments.livespec-ci.env]\n" in rendered
    assert 'TMUX_TMPDIR = "/workspace/.tmux"\n' in rendered


def test_tmux_probe_with_sandbox_tmpdir_leaves_host_default_socket_dir(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    tmux = fake_bin / "tmux"
    tmux.write_text(
        "#!/usr/bin/env python3\n"
        "import os\n"
        "import pathlib\n"
        "import sys\n"
        "sock = pathlib.Path(os.environ['TMUX_TMPDIR']) / f'tmux-{os.getuid()}' / 'default'\n"
        "if sys.argv[1:3] == ['new-session', '-d']:\n"
        "    sock.parent.mkdir(parents=True, exist_ok=True)\n"
        "    sock.write_text('sandbox', encoding='utf-8')\n"
        "elif sys.argv[1:] == ['kill-server']:\n"
        "    sock.unlink(missing_ok=True)\n"
        "else:\n"
        "    raise SystemExit(2)\n",
        encoding="utf-8",
    )
    tmux.chmod(0o755)
    assert _socket_dir_listing(path=tmp_path / "absent-host-default") == ()
    host_default = tmp_path / "host-default" / f"tmux-{os.getuid()}"
    host_default.mkdir(parents=True)
    before = _socket_dir_listing(path=host_default)
    sandbox_tmpdir = tmp_path / "sandbox-tmux"
    sandbox_tmpdir.mkdir(mode=0o700)
    env = {
        **os.environ,
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "TMUX_TMPDIR": str(sandbox_tmpdir),
    }
    _ = subprocess.run(
        ["tmux", "new-session", "-d", "-s", "livespec-tmux-tmpdir-probe"],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )
    _ = subprocess.run(
        ["tmux", "kill-server"],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )
    assert _socket_dir_listing(path=host_default) == before


def _socket_dir_listing(*, path: Path) -> tuple[str, ...]:
    if not path.exists():
        return ()
    return tuple(sorted(child.name for child in path.iterdir()))


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
    input_values = [
        value for index, value in enumerate(argv[1:], start=1) if argv[index - 1] == "--input"
    ]
    assert input_values == [
        f"acp_adapter={CODEX_IMPLEMENTER_ADAPTER}",
        "review_fix_visit_cap=4",
        "merge_on_review_cap_outcome=__merge_on_review_cap_disabled__",
    ]
    assert CODEX_IMPLEMENTER_ADAPTER == "npx --no-install @zed-industries/codex-acp"
    # The routing inputs precede --no-upgrade-check.
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


def test_fabro_run_argv_routes_effective_review_cap_policy_inputs(tmp_path: Path) -> None:
    """Dispatcher policy values are rendered as Fabro workflow inputs."""
    plan = build_plan(
        repo=tmp_path,
        work_item_id="x-1",
        workflow_toml=tmp_path / "wf.toml",
        goal_file=tmp_path / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=tmp_path / "janitor-co",
        review_fix_cap=7,
        merge_on_review_cap=True,
    )
    argv = fabro_run_argv(plan=plan)
    input_values = [
        value for index, value in enumerate(argv[1:], start=1) if argv[index - 1] == "--input"
    ]
    assert input_values == [
        f"acp_adapter={CODEX_IMPLEMENTER_ADAPTER}",
        "review_fix_visit_cap=8",
        "merge_on_review_cap_outcome=succeeded",
    ]


def _policy_item() -> WorkItem:
    return WorkItem(
        id="x-1",
        type="feature",
        status="ready",
        title="Title",
        description="Description",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-01-01T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        spec_commitment_hint=None,
        acceptance_criteria=None,
        notes=None,
        admission_policy=None,
        acceptance_policy=None,
        blocked_reason=None,
    )


def _store_config_stub(*, repo: Path) -> object:
    _ = repo
    return object()


def test_read_dispatch_labels_returns_raw_string_labels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_dispatcher_credentials, "store_config", _store_config_stub)

    def show_issue(*, issue_id: str) -> dict[str, object]:
        _ = issue_id
        return {"labels": ["merge-on-review-cap:true", 7, "review-fix-cap:5"]}

    def make_client(*, config: object) -> SimpleNamespace:
        _ = config
        return SimpleNamespace(show_issue=show_issue)

    monkeypatch.setattr(_dispatcher_credentials, "make_beads_client", make_client)
    assert _dispatcher_credentials.read_dispatch_labels(repo=tmp_path, item=_policy_item()) == (
        "merge-on-review-cap:true",
        "review-fix-cap:5",
    )


def test_read_dispatch_labels_returns_refusal_on_beads_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_show(*, issue_id: str) -> dict[str, object]:
        _ = issue_id
        raise BeadsCommandError(command="bd show x-1", exit_code=1, stderr="boom")

    monkeypatch.setattr(_dispatcher_credentials, "store_config", _store_config_stub)

    def make_client(*, config: object) -> SimpleNamespace:
        _ = config
        return SimpleNamespace(show_issue=fail_show)

    monkeypatch.setattr(_dispatcher_credentials, "make_beads_client", make_client)
    result = _dispatcher_credentials.read_dispatch_labels(repo=tmp_path, item=_policy_item())
    assert isinstance(result, str)
    assert result.startswith("ledger label read failed for x-1 (BeadsCommandError:")


def test_read_dispatch_labels_treats_missing_labels_as_no_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_dispatcher_credentials, "store_config", _store_config_stub)

    def show_issue(*, issue_id: str) -> dict[str, object]:
        _ = issue_id
        return {}

    def make_client(*, config: object) -> SimpleNamespace:
        _ = config
        return SimpleNamespace(show_issue=show_issue)

    monkeypatch.setattr(_dispatcher_credentials, "make_beads_client", make_client)
    assert _dispatcher_credentials.read_dispatch_labels(repo=tmp_path, item=_policy_item()) == ()


def test_dispatch_one_refuses_when_policy_labels_cannot_be_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def label_failure(*, repo: Path, item: WorkItem) -> str:
        _ = (repo, item)
        return "label backend unavailable"

    monkeypatch.setattr(_dispatcher_loop, "read_dispatch_labels", label_failure)
    outcome = _dispatcher_loop.dispatch_one(
        args=argparse.Namespace(fabro_bin="fabro"),
        repo=tmp_path,
        item=_policy_item(),
        journal=JournalFile(path=tmp_path / "journal.jsonl"),
        janitor=None,
    )
    assert outcome.status == "failed"
    assert outcome.stage == "ledger-labels"
    assert outcome.detail == "label backend unavailable"
    assert '"stage": "outcome"' in (tmp_path / "journal.jsonl").read_text(encoding="utf-8")


def test_dispatch_one_releases_dispatch_lock_when_locked_body_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    item = _policy_item()
    lock_path = tmp_path / "tmp" / f"fabro-dispatch-{item.id}.lock"

    def label_failure(*, repo: Path, item: WorkItem) -> str:
        _ = repo
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
        assert payload["work_item_id"] == item.id
        assert payload["dispatch_id"] == "dispatch-lock-test"
        raise RuntimeError("label backend crashed")

    monkeypatch.setattr(_dispatcher_loop, "run_id", lambda: "dispatch-lock-test")
    monkeypatch.setattr(_dispatcher_loop, "read_dispatch_labels", label_failure)

    with pytest.raises(RuntimeError, match="label backend crashed"):
        _dispatcher_loop.dispatch_one(
            args=argparse.Namespace(fabro_bin="fabro"),
            repo=tmp_path,
            item=item,
            journal=JournalFile(path=tmp_path / "journal.jsonl"),
            janitor=None,
        )

    assert not lock_path.exists()
