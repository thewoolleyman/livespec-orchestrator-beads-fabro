"""Every way the vault transport can fail is a PRE-LAUNCH refusal, not a degrade.

`route_dispatch_secrets` is the one place a dispatch decides whether its
credentials travel as values or as references, and each of its four arms fails
in a way that is invisible at every surface an operator watches. That is why
they are refusals rather than warnings, and why each is asserted separately
here: a run launched with references the vault cannot resolve looks exactly like
a healthy run until an agent node fails to authenticate several minutes in, with
nothing in the record naming a transport decision as the cause.

The ORDER inside that function matters as much as the refusals do, and the
store-failure case is what binds it: routing must finish before anything is
stored, so a refusal leaves the vault untouched rather than seeding credentials
for a dispatch the next line declines to launch.
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_credentials import (
    materialize_overlay,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_git_author import GitAuthor
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay_write import (
    write_routed_overlay,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_secret_channel import (
    SECRET_CHANNEL_NATIVE_SECRETS,
    RoutedOverlay,
    SecretChannelRefusal,
    VaultSecret,
    route_dispatch_secrets,
    vault_secret_name,
)

# Opaque non-secret placeholders; the routing rewrites whatever it finds.
_ANTHROPIC_VALUE = "vault-anthropic-placeholder"
_GITHUB_VALUE = "vault-github-placeholder"
_OPENAI_VALUE = "vault-openai-placeholder"


@dataclass(kw_only=True)
class _AcceptingSink:
    """A vault that stores everything it is handed."""

    stored: dict[str, str] = field(default_factory=dict)

    def set(self, *, secret: VaultSecret) -> str | None:
        self.stored[secret.secret_name] = secret.value
        return None


@dataclass(kw_only=True)
class _RefusingSink:
    """A vault that refuses the credential named in `refuse`."""

    refuse: str
    stored: dict[str, str] = field(default_factory=dict)

    def set(self, *, secret: VaultSecret) -> str | None:
        if secret.secret_name == self.refuse:
            return "server rejected the write"
        self.stored[secret.secret_name] = secret.value
        return None


def _complete_bundle() -> str:
    """A bundle carrying all three required credential families."""
    return (
        "[environments.sandbox.env]\n"
        f"CLAUDE_CODE_OAUTH_TOKEN = {json.dumps(_ANTHROPIC_VALUE)}\n"
        f"GITHUB_TOKEN = {json.dumps(_GITHUB_VALUE)}\n"
        f"CODEX_AUTH_JSON = {json.dumps(_OPENAI_VALUE)}\n"
    )


def test_a_native_dispatch_with_no_vault_wired_refuses() -> None:
    """Routing without somewhere to store is references pointing at nothing."""
    refusal = route_dispatch_secrets(
        overlay_text=_complete_bundle(),
        channel=SECRET_CHANNEL_NATIVE_SECRETS,
        proof_credentials_env="",
        sink=None,
    )
    assert isinstance(refusal, SecretChannelRefusal)
    assert SECRET_CHANNEL_NATIVE_SECRETS in refusal.message


def test_a_bundle_missing_a_required_family_refuses_through_the_dispatch_path() -> None:
    """The family refusal reaches the dispatch, not just the name collector."""
    bundle = (
        "[environments.sandbox.env]\n"
        f"CLAUDE_CODE_OAUTH_TOKEN = {json.dumps(_ANTHROPIC_VALUE)}\n"
        f"GITHUB_TOKEN = {json.dumps(_GITHUB_VALUE)}\n"
    )
    refusal = route_dispatch_secrets(
        overlay_text=bundle,
        channel=SECRET_CHANNEL_NATIVE_SECRETS,
        proof_credentials_env="",
        sink=_AcceptingSink(),
    )
    assert isinstance(refusal, SecretChannelRefusal)
    assert "CODEX_AUTH_JSON" in refusal.message


def test_a_routing_refusal_stores_nothing_at_all() -> None:
    """A bundle that cannot be routed cleanly leaves the vault untouched.

    This is the ordering assertion. The bundle below echoes one credential into
    a prepare step, which the residual scan catches AFTER the rewrite -- so a
    store performed line-by-line during the rewrite would already have written
    two credentials for a dispatch that is about to be refused.
    """
    bundle = f'{_complete_bundle()}\n[[run.prepare.steps]]\nscript = "echo {_GITHUB_VALUE}"\n'
    sink = _AcceptingSink()
    refusal = route_dispatch_secrets(
        overlay_text=bundle,
        channel=SECRET_CHANNEL_NATIVE_SECRETS,
        proof_credentials_env="",
        sink=sink,
    )
    assert isinstance(refusal, SecretChannelRefusal)
    assert sink.stored == {}


def test_a_vault_that_refuses_a_write_refuses_the_dispatch() -> None:
    """An ignored store failure is the rotation fault this transport must survive.

    The bundle still looks routed, so nothing looks wrong, and the worker would
    authenticate with an absent or incomplete stable entry. The
    refusal names the vault key and carries the server's own reason, never the
    value it could not store.
    """
    refused_key = vault_secret_name(env_name="GITHUB_TOKEN")
    refusal = route_dispatch_secrets(
        overlay_text=_complete_bundle(),
        channel=SECRET_CHANNEL_NATIVE_SECRETS,
        proof_credentials_env="",
        sink=_RefusingSink(refuse=refused_key),
    )
    assert isinstance(refusal, SecretChannelRefusal)
    assert refused_key in refusal.message
    assert _GITHUB_VALUE not in refusal.message


def test_a_routing_refusal_leaves_no_overlay_file_behind(tmp_path: Path) -> None:
    """An unroutable bundle writes nothing, because existence means materialized.

    The dispatch path treats the overlay's presence as a completed projection,
    so a refusal that had already written a half-routed file would be launched
    with credentials on neither transport.
    """
    overlay = tmp_path / "overlay.toml"
    refusal = write_routed_overlay(
        overlay=overlay,
        rendered=_complete_bundle(),
        channel=SECRET_CHANNEL_NATIVE_SECRETS,
        proof_credentials_env="",
        sink=None,
    )
    assert refusal is not None
    assert not overlay.exists()


def test_a_routing_refusal_removes_a_preexisting_credential_overlay(
    tmp_path: Path,
) -> None:
    """A refused replacement cannot preserve credentials from an earlier launch.

    The dispatch cleanup stack is registered only after materialization succeeds,
    so this function owns cleanup when native-secret routing itself refuses.
    """
    overlay = tmp_path / "overlay.toml"
    _ = overlay.write_text(_complete_bundle(), encoding="utf-8")

    refusal = write_routed_overlay(
        overlay=overlay,
        rendered=_complete_bundle(),
        channel=SECRET_CHANNEL_NATIVE_SECRETS,
        proof_credentials_env="",
        sink=None,
    )

    assert refusal is not None
    assert not overlay.exists()


def test_a_routed_bundle_is_written_mode_600(tmp_path: Path) -> None:
    """The written overlay is readable by its owner alone, routed or inline."""
    overlay = tmp_path / "overlay.toml"
    sink = _AcceptingSink()
    assert (
        write_routed_overlay(
            overlay=overlay,
            rendered=_complete_bundle(),
            channel=SECRET_CHANNEL_NATIVE_SECRETS,
            proof_credentials_env="",
            sink=sink,
        )
        is None
    )
    assert overlay.stat().st_mode & 0o777 == 0o600
    assert _ANTHROPIC_VALUE not in overlay.read_text(encoding="utf-8")


def test_a_routing_refusal_revokes_the_credentials_the_dispatch_had_minted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dispatch refused at the transport gives back every credential it minted.

    The proof-credential mint runs just before the bundle is routed, and its
    revoke is the RUN's own teardown — which a refused dispatch never reaches.
    So the refusal has to revoke on the way out, or a provider credential
    outlives a run that never existed and nothing is looking for it.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    config = {
        "livespec-orchestrator-beads-fabro": {
            "dispatcher": {"factories": {"candidate": {"secret_channel": "native_secrets"}}}
        }
    }
    _ = (repo / ".livespec.jsonc").write_text(json.dumps(config), encoding="utf-8")
    committed = tmp_path / "workflow.toml"
    _ = committed.write_text(
        '_version = 1\n\n[workflow]\ngraph = "workflow.fabro"\n\n[run.environment]\nid = "ci"\n',
        encoding="utf-8",
    )
    _ = (tmp_path / "workflow.fabro").write_text(
        "digraph ImplementWorkItem {\n"
        '    graph [\n        stall_timeout="7200s"\n    ]\n'
        '    implement [\n        timeout="1800s"\n    ]\n'
        "}\n",
        encoding="utf-8",
    )
    now = 1_700_000_000
    exp_payload = (
        base64.urlsafe_b64encode(json.dumps({"exp": now + 100 * 365 * 24 * 3600}).encode())
        .decode()
        .rstrip("=")
    )
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", _ANTHROPIC_VALUE)
    monkeypatch.setattr(
        _dispatcher_sibling_clones,
        "fetch_fleet_manifest_text",
        lambda: json.dumps({"owner": "thewoolleyman", "fleet": [{"repo": "livespec"}]}),
    )
    monkeypatch.setattr(_dispatcher_credentials.time, "time", lambda: now)
    monkeypatch.setattr(
        _dispatcher_codex_auth,
        "read_host_codex_auth",
        lambda: json.dumps(
            {
                "auth_mode": "chatgpt",
                "tokens": {"access_token": f"h.{exp_payload}.s", "refresh_token": "host"},
            }
        ),
    )
    revoked: list[str] = []
    monkeypatch.setattr(
        _dispatcher_credentials,
        "revoke_proof_credentials",
        lambda **kwargs: revoked.append(str(kwargs["scope"])),
    )
    error = materialize_overlay(
        committed=committed,
        overlay=tmp_path / "overlay.toml",
        repo=repo,
        work_item_id="wi-vault",
        dispatch_id="01M4G085KXTH03ME7KDARYG8G8",
        token=lambda: _GITHUB_VALUE,
        git_author=GitAuthor(name="Operator", email="operator@example.com"),
        review_fix_visit_cap=4,
        factory_name="candidate",
        secret_sink=None,
    )
    assert error is not None
    assert revoked == ["01M4G085KXTH03ME7KDARYG8G8"]


def test_a_declared_proof_credential_is_routed_with_the_dispatch_set() -> None:
    """A rendered proof-credential line travels as a reference like any other.

    `SPECIFICATION/contracts.md` section "Proof credential projection" makes the
    transport implementation-owned and requires that a change of transport leave
    the DECLARATION alone, so the routed name list is read back off the lines
    that projection rendered rather than from a second reading of the key.
    """
    reader_value = "acme-observer-placeholder"
    proof_env = f"ACME_STATUS_READER = {json.dumps(reader_value)}\n"
    sink = _AcceptingSink()
    routed = route_dispatch_secrets(
        overlay_text=_complete_bundle() + proof_env,
        channel=SECRET_CHANNEL_NATIVE_SECRETS,
        proof_credentials_env=proof_env,
        sink=sink,
    )
    assert isinstance(routed, RoutedOverlay)
    reader_key = vault_secret_name(env_name="ACME_STATUS_READER")
    assert sink.stored[reader_key] == reader_value
    assert reader_value not in routed.overlay_text
