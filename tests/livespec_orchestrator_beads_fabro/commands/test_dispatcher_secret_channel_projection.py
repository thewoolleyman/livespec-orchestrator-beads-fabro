"""Every required credential reaches the worker through the native secret channel.

The SECOND Definition-of-Done assertion of work-item bd-ib-4ipmub: the worker
resolves each required GitHub, Anthropic and OpenAI credential through the
native Fabro secret channel at execution time. Three things have to hold for
that to be true of a dispatch, and each is asserted below.

First, the factory has to SAY which transport its engine speaks. The pinned
0.254 engine resolves no reference at all, so the inline overlay stays the
default and a factory opts into the native channel by declaring it; a value this
build does not understand refuses rather than guessing, because guessing
`inline_overlay` on a Petri-era server is what persists a literal credential in
an immutable workflow version.

Second, all three families have to be ROUTED. The names are collected from the
rendered bundle, so a family whose projection rendered no line is a missing
credential rather than an absent option -- a `secrets.NAME` reference the worker
cannot resolve fails the run late and opaquely, while a refusal before launch
names the family.

Third, the values have to REACH THE VAULT. A reference is only a credential once
the server holds the value it names, so the routed secrets are pushed through a
    sink and the sink is asserted to have received each one under its stable
    vault key.

`SPECIFICATION/contracts.md` section "Proof credential projection" governs the
declared-proof-credential half: the transport is implementation-owned and a
change of transport MUST NOT change the declaration, so nothing here touches
what a repository declares -- the declaration is read exactly as before and the
rendered VALUE is what moves.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from inspect import signature
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
from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block
from livespec_orchestrator_beads_fabro.commands._dispatcher_credentials import (
    materialize_overlay,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_git_author import GitAuthor
from livespec_orchestrator_beads_fabro.commands._dispatcher_secret_channel import (
    SECRET_CHANNEL_INLINE_OVERLAY,
    SECRET_CHANNEL_NATIVE_SECRETS,
    VaultSecret,
)

_FACTORY = "hp-candidate"
_GIT_AUTHOR = GitAuthor(name="Operator", email="operator@example.com")
_REVIEW_FIX_VISIT_CAP = 4
_DISPATCH_SCOPE = "01M4G085KXTH03ME7KDARYG8G8"

# Opaque non-secret placeholders, bound to locals so ruff's hardcoded-credential
# rules do not read the literals at the call sites as real ones.
_FAKE_TOKEN = "projection-oauth-placeholder"
_FAKE_GITHUB_TOKEN = "projection-github-placeholder"

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
_FLEET_MANIFEST_TEXT = json.dumps(
    {"owner": "thewoolleyman", "fleet": [{"repo": "livespec"}]},
)

_EXPECTED_FAMILIES = {"CLAUDE_CODE_OAUTH_TOKEN", "CODEX_AUTH_JSON", "GITHUB_TOKEN"}


@dataclass(kw_only=True)
class _RecordingSink:
    """A vault that records what it was asked to store, and never refuses."""

    stored: dict[str, str] = field(default_factory=dict)

    def set(self, *, secret: VaultSecret) -> str | None:
        self.stored[secret.secret_name] = secret.value
        return None


def _auth_json_with_exp(*, exp: int) -> str:
    """A fake Codex auth.json whose access-token JWT carries `exp`."""
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return json.dumps(
        {
            "auth_mode": "chatgpt",
            "tokens": {"access_token": f"header.{payload}.sig", "refresh_token": "host-refresh"},
        }
    )


def _repo_declaring(*, tmp_path: Path, channel: str | None) -> Path:
    """A governed repository whose `hp-candidate` factory declares `channel`."""
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    factory: dict[str, str] = {"server": "https://hp-xubuntu.example.invalid:32278"}
    if channel is not None:
        factory["secret_channel"] = channel
    config = {
        "livespec-orchestrator-beads-fabro": {
            "dispatcher": {"factories": {_FACTORY: factory}},
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
    """Run the production materializer against a hermetic host environment."""
    committed = tmp_path / "workflow.toml"
    _ = committed.write_text(_COMMITTED_WORKFLOW_TOML, encoding="utf-8")
    _ = (committed.parent / "workflow.fabro").write_text(_MINIMAL_GRAPH, encoding="utf-8")
    overlay = tmp_path / "overlay.toml"
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", _FAKE_TOKEN)
    monkeypatch.setattr(
        _dispatcher_sibling_clones, "fetch_fleet_manifest_text", lambda: _FLEET_MANIFEST_TEXT
    )
    now = 1_700_000_000
    monkeypatch.setattr(_dispatcher_credentials.time, "time", lambda: now)
    monkeypatch.setattr(
        _dispatcher_codex_auth,
        "read_host_codex_auth",
        lambda: _auth_json_with_exp(exp=now + 100 * 365 * 24 * 3600),
    )
    error = materialize_overlay(
        committed=committed,
        overlay=overlay,
        repo=repo,
        work_item_id="wi-secret-channel",
        dispatch_id=_DISPATCH_SCOPE,
        token=lambda: _FAKE_GITHUB_TOKEN,
        git_author=_GIT_AUTHOR,
        review_fix_visit_cap=_REVIEW_FIX_VISIT_CAP,
        factory_name=_FACTORY,
        secret_sink=sink,
    )
    return error, overlay


def test_the_materializer_takes_the_factory_and_the_vault_it_stores_through() -> None:
    """The dispatch path can say WHICH factory it is launching at, and where to store.

    Asserted as a signature question because it is the precondition for every
    assertion below: without the factory name the materializer cannot read the
    declaration, and without the sink a routed reference would name a vault
    entry nothing ever wrote.
    """
    parameters = set(signature(materialize_overlay).parameters)
    assert {"factory_name", "secret_sink"} <= parameters


def test_required_families_are_named_and_complete() -> None:
    """The three required credential families, by the env name each arrives under."""
    required = set(getattr(channel_module, "REQUIRED_CREDENTIAL_ENV_NAMES", ()))
    assert required == _EXPECTED_FAMILIES


def test_an_undeclared_factory_keeps_the_inline_overlay(tmp_path: Path) -> None:
    """A factory that declares nothing runs the pinned engine, which has no vault."""
    repo = _repo_declaring(tmp_path=tmp_path, channel=None)
    block = dispatcher_block(cwd=repo)
    resolved = channel_module.resolve_secret_channel(block=block, factory=_FACTORY)
    assert resolved == SECRET_CHANNEL_INLINE_OVERLAY


@pytest.mark.parametrize(
    "block",
    [
        {},
        {"factories": []},
        {"factories": {}},
        {"factories": {_FACTORY: []}},
    ],
)
def test_an_absent_or_unstructured_factory_has_no_channel_declaration(
    block: dict[str, object],
) -> None:
    """Only an explicit channel value is graded by the channel resolver."""
    resolved = channel_module.resolve_secret_channel(block=block, factory=_FACTORY)
    assert resolved == SECRET_CHANNEL_INLINE_OVERLAY


def test_a_declared_native_factory_resolves_the_native_channel(tmp_path: Path) -> None:
    """The declaration is what opts a factory into the vault transport."""
    repo = _repo_declaring(tmp_path=tmp_path, channel=SECRET_CHANNEL_NATIVE_SECRETS)
    block = dispatcher_block(cwd=repo)
    resolved = channel_module.resolve_secret_channel(block=block, factory=_FACTORY)
    assert resolved == SECRET_CHANNEL_NATIVE_SECRETS


def test_an_unrecognised_declaration_refuses_rather_than_guessing(tmp_path: Path) -> None:
    """An unknown transport name cannot fall back to the inline one.

    Falling back would inline a literal credential into a workflow version a
    Petri-era server stores immutably -- the exposure this slice closes -- so the
    refusal names the key, the value read, and the transports this build speaks.
    """
    repo = _repo_declaring(tmp_path=tmp_path, channel="vault_v2")
    block = dispatcher_block(cwd=repo)
    refusal = channel_module.resolve_secret_channel(block=block, factory=_FACTORY)
    assert isinstance(refusal, channel_module.SecretChannelRefusal)
    assert "vault_v2" in refusal.message
    assert SECRET_CHANNEL_NATIVE_SECRETS in refusal.message


def test_a_missing_required_family_refuses_before_any_reference_is_rendered() -> None:
    """A bundle with no OpenAI credential line cannot be routed as if it had one."""
    bundle = (
        "[environments.sandbox.env]\n"
        f"CLAUDE_CODE_OAUTH_TOKEN = {json.dumps(_FAKE_TOKEN)}\n"
        f"GITHUB_TOKEN = {json.dumps(_FAKE_GITHUB_TOKEN)}\n"
    )
    refusal = channel_module.credential_env_names(overlay_text=bundle, optional=())
    assert isinstance(refusal, channel_module.SecretChannelRefusal)
    assert "CODEX_AUTH_JSON" in refusal.message


def test_an_optional_credential_is_routed_only_when_the_bundle_carries_it() -> None:
    """A conditionally-rendered credential is routed from its PRESENCE, not a guess.

    `GITHUB_PRIVATE_KEY` rides the overlay only where the host carries the App
    inputs, and a declared proof credential only where its value resolved. Both
    conditions already live in their own projections, so the routed name list is
    read back off the rendered bundle rather than re-deriving either one.
    """
    present = (
        "[environments.sandbox.env]\n"
        f"CLAUDE_CODE_OAUTH_TOKEN = {json.dumps(_FAKE_TOKEN)}\n"
        f"GITHUB_TOKEN = {json.dumps(_FAKE_GITHUB_TOKEN)}\n"
        f"CODEX_AUTH_JSON = {json.dumps('{}')}\n"
        f"GITHUB_PRIVATE_KEY = {json.dumps('pem-placeholder')}\n"
    )
    with_key = channel_module.credential_env_names(
        overlay_text=present, optional=("GITHUB_PRIVATE_KEY", "ACME_STATUS_READER")
    )
    assert set(with_key) == _EXPECTED_FAMILIES | {"GITHUB_PRIVATE_KEY"}


def test_a_dispatch_to_a_native_factory_routes_all_three_families(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end: the written bundle references each family and the vault holds it."""
    repo = _repo_declaring(tmp_path=tmp_path, channel=SECRET_CHANNEL_NATIVE_SECRETS)
    sink = _RecordingSink()
    error, overlay = _materialize(tmp_path=tmp_path, monkeypatch=monkeypatch, repo=repo, sink=sink)
    assert error is None
    rendered = overlay.read_text(encoding="utf-8")
    for env_name in sorted(_EXPECTED_FAMILIES):
        secret_name = channel_module.vault_secret_name(env_name=env_name)
        reference = channel_module.secret_reference(secret_name=secret_name)
        assert f"{env_name} = {json.dumps(reference)}\n" in rendered
        assert secret_name in sink.stored
    assert _FAKE_TOKEN not in rendered
    assert _FAKE_GITHUB_TOKEN not in rendered
    assert sink.stored[channel_module.vault_secret_name(env_name="GITHUB_TOKEN")] == (
        _FAKE_GITHUB_TOKEN
    )


def test_a_dispatch_to_an_undeclared_factory_still_inlines_and_stores_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pinned path is byte-for-byte what it was, and writes no vault entry.

    This is the regression arm for every dispatch in flight today: the factory
    this fleet runs declares no channel, so it must keep receiving inline values
    and must not acquire a dependency on a server-side vault.
    """
    repo = _repo_declaring(tmp_path=tmp_path, channel=None)
    sink = _RecordingSink()
    error, overlay = _materialize(tmp_path=tmp_path, monkeypatch=monkeypatch, repo=repo, sink=sink)
    assert error is None
    rendered = overlay.read_text(encoding="utf-8")
    assert f"CLAUDE_CODE_OAUTH_TOKEN = {json.dumps(_FAKE_TOKEN)}\n" in rendered
    assert sink.stored == {}


def test_an_unrecognised_declaration_refuses_the_whole_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The channel refusal is a PRE-LAUNCH refusal, reported as the overlay error."""
    repo = _repo_declaring(tmp_path=tmp_path, channel="vault_v2")
    sink = _RecordingSink()
    error, overlay = _materialize(tmp_path=tmp_path, monkeypatch=monkeypatch, repo=repo, sink=sink)
    assert error is not None
    assert "vault_v2" in error
    assert not overlay.exists()
    assert sink.stored == {}
