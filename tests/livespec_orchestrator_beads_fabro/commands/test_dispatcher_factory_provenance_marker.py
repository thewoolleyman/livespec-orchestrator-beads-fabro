"""Tests for the factory-provenance marker the Dispatcher injects per sandbox.

Wave 2 R1, the orchestrator half of the hermetic factory-provenance commit
gate (work-item bd-ib-dosmpm). Every Fabro sandbox must DECLARE that its
clone was provisioned by the factory, so the dev-tooling commit gate that
lands next can refuse a hand-cranked product-`.py` commit on a host worktree
while passing an identical commit made inside a dispatch.

Two properties are load-bearing and are asserted separately here:

- The declaration is injected by the DISPATCHER OVERLAY, not by any
  committed `workflow.toml`. `workflow.toml` has per-repo forks (the console
  fork, the groom variant, the homelab/openbrain adopter forks), so a step
  written into one fork covers one consumer; the overlay covers every
  dispatch regardless of which fork it selects. The fixture config below
  therefore carries no marker of its own, and the rendered overlay does.
- The declared value is the PRE-LAUNCH `dispatch_id`, never the Fabro run
  id. The overlay is materialized BEFORE `fabro run` is invoked, so no Fabro
  run id exists yet at the point a prepare step could read one.
"""

from __future__ import annotations

import base64
import json
from inspect import signature
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_codex_auth,
    _dispatcher_credentials,
    _dispatcher_sibling_clones,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credentials import (
    materialize_overlay,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_git_author import GitAuthor
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import (
    render_run_config_overlay,
)

# The git-config key the sandbox declares its factory provenance under. Spelled
# literally here rather than imported from the module under test: a test that
# reads the name from the implementation cannot detect the name changing, and
# the dev-tooling hook gate reads this exact string.
_MARKER = "livespec.factoryRunId"
_GIT_AUTHOR = GitAuthor(name="Operator", email="operator@example.com")

# A committed workflow config with the canonical [workflow] graph + the
# [run.environment] id the overlay rewrites/targets (mirrors the shape the
# other overlay tests use). It declares NO marker step of its own.
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
# timeout plus the run-level stall watchdog.
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

# A canned fleet manifest so `resolve_sibling_clones` (which runs inside
# `materialize_overlay`) never shells out to a real `gh api`.
_FLEET_MANIFEST_TEXT = (
    "{\n"
    '  "owner": "thewoolleyman",\n'
    '  "members": [{ "repo": "livespec", "class": "core" }]\n'
    "}\n"
)

# Bound to locals before passing as `token=` / `github_token=` so ruff's S106
# (hardcoded password) does not flag the literals.
_FAKE_TOKEN = "test-oauth-token"
_FAKE_GITHUB_TOKEN = "test-github-token"


def _auth_json_with_exp(*, exp: int) -> str:
    """Build a fake Codex auth.json whose access-token JWT carries `exp`."""
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    access_token = f"header.{payload}.sig"
    return json.dumps(
        {
            "auth_mode": "chatgpt",
            "tokens": {"access_token": access_token, "refresh_token": "host-refresh-token"},
        }
    )


def _marker_step_line(*, dispatch_id: str) -> str:
    """The rendered `script = ...` line a conforming marker step carries."""
    return f"script = {json.dumps(f'git config {_MARKER} {dispatch_id}')}"


def test_render_run_config_overlay_injects_the_factory_run_id_marker(tmp_path: Path) -> None:
    """The overlay appends a `[[run.prepare.steps]]` block declaring the marker."""
    assert "dispatch_id" in signature(render_run_config_overlay).parameters
    assert _MARKER not in _COMMITTED_WORKFLOW_TOML
    rendered = render_run_config_overlay(
        committed_text=_COMMITTED_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=_FAKE_TOKEN,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=None,
        dispatch_id="disp-1",
    )
    assert rendered is not None
    # The whole block, not merely the string: a marker that did not ride an
    # appended prepare step would never run inside the sandbox.
    assert f"[[run.prepare.steps]]\n{_marker_step_line(dispatch_id='disp-1')}\n" in rendered


def test_render_run_config_overlay_without_a_dispatch_id_declares_no_marker(
    tmp_path: Path,
) -> None:
    """A caller that materialized no dispatch id renders no marker step.

    The production path always carries one; this arm keeps the projection
    honest for a direct caller rather than declaring an empty provenance.
    """
    rendered = render_run_config_overlay(
        committed_text=_COMMITTED_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=_FAKE_TOKEN,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=None,
    )
    assert rendered is not None
    assert _MARKER not in rendered


def test_materialize_overlay_declares_the_pre_launch_dispatch_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The written overlay carries the dispatch id the Dispatcher minted pre-launch.

    `materialize_overlay` runs before `fabro run` is invoked, so the id it
    projects here is necessarily the pre-launch `dispatch_id` — the Fabro run
    id does not exist until the launch this file is an input to.
    """
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
        dispatch_id="01M23CD51JNGY3R1AKN2WNP4WB",
        token=lambda: _FAKE_GITHUB_TOKEN,
        git_author=_GIT_AUTHOR,
    )
    assert error is None
    rendered = overlay.read_text(encoding="utf-8")
    assert _marker_step_line(dispatch_id="01M23CD51JNGY3R1AKN2WNP4WB") in rendered
