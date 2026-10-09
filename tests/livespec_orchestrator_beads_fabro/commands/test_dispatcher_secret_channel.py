"""The run-configuration bundle carries secret REFERENCES, never resolved values.

`SPECIFICATION/contracts.md` section "Worker credential projection" leaves the
projection mechanism implementation-owned, and section "Proof credential
projection" names the two transports explicitly: an inline value in the
uncommitted run-configuration overlay on an engine with no secret reference
syntax, or a by-name vault reference on an engine that resolves one in the
worker. The pinned 0.254 engine is the first; the Petri-era candidate is the
second, and on it a workflow version is stored IMMUTABLY ON THE SERVER, so an
inline value does not expire with the uncommitted overlay file -- it persists
server-side for the life of the version. That is the measured exposure
`fabro inspect` returned unredacted on hp run 01M058955QQ5.

The assertions below bind the FIRST Definition-of-Done assertion of work-item
bd-ib-4ipmub: the generated bundle contains only reference tokens and never a
resolved credential value. They are deliberately written against the rendered
TEXT rather than against the projection inputs, because the text is what the
server stores and what `fabro inspect` reads back.

The module under test is imported through `importlib` inside each test body
rather than at module top, so the first Red of this slice fails on a genuine
assertion about the module's own absence instead of dying at collection.
"""

from __future__ import annotations

import importlib
import json
import sys
from collections.abc import Callable
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from typing import cast

import livespec_orchestrator_beads_fabro.commands._acp_candidate_secrets as _commands_anchor
import pytest

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_secret_channel"
# Resolved off an existing sibling's own location, so the path is correct from
# any working directory the suite is invoked from.
_COMMANDS_DIR = Path(cast("str", _commands_anchor.__file__)).parent
_MODULE_PATH = _COMMANDS_DIR / "_dispatcher_secret_channel.py"

# Opaque non-secret placeholders. The routing rewrites whatever value it finds
# on the named line, so a literal spelled like a real credential here would read
# to the lint rules as a hardcoded one while proving nothing extra.
_ANTHROPIC_VALUE = "anthropic-oauth-placeholder-value"
_GITHUB_VALUE = "github-installation-placeholder-value"
# The Codex snapshot is the awkward one on purpose: it is JSON, so the overlay
# renders it through `json.dumps` and the ESCAPED form is what lands in the
# bundle. A residual scan looking only for the raw text would pass trivially on
# exactly this value, which is why it is the one carried here.
_OPENAI_VALUE = '{"tokens": {"access_token": "codex-placeholder-value"}}'

_ENV_NAMES = ("CLAUDE_CODE_OAUTH_TOKEN", "CODEX_AUTH_JSON", "GITHUB_TOKEN")
_SCOPE = "dispatch-secret-channel"


def _module() -> ModuleType:
    return importlib.import_module(_MODULE_NAME)


def _overlay_text() -> str:
    """One overlay whose env table carries all three projected credentials."""
    return (
        '[workflow]\ngraph = "/abs/workflow.fabro"\n\n'
        '[run.environment]\nid = "sandbox"\n\n'
        "[environments.sandbox.env]\n"
        f"CLAUDE_CODE_OAUTH_TOKEN = {json.dumps(_ANTHROPIC_VALUE)}\n"
        f"GITHUB_TOKEN = {json.dumps(_GITHUB_VALUE)}\n"
        f"CODEX_AUTH_JSON = {json.dumps(_OPENAI_VALUE)}\n"
        'LIVESPEC_CURRENCY_GATE = "fail"\n'
    )


def test_native_channel_renders_references_and_retains_no_resolved_value() -> None:
    """The routed bundle names each secret and carries none of their values."""
    assert _MODULE_PATH.is_file(), f"{_MODULE_PATH} does not exist yet"
    module = _module()
    routed = module.route_secrets_through_vault(
        overlay_text=_overlay_text(),
        channel=module.SECRET_CHANNEL_NATIVE_SECRETS,
        env_names=_ENV_NAMES,
        scope=_SCOPE,
    )
    text = cast("str", routed.overlay_text)
    for env_name in _ENV_NAMES:
        secret_name = module.vault_secret_name(env_name=env_name, scope=_SCOPE)
        reference = module.secret_reference(secret_name=secret_name)
        assert f"{env_name} = {json.dumps(reference)}\n" in text
    for value in (_ANTHROPIC_VALUE, _GITHUB_VALUE, _OPENAI_VALUE):
        assert value not in text
        # The escaped rendering is a DIFFERENT string from the raw value for any
        # JSON-shaped credential, and it is the one the bundle would actually
        # carry, so both forms are asserted absent.
        assert json.dumps(value)[1:-1] not in text


def test_routed_secrets_carry_each_value_for_the_vault() -> None:
    """Each routed entry pairs its launch-scoped vault name with its displaced value."""
    module = _module()
    routed = module.route_secrets_through_vault(
        overlay_text=_overlay_text(),
        channel=module.SECRET_CHANNEL_NATIVE_SECRETS,
        env_names=_ENV_NAMES,
        scope=_SCOPE,
    )
    projected = {secret.env_name: (secret.secret_name, secret.value) for secret in routed.secrets}
    assert projected == {
        "CLAUDE_CODE_OAUTH_TOKEN": (
            module.vault_secret_name(env_name="CLAUDE_CODE_OAUTH_TOKEN", scope=_SCOPE),
            _ANTHROPIC_VALUE,
        ),
        "CODEX_AUTH_JSON": (
            module.vault_secret_name(env_name="CODEX_AUTH_JSON", scope=_SCOPE),
            _OPENAI_VALUE,
        ),
        "GITHUB_TOKEN": (
            module.vault_secret_name(env_name="GITHUB_TOKEN", scope=_SCOPE),
            _GITHUB_VALUE,
        ),
    }


def test_inline_channel_leaves_the_pinned_engine_bundle_untouched() -> None:
    """The pinned engine has no reference syntax, so its bundle is unchanged."""
    module = _module()
    text = _overlay_text()
    routed = module.route_secrets_through_vault(
        overlay_text=text,
        channel=module.SECRET_CHANNEL_INLINE_OVERLAY,
        env_names=_ENV_NAMES,
        scope=_SCOPE,
    )
    assert routed.overlay_text == text
    assert routed.secrets == ()


def test_a_value_surviving_the_rewrite_refuses_instead_of_publishing_it() -> None:
    """A credential echoed elsewhere in the bundle refuses the whole routing.

    Fail-closed rather than best-effort: the routing rewrites the env LINE, so a
    projection that also pasted the same value into a prepare-step script would
    leave it in the immutable server-side version with the env line looking
    perfectly clean. The refusal names the secret and never the value.
    """
    module = _module()
    leaked = f'{_overlay_text()}\n[[run.prepare.steps]]\nscript = "echo {_GITHUB_VALUE}"\n'
    refusal = module.route_secrets_through_vault(
        overlay_text=leaked,
        channel=module.SECRET_CHANNEL_NATIVE_SECRETS,
        env_names=_ENV_NAMES,
        scope=_SCOPE,
    )
    message = cast("str", refusal.message)
    assert module.vault_secret_name(env_name="GITHUB_TOKEN", scope=_SCOPE) in message
    assert _GITHUB_VALUE not in message


def test_a_named_credential_absent_from_the_bundle_refuses() -> None:
    """Routing a name the bundle does not carry is a disagreement, not a no-op.

    The name list and the rendered table come from two different code paths, so
    a name with no line means one of them is wrong. Skipping it would hand the
    worker a `secrets.NAME` reference for a credential nothing ever set -- or,
    worse, leave an inline value standing under a different spelling.
    """
    module = _module()
    refusal = module.route_secrets_through_vault(
        overlay_text=_overlay_text(),
        channel=module.SECRET_CHANNEL_NATIVE_SECRETS,
        env_names=(*_ENV_NAMES, "ACME_ABSENT_CREDENTIAL"),
        scope=_SCOPE,
    )
    assert "ACME_ABSENT_CREDENTIAL" in cast("str", refusal.message)


def test_an_undecodable_rendered_value_refuses_rather_than_guessing() -> None:
    """A line this build cannot decode exactly refuses instead of storing bytes.

    Both arms are exercised because they fail differently and the second is the
    one that looks harmless: a value that will not parse at all, and a value
    that parses cleanly into something that is not a string. Either way the
    vault would receive bytes that are not the credential, and the bundle would
    look perfectly routed, so neither may be guessed at.
    """
    module = _module()
    for rendered in ('"unterminated', "4100"):
        bundle = (
            "[environments.sandbox.env]\n"
            f"CLAUDE_CODE_OAUTH_TOKEN = {rendered}\n"
            f"GITHUB_TOKEN = {json.dumps(_GITHUB_VALUE)}\n"
        )
        refusal = module.route_secrets_through_vault(
            overlay_text=bundle,
            channel=module.SECRET_CHANNEL_NATIVE_SECRETS,
            env_names=("CLAUDE_CODE_OAUTH_TOKEN",),
            scope=_SCOPE,
        )
        assert "CLAUDE_CODE_OAUTH_TOKEN" in cast("str", refusal.message)


def test_red_transition_helper_exercises_the_pre_scope_interface(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The immutable Red test's compatibility arm remains covered at Green.

    Red had to call the old, unscoped interface so its failure was behavioural
    rather than a ``TypeError``. Red-to-Green keeps that test byte-identical, so
    this ride-along case exercises the old-interface arm with a local stub after
    production has made the launch scope mandatory.
    """
    test_path = Path(__file__).with_name("test_dispatcher_secret_review_fixes.py")
    spec = spec_from_file_location("_secret_review_red_transition", test_path)
    assert spec is not None
    assert spec.loader is not None
    review_module = module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, review_module)
    spec.loader.exec_module(review_module)

    def legacy_route(*, overlay_text: str, channel: str, env_names: tuple[str, ...]) -> object:
        _ = channel, env_names
        return review_module.RoutedOverlay(
            channel="native_secrets", overlay_text=overlay_text, secrets=()
        )

    monkeypatch.setattr(review_module, "route_secrets_through_vault", legacy_route)
    route = cast("Callable[..., object]", vars(review_module)["_route"])
    result = route(
        text='GITHUB_TOKEN = "placeholder"\n',
        value_name="GITHUB_TOKEN",
        scope="not-forwarded-to-the-legacy-stub",
    )
    assert isinstance(result, review_module.RoutedOverlay)
