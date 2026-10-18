"""A Codex-routed bundle missing its Codex credential is still refused.

The SECOND Definition-of-Done assertion of work-item bd-ib-rcymxo: a dispatch to
a factory declaring the native secret channel whose resolved routing LAUNCHES a
Codex node and whose bundle carries no `CODEX_AUTH_JSON` line is refused at the
run-configuration overlay stage with a message naming `CODEX_AUTH_JSON`.

THIS IS A CONTROL, in the sense `tests/CLAUDE.md` already uses for the
provider-exhaustion pair: it pins a CONSEQUENCE of the routing scoping rather
than behaviour of its own, so it could not have failed before that scoping
landed -- the family was required of every bundle, so this refusal held for
every routing including the one that does not need it. It is committed on a
suite-green leg for that reason. Without it, the scoping has no guard in the
direction it must NOT have relaxed, and the two ways a build can be wrong here
are indistinguishable at every other surface: a required family and a silently
dropped one both produce a bundle the dispatch is perfectly happy to launch.

WHY THE CONDITION IS STAGED AT THE RENDERER rather than produced by the dispatch
path. The refusal exists for a DISAGREEMENT between two code paths -- the
projection that renders credential lines and the list of names the transport
routes -- so there is deliberately no healthy dispatch that reaches it: a
Codex-routed dispatch whose host credential graded clean renders the line, and
one whose credential did not grade is refused earlier by the projection leg. The
renderer is therefore stubbed, which is what puts the bundle and the routing in
the exact disagreement the refusal is written to catch.

The PASSING case is the load-bearing half of the pair. Without it, a build that
refused every Codex-routed dispatch -- the opposite defect, and the one the
scoping could plausibly have introduced -- would satisfy the refusal case
exactly as well as a correct build does.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_codex_auth,
    _dispatcher_credentials,
    _dispatcher_sibling_clones,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_routing import CodexRouting
from livespec_orchestrator_beads_fabro.commands._dispatcher_credentials import (
    materialize_overlay,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_git_author import GitAuthor
from livespec_orchestrator_beads_fabro.commands._dispatcher_secret_channel import (
    SECRET_CHANNEL_NATIVE_SECRETS,
    VaultSecret,
    vault_secret_name,
)

_FACTORY = "petri"
_GIT_AUTHOR = GitAuthor(name="Operator", email="operator@example.com")
_REVIEW_FIX_VISIT_CAP = 4
_DISPATCH_SCOPE = "01M4G085KXTH03ME7KDARYG8G8"

# Opaque non-secret placeholders, bound to locals so ruff's hardcoded-credential
# rules do not read the literals at the call sites as real ones.
_FAKE_TOKEN = "codex-routed-oauth-placeholder"
_FAKE_GITHUB_TOKEN = "codex-routed-github-placeholder"
_FAKE_CODEX_SNAPSHOT = '{"tokens": {"access_token": "codex-routed-placeholder"}}'

_ANTHROPIC_ENV = "CLAUDE_CODE_OAUTH_TOKEN"
_GITHUB_ENV = "GITHUB_TOKEN"
_CODEX_ENV = "CODEX_AUTH_JSON"

_COMMITTED_WORKFLOW_TOML = (
    "_version = 1\n"
    "\n"
    "[workflow]\n"
    'graph = "workflow.fabro"\n'
    "\n"
    "[run.environment]\n"
    'id = "livespec-ci"\n'
)
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
_FLEET_MANIFEST_TEXT = json.dumps({"owner": "thewoolleyman", "fleet": [{"repo": "livespec"}]})

_CODEX_ROUTED_ROUTING = CodexRouting(
    routes_codex=True,
    detail=("resolved ACP candidate keys naming the codex-acp agent: codex-acp/openai/gpt-5.1"),
)


@dataclass(kw_only=True)
class _RecordingSink:
    """A vault that records what it was asked to store, and never refuses."""

    stored: dict[str, str] = field(default_factory=dict)

    def set(self, *, secret: VaultSecret) -> str | None:
        self.stored[secret.secret_name] = secret.value
        return None


def _bundle(*, carries_codex: bool) -> str:
    """One rendered bundle, with or without the Codex credential line."""
    codex_line = f"{_CODEX_ENV} = {json.dumps(_FAKE_CODEX_SNAPSHOT)}\n" if carries_codex else ""
    return (
        '[workflow]\ngraph = "/abs/workflow.fabro"\n\n'
        '[run.environment]\nid = "livespec-ci"\n\n'
        "[environments.livespec-ci.env]\n"
        f"{_ANTHROPIC_ENV} = {json.dumps(_FAKE_TOKEN)}\n"
        f"{_GITHUB_ENV} = {json.dumps(_FAKE_GITHUB_TOKEN)}\n"
        f"{codex_line}"
    )


def _native_factory_repo(*, tmp_path: Path) -> Path:
    """A governed repository whose `petri` factory declares the native channel."""
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    config = {
        "livespec-orchestrator-beads-fabro": {
            "dispatcher": {
                "factories": {
                    _FACTORY: {
                        "server": "https://gmktec-xubuntu.example.invalid:32276",
                        "secret_channel": SECRET_CHANNEL_NATIVE_SECRETS,
                    }
                }
            },
        }
    }
    _ = (repo / ".livespec.jsonc").write_text(json.dumps(config), encoding="utf-8")
    return repo


def _access_token(*, exp: int) -> str:
    """A fake Codex access token whose JWT payload carries `exp`."""
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return f"header.{payload}.sig"


def _materialize(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    carries_codex: bool,
    sink: _RecordingSink,
) -> tuple[str | None, Path]:
    """Materialize a CODEX-ROUTED dispatch over a bundle staged at the renderer."""
    repo = _native_factory_repo(tmp_path=tmp_path)
    committed = tmp_path / "workflow.toml"
    _ = committed.write_text(_COMMITTED_WORKFLOW_TOML, encoding="utf-8")
    _ = (committed.parent / "workflow.fabro").write_text(_MINIMAL_GRAPH, encoding="utf-8")
    overlay = tmp_path / "overlay.toml"
    monkeypatch.setenv(_ANTHROPIC_ENV, _FAKE_TOKEN)
    monkeypatch.setattr(
        _dispatcher_sibling_clones, "fetch_fleet_manifest_text", lambda: _FLEET_MANIFEST_TEXT
    )
    now = 1_700_000_000
    monkeypatch.setattr(_dispatcher_credentials.time, "time", lambda: now)
    # A host credential with a century of lifetime, so the projection leg grades
    # it clean and the dispatch reaches the transport: this pair is about the
    # BUNDLE's families, and a freshness refusal would stop it earlier with a
    # message about `codex login`.
    monkeypatch.setattr(
        _dispatcher_codex_auth,
        "read_host_codex_auth",
        lambda: json.dumps(
            {
                "auth_mode": "chatgpt",
                "tokens": {
                    "access_token": _access_token(exp=now + 100 * 365 * 24 * 3600),
                    "refresh_token": "host-refresh",
                },
            }
        ),
    )
    monkeypatch.setattr(
        _dispatcher_credentials,
        "codex_routing_for_dispatch",
        lambda **_kwargs: _CODEX_ROUTED_ROUTING,
    )
    monkeypatch.setattr(
        _dispatcher_credentials,
        "render_run_config_overlay",
        lambda **_kwargs: _bundle(carries_codex=carries_codex),
    )
    error = materialize_overlay(
        committed=committed,
        overlay=overlay,
        repo=repo,
        work_item_id="wi-codex-routed",
        dispatch_id=_DISPATCH_SCOPE,
        token=lambda: _FAKE_GITHUB_TOKEN,
        git_author=_GIT_AUTHOR,
        review_fix_visit_cap=_REVIEW_FIX_VISIT_CAP,
        factory_name=_FACTORY,
        secret_sink=sink,
    )
    return error, overlay


def test_a_codex_routed_bundle_without_the_codex_credential_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The refusal names the family, writes no overlay, and stores nothing.

    All three are read off the one materialization. The message is what points
    the operator at the dropped projection; the absent file is what keeps the
    dispatch path from launching a bundle whose credentials are on neither
    transport; and the empty vault is what keeps a refused dispatch from seeding
    entries a later launch would authenticate against.
    """
    sink = _RecordingSink()
    error, overlay = _materialize(
        tmp_path=tmp_path, monkeypatch=monkeypatch, carries_codex=False, sink=sink
    )
    assert error is not None
    assert _CODEX_ENV in error
    assert not overlay.exists()
    assert sink.stored == {}


def test_the_same_codex_routed_dispatch_passes_once_the_bundle_carries_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The positive control: only the MISSING line refuses, not the routing.

    Identical in every input but the one line, so a build that refused every
    Codex-routed dispatch fails here instead of satisfying the case above by
    accident.
    """
    sink = _RecordingSink()
    error, overlay = _materialize(
        tmp_path=tmp_path, monkeypatch=monkeypatch, carries_codex=True, sink=sink
    )
    assert error is None
    assert overlay.exists()
    assert sink.stored[vault_secret_name(env_name=_CODEX_ENV)] == _FAKE_CODEX_SNAPSHOT
    assert _FAKE_CODEX_SNAPSHOT not in overlay.read_text(encoding="utf-8")
