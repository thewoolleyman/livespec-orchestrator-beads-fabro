"""Tests for the dispatch-time dual-credential projection (Slice B).

The Dispatcher reads the host Codex `auth.json`, freshness-gates it, and
projects a NON-rotatable snapshot into the sandbox at `$CODEX_HOME/auth.json`
alongside the existing Claude OAuth env, then flips the implementer nodes
to the Codex ACP adapter (scenarios.md Scenario 18 / Scenario 19). These
tests exercise the PURE overlay surface (`render_run_config_overlay`), the
Fabro port run inputs, and the host-read + projection helpers in `dispatcher`:
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
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_codex_auth,
    _dispatcher_credentials,
    _dispatcher_loop,
    _dispatcher_sibling_clones,
)
from livespec_orchestrator_beads_fabro.commands._codex_model_tiers import CodexModelTier
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_auth import (
    CodexProjectionRefusal,
    project_codex_auth,
    read_host_codex_auth,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credentials import (
    materialize_overlay,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    dispatch_fabro_run_inputs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_git_author import GitAuthor
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    CODEX_ADAPTER_BASE,
    CODEX_AGENT_MODE_READ_ONLY,
    CODEX_AGENT_MODE_WRITE,
    build_plan,
    codex_adapter,
    render_run_config_overlay,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroTarget
from livespec_orchestrator_beads_fabro.errors import BeadsCommandError
from livespec_orchestrator_beads_fabro.types import WorkItem

from tests.conftest import ResolveAcpNodes

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

# A minimal workflow graph for the payload materializer to render: one node
# timeout plus the run-level stall watchdog, which is the shape the literal-
# duration rewrite requires (commands/_dispatcher_graph_render.py).
_MINIMAL_GRAPH = (
    "digraph ImplementWorkItem {\n"
    "    graph [\n"
    '        stall_timeout="7200s"\n'
    "    ]\n"
    "\n"
    "    implement [\n"
    '        timeout="1800s"\n'
    "    ]\n"
    "}\n"
)

# Bound to locals before passing as `token=` / `github_token=` so ruff's
# S106 (hardcoded password) does not flag the literals.
_FAKE_TOKEN = "test-oauth-token"
_FAKE_GITHUB_TOKEN = "test-github-token"
_GIT_AUTHOR = GitAuthor(name="Operator", email="operator@example.com")

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
        ' && test -s \\"$CODEX_HOME/auth.json\\"'
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


def test_render_overlay_projects_the_codex_otel_config(tmp_path: Path) -> None:
    """A non-None `[otel]` body adds its prepare step + env line (work-item bd-ib-dbzp).

    Codex reads its OTLP exporters from `$CODEX_HOME/config.toml` and honors
    no `OTEL_*` variable, so without this file it resolves its trace exporter
    to None and exports no span — which is why no Codex token span ever
    reached the host receiver.
    """
    rendered = render_run_config_overlay(
        committed_text=_COMMITTED_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=_FAKE_TOKEN,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=None,
        codex_auth_snapshot=_FAKE_SNAPSHOT,
        codex_otel_config='[otel]\nenvironment = "livespec"\n',
    )
    assert rendered is not None
    prepare_region, env_table = rendered.split("[environments.livespec-ci.env]", 1)
    # Written before the agent nodes, and read back so an empty projection
    # aborts the run here rather than surfacing as telemetry absence later.
    assert (
        'printf %s \\"$CODEX_OTEL_CONFIG_TOML\\" > \\"$CODEX_HOME/config.toml\\"'
        ' && chmod 600 \\"$CODEX_HOME/config.toml\\"'
        ' && test -s \\"$CODEX_HOME/config.toml\\"'
    ) in prepare_region
    # The body round-trips through the env table (json.dumps single-lines it).
    otel_line = next(
        line for line in env_table.splitlines() if line.startswith("CODEX_OTEL_CONFIG_TOML = ")
    )
    assert json.loads(otel_line[len("CODEX_OTEL_CONFIG_TOML = ") :]) == (
        '[otel]\nenvironment = "livespec"\n'
    )


def test_render_overlay_omits_codex_otel_config_when_absent(tmp_path: Path) -> None:
    """No `[otel]` projection: neither the step nor the env line appears.

    The Claude-OAuth-only shape has no Codex node and no `$CODEX_HOME`, so
    writing a telemetry config there would be a step that cannot succeed.
    """
    rendered = render_run_config_overlay(
        committed_text=_COMMITTED_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=_FAKE_TOKEN,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=None,
    )
    assert rendered is not None
    assert "CODEX_OTEL_CONFIG_TOML" not in rendered
    assert "config.toml" not in rendered


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


@dataclass(kw_only=True)
class _FabroRunner:
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        self.calls.append(argv)
        return CommandResult(exit_code=0, stdout="", stderr="")


# ---------------------------------------------------------------------------
# FabroPort run inputs — the static Codex implementer-adapter routing
# ---------------------------------------------------------------------------


def test_fabro_port_run_routes_implementer_to_codex_adapter(
    tmp_path: Path, resolve_test_acp_nodes: ResolveAcpNodes
) -> None:
    """The resolved per-node adapters reach `--input`, before --no-upgrade-check."""
    plan = build_plan(
        repo=tmp_path,
        work_item_id="x-1",
        workflow_toml=tmp_path / "wf.toml",
        goal_file=tmp_path / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=tmp_path / "janitor-co",
        acp_nodes=resolve_test_acp_nodes(repo=tmp_path),
    )
    runner = _FabroRunner()
    _ = FabroPort(
        fabro_bin=plan.fabro_bin,
        target=FabroTarget(),
        runner=runner,
        cwd=plan.repo,
    ).run(
        workflow_toml=plan.workflow_toml,
        goal_file=plan.goal_file,
        inputs=dispatch_fabro_run_inputs(plan=plan),
        timeout_seconds=1,
    )
    argv = runner.calls[0]
    input_values = [
        value for index, value in enumerate(argv[1:], start=1) if argv[index - 1] == "--input"
    ]
    # `tmp_path` carries no .livespec.jsonc, so implementation work uses the
    # fleet's Claude Opus 5 default while the PR node takes the Claude Haiku
    # publish default (v107) — neither class is a Codex adapter absent a pin.
    claude_opus_5 = (
        "ANTHROPIC_MODEL=claude-opus-5 CLAUDE_CODE_EFFORT_LEVEL=high "
        "npx -y @agentclientprotocol/claude-agent-acp"
    )
    claude_haiku_pr = (
        "ANTHROPIC_MODEL=claude-haiku-4-5 CLAUDE_CODE_EFFORT_LEVEL=high "
        "npx -y @agentclientprotocol/claude-agent-acp"
    )
    assert input_values == [
        "disposition_adapter=npx -y @agentclientprotocol/claude-agent-acp",
        f"fix_adapter={claude_opus_5}",
        f"implement_adapter={claude_opus_5}",
        f"pr_adapter={claude_haiku_pr}",
        "review_adapter=npx -y @agentclientprotocol/claude-agent-acp",
        f"review_fix_adapter={claude_opus_5}",
        "review_fix_visit_cap=4",
        "merge_on_review_cap_outcome=__merge_on_review_cap_disabled__",
        "merge_hold=false",
    ]
    expected_base = (
        'CODEX_CONFIG=\'{"approval_policy":"never","sandbox_mode":"danger-full-access"}\' '
        "INITIAL_AGENT_MODE=agent-full-access /opt/livespec/codex-acp/bin/codex-acp"
    )
    assert expected_base == CODEX_ADAPTER_BASE
    # Absent an explicit `codex_models.pr` table the publish node renders the
    # Claude Haiku adapter, not a Codex one. Keyed by input NAME rather than by
    # position: the pairs are rendered in sorted-name order.
    [pr_input] = [pair for pair in input_values if pair.startswith("pr_adapter=")]
    assert "codex-acp" not in pr_input
    assert "CODEX_CONFIG" not in pr_input
    assert pr_input.endswith(" npx -y @agentclientprotocol/claude-agent-acp")
    # No node emits a Codex adapter by default.
    assert not [pair for pair in input_values if "codex-acp" in pair]
    # The un-pinned Codex base is no longer emitted bare on any node.
    assert not [pair for pair in input_values if pair.endswith(f"={expected_base}")]
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
    _ = (committed.parent / "workflow.fabro").write_text(_MINIMAL_GRAPH, encoding="utf-8")
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
        git_author=_GIT_AUTHOR,
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
    _ = (committed.parent / "workflow.fabro").write_text(_MINIMAL_GRAPH, encoding="utf-8")
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
        git_author=_GIT_AUTHOR,
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
    _ = (committed.parent / "workflow.fabro").write_text(_MINIMAL_GRAPH, encoding="utf-8")
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
        git_author=_GIT_AUTHOR,
    )
    assert error is None
    rendered = overlay.read_text(encoding="utf-8")
    assert 'CODEX_HOME = "/workspace/.codex"' in rendered
    assert "CODEX_AUTH_JSON = " in rendered
    assert "[[run.prepare.steps]]" in rendered
    # The overlay stays mode-600 (the run-scoped credential projection).
    assert stat.S_IMODE(overlay.stat().st_mode) == 0o600


def test_materialize_overlay_refuses_a_config_without_a_run_environment_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A config carrying a graph but no `[run.environment] id` refuses here.

    The payload materializer upstream needs only `[workflow] graph`, so this
    half of the unusable-config surface is the overlay's alone to catch.
    """
    committed = tmp_path / "workflow.toml"
    _ = committed.write_text('[workflow]\ngraph = "workflow.fabro"\n', encoding="utf-8")
    _ = (committed.parent / "workflow.fabro").write_text(_MINIMAL_GRAPH, encoding="utf-8")
    overlay = tmp_path / "overlay.toml"
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", _FAKE_TOKEN)
    monkeypatch.setattr(
        _dispatcher_sibling_clones, "fetch_fleet_manifest_text", lambda: _FLEET_MANIFEST_TEXT
    )
    error = materialize_overlay(
        committed=committed,
        overlay=overlay,
        repo=tmp_path / "repo",
        work_item_id="wi-1",
        dispatch_id="disp-1",
        token=lambda: _FAKE_GITHUB_TOKEN,
        git_author=_GIT_AUTHOR,
    )
    assert error is not None
    assert "is not materializable" in error
    assert not overlay.exists()


def test_fabro_port_run_routes_effective_review_cap_policy_inputs(tmp_path: Path) -> None:
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
    runner = _FabroRunner()
    _ = FabroPort(
        fabro_bin=plan.fabro_bin,
        target=FabroTarget(),
        runner=runner,
        cwd=plan.repo,
    ).run(
        workflow_toml=plan.workflow_toml,
        goal_file=plan.goal_file,
        inputs=dispatch_fabro_run_inputs(plan=plan),
        timeout_seconds=1,
    )
    argv = runner.calls[0]
    input_values = [
        value for index, value in enumerate(argv[1:], start=1) if argv[index - 1] == "--input"
    ]
    # Scoped to the POLICY inputs this test is about. The adapter inputs are
    # absent because this plan carries no adapter resolution, and which
    # adapter each node runs is bound by the ACP-node tests rather than here.
    assert input_values == [
        "review_fix_visit_cap=8",
        "merge_on_review_cap_outcome=succeeded",
        "merge_hold=false",
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


# ---------------------------------------------------------------------------
# codex_adapter — tier rendering, including the un-pinned opt-out
# ---------------------------------------------------------------------------


def test_codex_adapter_renders_the_base_command_for_an_unpinned_tier() -> None:
    """An empty-model tier is a true no-op: the base string, byte-for-byte.

    This is the `"model": ""` opt-out reaching the adapter. It has to render
    identically to the pre-pin command, otherwise "disable the pin" would
    quietly mean "pin to something else".
    """
    rendered = codex_adapter(tier=CodexModelTier(model="", reasoning_effort=""))
    assert rendered == CODEX_ADAPTER_BASE
    assert '"model"' not in rendered
    assert '"model_reasoning_effort"' not in rendered


def test_codex_adapter_renders_a_read_only_agent_mode_on_request() -> None:
    """The read-only agent mode is the ONLY thing it changes.

    A reviewer performs no writes, so it takes `read-only` where the
    implementer and publish classes take `agent-full-access`. Asserting the
    two renderings differ by exactly that substitution is the point: the agent
    mode must not disturb CODEX_CONFIG, the key order, or the command, and a
    test that only checked `read-only` was present could not tell.
    """
    tier = CodexModelTier(model="gpt-5.6-terra", reasoning_effort="xhigh")
    read_only = codex_adapter(tier=tier, agent_mode=CODEX_AGENT_MODE_READ_ONLY)
    write = codex_adapter(tier=tier, agent_mode=CODEX_AGENT_MODE_WRITE)

    assert "INITIAL_AGENT_MODE=read-only" in read_only
    assert read_only == write.replace(
        f"INITIAL_AGENT_MODE={CODEX_AGENT_MODE_WRITE}",
        f"INITIAL_AGENT_MODE={CODEX_AGENT_MODE_READ_ONLY}",
    )
    assert write == codex_adapter(tier=tier), "agent-full-access is the default"


def test_codex_adapter_appends_model_overrides_for_a_pinned_tier() -> None:
    """A pinned tier keeps the sandbox/approval posture and adds the model.

    This is the literal string contracts.md section "Codex ACP node model pins"
    spells out for the publish class, asserted whole rather than by fragments:
    the section's own stated control is that a reader can predict the adapter
    string from the specification alone and check it against `run_turn.command`.
    """
    rendered = codex_adapter(tier=CodexModelTier(model="gpt-5.4-mini", reasoning_effort="high"))
    assert rendered == (
        'CODEX_CONFIG=\'{"approval_policy":"never","model":"gpt-5.4-mini",'
        '"model_reasoning_effort":"high","sandbox_mode":"danger-full-access"}\' '
        "INITIAL_AGENT_MODE=agent-full-access /opt/livespec/codex-acp/bin/codex-acp"
    )
