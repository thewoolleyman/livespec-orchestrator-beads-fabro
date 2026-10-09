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

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, cast

from livespec_orchestrator_beads_fabro.effects import JsonParseFailure, parse_json

__all__: list[str] = [
    "ANTHROPIC_CREDENTIAL_ENV",
    "GITHUB_CREDENTIAL_ENV",
    "OPENAI_CREDENTIAL_ENV",
    "OPTIONAL_CREDENTIAL_ENV_NAMES",
    "REQUIRED_CREDENTIAL_ENV_NAMES",
    "SECRET_CHANNELS",
    "SECRET_CHANNEL_INLINE_OVERLAY",
    "SECRET_CHANNEL_KEY",
    "SECRET_CHANNEL_NATIVE_SECRETS",
    "VAULT_SECRET_PREFIX",
    "RoutedOverlay",
    "SecretChannelRefusal",
    "VaultSecret",
    "VaultSecretSink",
    "credential_env_names",
    "declared_env_names",
    "resolve_secret_channel",
    "route_dispatch_secrets",
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
# The per-factory declaration key under `dispatcher.factories.<name>`. It is
# neither declared API-configurable nor otherwise classified, so it is
# committed-only by default per `SPECIFICATION/contracts.md` section "The
# declared-API-configurable class" and triggers no console Settings lockstep.
SECRET_CHANNEL_KEY = "secret_channel"  # noqa: S105 - a configuration KEY name

# The three credential families a worker must resolve, by the environment
# variable each one arrives under. GitHub is the installation token the sandbox
# authenticates the forge with, Anthropic the Claude subscription OAuth token,
# and OpenAI the Codex subscription auth snapshot -- NOT a provider API key,
# which the OAuth-only posture forbids the server from holding at all. That is
# also the disposition of the candidate instance's placeholder `OPENAI_API_KEY`:
# it exists only to satisfy the engine's provider-readiness admission, it is not
# in this set, and nothing here ever reads or writes it.
GITHUB_CREDENTIAL_ENV = "GITHUB_TOKEN"
ANTHROPIC_CREDENTIAL_ENV = "CLAUDE_CODE_OAUTH_TOKEN"
OPENAI_CREDENTIAL_ENV = "CODEX_AUTH_JSON"
REQUIRED_CREDENTIAL_ENV_NAMES: tuple[str, ...] = (
    ANTHROPIC_CREDENTIAL_ENV,
    OPENAI_CREDENTIAL_ENV,
    GITHUB_CREDENTIAL_ENV,
)

# Credentials the overlay renders CONDITIONALLY, so they are routed when the
# bundle carries them and absent without refusing. `GITHUB_PRIVATE_KEY` rides
# the overlay only where the host holds the App inputs the sandbox's own
# installation-token mint needs.
#
# WHY THIS LIST IS EXPLICIT RATHER THAN DISCOVERED. A lexical marker scan over
# every env name in the bundle was the obvious generalisation and it is wrong
# here: the same table carries `CODEX_REFRESH_TOKEN_URL_OVERRIDE`, a loopback
# URL, and the credential-use deadline keys, none of which is a credential, and
# a scan that refused or routed those would break every dispatch. A credential
# renderer added later must therefore add its env name here; `_acp_candidate_
# secrets` documents the same trade-off from the other direction.
OPTIONAL_CREDENTIAL_ENV_NAMES: tuple[str, ...] = ("GITHUB_PRIVATE_KEY",)

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


class VaultSecretSink(Protocol):
    """Where a routed credential is stored so the worker can resolve it.

    A seam rather than a direct call because the store is a per-factory server
    operation while the routing is a pure rewrite: keeping them apart is what
    lets the whole transport be exercised without a factory, and what keeps the
    value off every surface except this one call.
    """

    def set(self, *, secret: VaultSecret) -> str | None:
        """Store one secret; a message when it could not be stored, else None."""
        ...


def vault_secret_name(*, env_name: str, scope: str) -> str:
    """The launch-scoped vault key one environment variable is stored under.

    Fabro's vault is server-global. A name derived from ``env_name`` alone lets
    overlapping dispatchers replace a value after another dispatch rendered its
    reference but before its worker resolved it. The dispatch scope prevents
    that cross-launch read; its digest keeps arbitrary dispatch-id punctuation
    out of the expression grammar while retaining collision-resistant identity.
    """
    scope_digest = hashlib.sha256(scope.encode("utf-8")).hexdigest()[:32].upper()
    return f"{VAULT_SECRET_PREFIX}{scope_digest}_{env_name}"


def secret_reference(*, secret_name: str) -> str:
    """The worker-resolved reference token naming one vault secret.

    Rendered with the engine's own interpolation delimiters, which the overlay's
    `inputs.*` substituter deliberately leaves alone: its grammar matches only
    the `inputs.` namespace, so a `secrets.` token passes through host-side
    rendering untouched and reaches the worker, which resolves it from the vault
    at consumption time.
    """
    return "{{ secrets." + secret_name + " }}"


def resolve_secret_channel(
    *, block: Mapping[str, object], factory: str
) -> str | SecretChannelRefusal:
    """The transport one named factory declares; the inline channel by default.

    An ABSENT declaration is a complete answer rather than a gap: every factory
    in this fleet today runs the pinned engine, which resolves no reference, so
    the inline overlay is what "nothing declared" correctly means. An
    UNRECOGNISED value is not, for the reason the module docstring gives, so it
    refuses naming the key, the value read, and the transports this build
    speaks.
    """
    declared = _declared_channel(block=block, factory=factory)
    if declared is None:
        return SECRET_CHANNEL_INLINE_OVERLAY
    if declared not in SECRET_CHANNELS:
        return SecretChannelRefusal(
            message=(
                f"factory {factory!r} declares {SECRET_CHANNEL_KEY} = {declared!r}, "
                "which this build does not understand; the transports it speaks "
                f"are {', '.join(SECRET_CHANNELS)}"
            )
        )
    return declared


def credential_env_names(
    *, overlay_text: str, optional: Sequence[str]
) -> tuple[str, ...] | SecretChannelRefusal:
    """Which env lines of this bundle the native channel routes.

    Every REQUIRED family must be present, and a missing one refuses: the three
    are what the worker authenticates with, and a bundle lacking one is a broken
    projection rather than a dispatch with fewer options. Refusing here names the
    family before launch, where an unrouted inline value would instead persist in
    the immutable workflow version and a reference to an unset vault entry would
    fail the run late and opaquely.

    Each OPTIONAL name is routed only when the bundle actually carries it. Those
    credentials are rendered conditionally by projections that already own their
    own conditions -- the host's App inputs, a declared proof credential whose
    value resolved -- so reading the condition back off the rendered bundle is
    what keeps this from being a second, drifting copy of each one.
    """
    missing = [
        name
        for name in REQUIRED_CREDENTIAL_ENV_NAMES
        if not _carries(text=overlay_text, env_name=name)
    ]
    if missing:
        return SecretChannelRefusal(
            message=(
                "the run-configuration bundle carries no line for "
                f"{', '.join(sorted(missing))}, so the native secret channel has "
                "no value to store and the worker would resolve a vault entry "
                "nothing set"
            )
        )
    present = [name for name in optional if _carries(text=overlay_text, env_name=name)]
    return tuple(sorted({*REQUIRED_CREDENTIAL_ENV_NAMES, *present}))


def route_dispatch_secrets(
    *,
    overlay_text: str,
    channel: str,
    scope: str,
    proof_credentials_env: str,
    sink: VaultSecretSink | None,
) -> RoutedOverlay | SecretChannelRefusal:
    """Route one dispatch's whole bundle and store every value it displaced.

    The inline channel short-circuits: nothing is routed, nothing is stored, and
    the bundle comes back byte-for-byte, which is what keeps every dispatch to a
    pinned factory exactly as it was.

    On the native channel the order is route-then-store, and it is deliberate.
    Routing is the step that can still REFUSE, and a refusal must leave the
    vault untouched: storing first would write credentials for a dispatch the
    very next line declines to launch.

    An UNWIRED sink refuses rather than routing silently. A bundle full of
    references the vault was never given values for is the worst available
    outcome -- the run launches, authenticates against nothing, and fails deep
    inside an agent node with no indication that a transport decision caused it.
    """
    if channel != SECRET_CHANNEL_NATIVE_SECRETS:
        return RoutedOverlay(channel=channel, overlay_text=overlay_text, secrets=())
    if sink is None:
        return SecretChannelRefusal(
            message=(
                f"this dispatch resolved the {SECRET_CHANNEL_NATIVE_SECRETS} "
                "transport but was wired no vault to store through, so the worker "
                "would resolve references nothing ever set"
            )
        )
    names = credential_env_names(
        overlay_text=overlay_text,
        optional=(
            *OPTIONAL_CREDENTIAL_ENV_NAMES,
            *declared_env_names(text=proof_credentials_env),
        ),
    )
    if isinstance(names, SecretChannelRefusal):
        return names
    routed = route_secrets_through_vault(
        overlay_text=overlay_text, channel=channel, env_names=names, scope=scope
    )
    if isinstance(routed, SecretChannelRefusal):
        return routed
    return _stored(routed=routed, sink=sink)


def _stored(
    *, routed: RoutedOverlay, sink: VaultSecretSink
) -> RoutedOverlay | SecretChannelRefusal:
    """Store every routed value, refusing on the first the vault would not take.

    A store that failed and was ignored is the rotation failure mode this whole
    transport has to survive: the bundle is unchanged, so nothing looks wrong,
    and the run authenticates with whatever the vault happened to hold from an
    earlier launch -- possibly an expired credential. So the refusal is
    mandatory, and it names the vault key rather than the value it could not
    store.
    """
    for secret in routed.secrets:
        failure = sink.set(secret=secret)
        if failure is not None:
            return SecretChannelRefusal(
                message=(
                    f"storing {secret.secret_name} in the factory vault failed "
                    f"({failure}), so the worker would resolve a stale or absent value"
                )
            )
    return routed


def declared_env_names(*, text: str) -> tuple[str, ...]:
    """The env-table keys one rendered fragment assigns, in rendered order.

    Used to learn WHICH declared proof credentials a dispatch actually rendered,
    without re-reading the declaration this module must not interpret: the
    projection that owns it has already decided, and its output names them.
    """
    return tuple(match.group(1) for match in _ENV_KEY_RE.finditer(text))


def route_secrets_through_vault(
    *, overlay_text: str, channel: str, env_names: Sequence[str], scope: str
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
        replaced = _route_one(text=text, env_name=env_name, scope=scope)
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


def _route_one(
    *, text: str, env_name: str, scope: str
) -> tuple[str, VaultSecret] | SecretChannelRefusal:
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
    secret_name = vault_secret_name(env_name=env_name, scope=scope)
    reference = _render_string(value=secret_reference(secret_name=secret_name))
    rewritten = f"{text[: match.start(1)]}{reference}{text[match.end(1) :]}"
    return rewritten, VaultSecret(env_name=env_name, secret_name=secret_name, value=decoded)


def _env_line_pattern(*, env_name: str) -> re.Pattern[str]:
    """One whole `NAME = <value>` env-table line, with the value captured."""
    return re.compile(rf"(?m)^{re.escape(env_name)} = (.*)$")


# Any env-table assignment, with the KEY captured. Deliberately anchored at the
# line start and spelled with the same ` = ` separator the renderers emit, so it
# reads the lines this package writes rather than general TOML.
_ENV_KEY_RE = re.compile(r"(?m)^([A-Za-z_][A-Za-z0-9_]*) = ")


def _carries(*, text: str, env_name: str) -> bool:
    """Whether the bundle assigns `env_name` at all."""
    return _env_line_pattern(env_name=env_name).search(text) is not None


def _declared_channel(*, block: Mapping[str, object], factory: str) -> str | None:
    """One factory's declared transport, or None when it declares none.

    Walked as a loop rather than three nested reads so every "this level is not
    a mapping" answer is ONE site: an absent `factories` block, an undeclared
    factory name and a malformed entry all mean the same thing here, and
    spelling them separately would invite three slightly different answers.
    """
    cursor: object = block
    for key in ("factories", factory, SECRET_CHANNEL_KEY):
        if not isinstance(cursor, dict):
            return None
        level = cast("dict[str, Any]", cursor)
        cursor = level.get(key)
    return cursor if isinstance(cursor, str) and cursor != "" else None


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

    The overlay renderers use ``json.dumps`` because its output is also a valid
    TOML basic string. Reusing that exact serializer is load-bearing for the
    residual scan: newlines, controls and non-ASCII must have the same encoded
    spelling here as they do everywhere else in the bundle.
    """
    return json.dumps(value)


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
