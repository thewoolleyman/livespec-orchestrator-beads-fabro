"""The transport a projected credential reaches the worker through.

`SPECIFICATION/contracts.md` section "Worker credential projection" leaves the
projection MECHANISM implementation-owned, and section "Proof credential
projection" names the two transports this module chooses between: an inline
value in the uncommitted run-configuration overlay on an engine with no secret
reference syntax, or a by-name vault reference on an engine that resolves one in
the worker. A change of transport MUST NOT change any declaration, which is why
nothing here touches what a repository declared -- every projection renders its
own env lines exactly as before, and this module rewrites the rendered VALUE
afterwards.

WHY A CHOKEPOINT REWRITE RATHER THAN A PER-PROJECTION PARAMETER. Credentials
reach the overlay from several independent renderers: the dispatch credential
table, the Codex auth snapshot, the GitHub App inputs, and each declared proof
credential. Threading the channel through every one of them makes the guarantee
"each renderer was wired correctly", which no single test can establish and
which the next renderer added silently breaks. Routing the rendered TEXT makes
it "no routed value survives in the bundle", which is one scan over one artifact
-- the same artifact the server stores immutably and `fabro inspect` reads back.

WHY THE INLINE CHANNEL IS THE DEFAULT. The pinned 0.254 engine offers no
reference syntax at all, so routing a secret on it would hand the worker a
literal reference string where a credential should be and every dispatch would
fail to authenticate. A factory says which engine it runs by DECLARING its
channel; a factory that declares nothing is the pinned one. The exposure this
module exists to close is on the OTHER engine: a Petri-era server stores each
workflow version IMMUTABLY, so an inline value persists server-side for the life
of that version rather than expiring with the mode-600 overlay file, which is
how `fabro inspect` returned the projected `CLAUDE_CODE_OAUTH_TOKEN` unredacted
on hp run 01M058955QQ5.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.effects import JsonParseFailure, parse_json

__all__: list[str] = [
    "SECRET_CHANNELS",
    "SECRET_CHANNEL_INLINE_OVERLAY",
    "SECRET_CHANNEL_NATIVE_SECRETS",
    "VAULT_SECRET_PREFIX",
    "RoutedOverlay",
    "SecretChannelRefusal",
    "VaultSecret",
    "route_secrets_through_vault",
    "secret_reference",
    "vault_secret_name",
]

# The two transports, named for WHAT THEY ARE rather than numbered: a reader of
# a dispatch refusal has to be able to tell which one a factory declared without
# consulting a lookup table.
SECRET_CHANNEL_INLINE_OVERLAY = "inline_overlay"  # noqa: S105 - a transport NAME
SECRET_CHANNEL_NATIVE_SECRETS = "native_secrets"  # noqa: S105 - a transport NAME
SECRET_CHANNELS: tuple[str, ...] = (
    SECRET_CHANNEL_INLINE_OVERLAY,
    SECRET_CHANNEL_NATIVE_SECRETS,
)

# The vault-key namespace. A prefix rather than the bare environment-variable
# name because a factory's vault is SHARED by every client of that server: the
# candidate instance already holds a placeholder `OPENAI_API_KEY` that exists
# only to satisfy the engine's provider-readiness admission, and a dispatch
# writing its own value under that spelling would silently redefine another
# client's entry. Namespacing also makes that placeholder's disposition legible
# -- it is NOT in this namespace, so it is never read, never written, and never
# mistaken for a projected credential.
VAULT_SECRET_PREFIX = "LIVESPEC_DISPATCH_"  # noqa: S105 - a vault-key PREFIX


@dataclass(frozen=True, kw_only=True)
class VaultSecret:
    """One credential routed out of the bundle and into the server-side vault.

    `value` is the resolved credential, carried so the caller can store it under
    `secret_name`. It is deliberately absent from every rendering this module
    produces, and no refusal text below interpolates it.
    """

    env_name: str
    secret_name: str
    value: str


@dataclass(frozen=True, kw_only=True)
class RoutedOverlay:
    """A bundle whose credential lines have been routed through the channel."""

    channel: str
    overlay_text: str
    secrets: tuple[VaultSecret, ...]


@dataclass(frozen=True, kw_only=True)
class SecretChannelRefusal:
    """A pre-launch refusal, carrying names and positions but never a value."""

    message: str


def vault_secret_name(*, env_name: str) -> str:
    """The STABLE vault key one environment variable's value is stored under.

    Stability across launches is load-bearing rather than tidy: the reference
    token is rendered into a workflow version the server stores immutably, so a
    run- or dispatch-scoped key would mean every rotation needed a NEW bundle.
    Deriving the key from the environment-variable name alone is what lets a
    rotated credential take effect against the bundle already on the server.
    """
    return f"{VAULT_SECRET_PREFIX}{env_name}"


def secret_reference(*, secret_name: str) -> str:
    """The worker-resolved reference token naming one vault secret.

    Rendered with the engine's own interpolation delimiters, which the overlay's
    `inputs.*` substituter deliberately leaves alone: its grammar matches only
    the `inputs.` namespace, so a `secrets.` token passes through host-side
    rendering untouched and reaches the worker, which resolves it from the vault
    at consumption time.
    """
    return "{{ secrets." + secret_name + " }}"


def route_secrets_through_vault(
    *, overlay_text: str, channel: str, env_names: Sequence[str]
) -> RoutedOverlay | SecretChannelRefusal:
    """Route each named credential line onto the channel the factory declared.

    On the inline channel the bundle is returned verbatim and nothing is routed:
    that engine resolves no reference, so the value must stay where it is.

    On the native channel each named line's rendered value is replaced by its
    reference token and returned for the caller to store. Three conditions
    REFUSE rather than degrade, because each one means the bundle and the name
    list disagree and publishing anyway is the expensive direction: a named line
    the bundle does not carry exactly once, a line carrying a value this build
    cannot decode, and a routed value still present anywhere in the rewritten
    text.
    """
    if channel != SECRET_CHANNEL_NATIVE_SECRETS:
        return RoutedOverlay(channel=channel, overlay_text=overlay_text, secrets=())
    text = overlay_text
    routed: list[VaultSecret] = []
    for env_name in sorted(set(env_names)):
        replaced = _route_one(text=text, env_name=env_name)
        if isinstance(replaced, SecretChannelRefusal):
            return replaced
        text, secret = replaced
        routed.append(secret)
    residual = _residual_refusal(text=text, secrets=tuple(routed))
    if residual is not None:
        return residual
    return RoutedOverlay(
        channel=SECRET_CHANNEL_NATIVE_SECRETS, overlay_text=text, secrets=tuple(routed)
    )


def _route_one(*, text: str, env_name: str) -> tuple[str, VaultSecret] | SecretChannelRefusal:
    """Replace one env line's value with its reference; refuse on any surprise."""
    matches = list(re.finditer(_env_line_pattern(env_name=env_name), text))
    if len(matches) != 1:
        return SecretChannelRefusal(
            message=(
                f"{env_name} appears {len(matches)} times in the run-configuration "
                "bundle; the native secret channel routes exactly one line per "
                "credential, so the projection and the routed name list disagree"
            )
        )
    match = matches[0]
    decoded = _decode_rendered_string(rendered=match.group(1))
    if decoded is None:
        return SecretChannelRefusal(
            message=(
                f"{env_name}'s rendered value is not a quoted string this build can "
                "decode, so routing it to the vault would store the wrong bytes"
            )
        )
    secret_name = vault_secret_name(env_name=env_name)
    reference = _render_string(value=secret_reference(secret_name=secret_name))
    rewritten = f"{text[: match.start(1)]}{reference}{text[match.end(1) :]}"
    return rewritten, VaultSecret(env_name=env_name, secret_name=secret_name, value=decoded)


def _env_line_pattern(*, env_name: str) -> re.Pattern[str]:
    """One whole `NAME = <value>` env-table line, with the value captured."""
    return re.compile(rf"(?m)^{re.escape(env_name)} = (.*)$")


def _decode_rendered_string(*, rendered: str) -> str | None:
    """The original value behind one rendered TOML basic string.

    Every credential line in the overlay is rendered through `json.dumps`, whose
    output is also valid JSON, so this decode is EXACT rather than a best-effort
    unescape. Anything else -- a bare literal, a multi-line string, a value some
    other renderer produced -- answers None and refuses above, because a value
    decoded wrongly would be stored wrongly in the vault while the bundle looked
    perfectly clean.
    """
    parsed = parse_json(text=rendered.strip())
    if isinstance(parsed, JsonParseFailure):
        return None
    return parsed if isinstance(parsed, str) else None


def _render_string(*, value: str) -> str:
    """One value as the TOML basic string the env table carries it in.

    Spelled through `parse_json`'s inverse rather than imported from the overlay
    renderer, so this module depends on no renderer and can be read on its own.
    """
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _residual_refusal(
    *, text: str, secrets: tuple[VaultSecret, ...]
) -> SecretChannelRefusal | None:
    """Refuse when any routed value still appears in the rewritten bundle.

    BOTH renderings are searched for. The raw value is the obvious one; the
    ESCAPED body is the one that catches a JSON-shaped credential -- the Codex
    auth snapshot is JSON, so every quote inside it is escaped where it lands in
    the bundle, and a raw-only scan passes trivially on exactly the credential
    most likely to have been pasted somewhere a line rewrite cannot reach.
    """
    for secret in secrets:
        escaped = _render_string(value=secret.value)[1:-1]
        if secret.value in text or escaped in text:
            return SecretChannelRefusal(
                message=(
                    f"{secret.secret_name}'s resolved value still appears in the "
                    "run-configuration bundle after routing, so the immutable "
                    "server-side workflow version would persist it"
                )
            )
    return None
