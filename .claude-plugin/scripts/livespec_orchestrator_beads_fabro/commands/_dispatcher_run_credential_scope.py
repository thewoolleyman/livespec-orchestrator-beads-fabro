"""Which ACP nodes the run-scoped provisioned credential reaches, and which opt out.

The Dispatcher projects ONE credential per run, into the `[environments.<id>.env]` table
of the uncommitted run-config overlay. Every node of the graph executes inside that
environment, so the review node authenticates as the same manager-selected account as the
implementer — not as a second credential drawn from somewhere else. That is the property
this module makes checkable rather than merely true-by-accident.

THE EXCEPTION IS AN ADAPTER THAT ASKS FOR ONE. A node's ACP adapter is a
`(command, env, args)` triple, and its `env` layer wins over the environment table for the
keys it names. So a node whose adapter env declares its own provider credential key has
EXPLICITLY REQUESTED another capability — a different provider, a proxied endpoint, an
API-billed key — and the run-scoped credential must not be read as governing it. A node
whose adapter names no credential key has requested nothing, and the run-scoped credential
applies.

WHY THIS IS A NAME TEST AND NOT A VALUE TEST. There is no reliable shape for "this string
is a credential"; what IS reliable is that a credential arrives under a name that says so.
`_acp_candidate_secrets` makes the same argument for refusing committed literals, and this
module deliberately mirrors its reasoning — but NOT its vocabulary. That scan is broad on
purpose (it refuses anything smelling of a secret in committed data); this one must be
NARROW, because a false positive here would silently conclude that a node opted out of the
run credential when it did not. So the set below is exactly the env names by which an
Anthropic-authenticating ACP adapter can be handed its own credential, and nothing else.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

__all__: list[str] = [
    "CAPABILITY_CREDENTIAL_ENV_NAMES",
    "requested_capability_env_name",
    "run_scoped_credential_applies",
]

# The closed set of env names by which an adapter can be handed a credential of its own.
# `ANTHROPIC_AUTH_TOKEN` and `ANTHROPIC_API_KEY` are the two the Anthropic SDK reads;
# `CLAUDE_CODE_OAUTH_TOKEN` is the subscription credential the run-scoped projection
# itself uses, so an adapter that sets it is overriding that projection by name.
CAPABILITY_CREDENTIAL_ENV_NAMES: Final = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "CLAUDE_CODE_OAUTH_TOKEN",
)


def requested_capability_env_name(*, adapter_env: Mapping[str, str]) -> str | None:
    """The credential env name this adapter declares, or None when it declares none.

    Returned by NAME rather than as a boolean so a caller reporting the exception can say
    which key caused it; the VALUE is never read, so an adapter declaring a credential
    cannot leak one through this surface.
    """
    return next(
        (name for name in CAPABILITY_CREDENTIAL_ENV_NAMES if name in adapter_env),
        None,
    )


def run_scoped_credential_applies(*, adapter_env: Mapping[str, str]) -> bool:
    """Whether this node receives the run-scoped credential the manager provisioned."""
    return requested_capability_env_name(adapter_env=adapter_env) is None
