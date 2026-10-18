"""The native secret channel requires only the credentials this dispatch projects.

The FIRST Definition-of-Done assertion of work-item bd-ib-rcymxo: a dispatch to a
factory declaring the native secret channel whose resolved routing launches NO
Codex node passes the run-configuration overlay stage and stores the Anthropic
and GitHub credentials in the factory vault without a `CODEX_AUTH_JSON` line.

The two decisions this binds together are owned by two modules, and the defect
was that neither of them knew what the other had decided.
`_dispatcher_codex_overlay_leg` projects no Codex credential at all for a
dispatch that routes no node to the `codex-acp` agent -- "routing decides whether
there is a credential to project" -- so such a bundle carries no
`CODEX_AUTH_JSON` line. The channel's required-family list named that family
unconditionally, so every native-channel dispatch without a Codex node was
refused before launch, naming a credential the dispatch was right not to carry.
Measured 2026-10-18 12:01:55Z: canary dispatch 3239702d96d246b28af019dd63dc151f
to factory `petri` failed at stage `run-config-overlay` with "the
run-configuration bundle carries no line for CODEX_AUTH_JSON", no Fabro run was
created, and the item was released to `ready`.

The routing is DECLARED here rather than resolved, exactly as the sibling
projection test declares it in the opposite direction: these cases are about
which families the transport demands of a bundle, and the routing is the input
that decides it, so a case whose routing came out of a fixture repository's
adapter resolution would be asserting something else.

The host holds NO Codex credential, which is the sharpest available form of the
claim rather than a convenience: an Anthropic-only dispatch does not consult one,
so a case that supplied a healthy one could not tell "this dispatch needs no
Codex credential" from "this dispatch was handed a good one". It is also what a
real all-Claude operator host looks like.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_codex_auth,
    _dispatcher_credentials,
    _dispatcher_sibling_clones,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_secret_channel as channel_module,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_routing import CodexRouting
from livespec_orchestrator_beads_fabro.commands._dispatcher_credentials import (
    materialize_overlay,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_git_author import GitAuthor
from livespec_orchestrator_beads_fabro.commands._dispatcher_secret_channel import (
    SECRET_CHANNEL_NATIVE_SECRETS,
    VaultSecret,
)

_FACTORY = "petri"
_GIT_AUTHOR = GitAuthor(name="Operator", email="operator@example.com")
_REVIEW_FIX_VISIT_CAP = 4
_DISPATCH_SCOPE = "01M4G085KXTH03ME7KDARYG8G8"

# Opaque non-secret placeholders, bound to locals so ruff's hardcoded-credential
# rules do not read the literals at the call sites as real ones.
_FAKE_TOKEN = "anthropic-only-oauth-placeholder"
_FAKE_GITHUB_TOKEN = "anthropic-only-github-placeholder"

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

_ANTHROPIC_ONLY_ROUTING = CodexRouting(
    routes_codex=False,
    detail="every resolved ACP candidate names the claude-acp agent",
)


@dataclass(kw_only=True)
class _RecordingSink:
    """A vault that records what it was asked to store, and never refuses."""

    stored: dict[str, str] = field(default_factory=dict)

    def set(self, *, secret: VaultSecret) -> str | None:
        self.stored[secret.secret_name] = secret.value
        return None


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


def _materialize(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    repo: Path,
    sink: _RecordingSink,
) -> tuple[str | None, Path]:
    """Run the production materializer for an ANTHROPIC-ONLY dispatch."""
    committed = tmp_path / "workflow.toml"
    _ = committed.write_text(_COMMITTED_WORKFLOW_TOML, encoding="utf-8")
    _ = (committed.parent / "workflow.fabro").write_text(_MINIMAL_GRAPH, encoding="utf-8")
    overlay = tmp_path / "overlay.toml"
    monkeypatch.setenv(_ANTHROPIC_ENV, _FAKE_TOKEN)
    monkeypatch.setattr(
        _dispatcher_sibling_clones, "fetch_fleet_manifest_text", lambda: _FLEET_MANIFEST_TEXT
    )
    monkeypatch.setattr(_dispatcher_credentials.time, "time", lambda: 1_700_000_000)
    # A host holding NO Codex credential at all -- see the module docstring on why
    # that is the sharper fixture, and note the hermeticity it also buys: without
    # this the read would reach the real `$CODEX_HOME` of whatever host the suite
    # runs on.
    monkeypatch.setattr(_dispatcher_codex_auth, "read_host_codex_auth", lambda: None)
    monkeypatch.setattr(
        _dispatcher_credentials,
        "codex_routing_for_dispatch",
        lambda **_kwargs: _ANTHROPIC_ONLY_ROUTING,
    )
    error = materialize_overlay(
        committed=committed,
        overlay=overlay,
        repo=repo,
        work_item_id="wi-anthropic-only",
        dispatch_id=_DISPATCH_SCOPE,
        token=lambda: _FAKE_GITHUB_TOKEN,
        git_author=_GIT_AUTHOR,
        review_fix_visit_cap=_REVIEW_FIX_VISIT_CAP,
        factory_name=_FACTORY,
        secret_sink=sink,
    )
    return error, overlay


def test_an_anthropic_only_dispatch_passes_the_overlay_stage_and_stores_two_families(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The stage passes, both projected families are routed, and Codex is absent.

    Every clause of the assertion is read off the same materialization: the
    stage's own verdict, the two references in the written bundle, the two values
    in the vault, and the absence of any `CODEX_AUTH_JSON` line. Asserting the
    verdict alone would pass for a build that routed nothing, and asserting the
    references alone would pass for a build that left the values inline.
    """
    repo = _native_factory_repo(tmp_path=tmp_path)
    sink = _RecordingSink()
    error, overlay = _materialize(tmp_path=tmp_path, monkeypatch=monkeypatch, repo=repo, sink=sink)
    assert error is None
    rendered = overlay.read_text(encoding="utf-8")
    for env_name in (_ANTHROPIC_ENV, _GITHUB_ENV):
        secret_name = channel_module.vault_secret_name(env_name=env_name)
        reference = channel_module.secret_reference(secret_name=secret_name)
        assert f"{env_name} = {json.dumps(reference)}\n" in rendered
        assert secret_name in sink.stored
    assert sink.stored[channel_module.vault_secret_name(env_name=_GITHUB_ENV)] == (
        _FAKE_GITHUB_TOKEN
    )
    assert sink.stored[channel_module.vault_secret_name(env_name=_ANTHROPIC_ENV)] == _FAKE_TOKEN
    assert f"{_CODEX_ENV} = " not in rendered
    assert channel_module.vault_secret_name(env_name=_CODEX_ENV) not in sink.stored
