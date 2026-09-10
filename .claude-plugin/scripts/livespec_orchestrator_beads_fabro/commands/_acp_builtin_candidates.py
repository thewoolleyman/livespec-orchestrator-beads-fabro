"""The BUILT-IN candidate identities this build itself renders.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" says built-in identity metadata applies ONLY WHILE the finally
resolved adapter MATCHES that built-in, that a fallback-enabled arbitrary
primary must carry explicit identity and must not retain the replaced
built-in's, and that identity is NEVER INFERRED FROM COMMAND TEXT.

THE TABLE IS KEYED ON EXACT RENDERED BYTES, and that is the difference
between matching a built-in and inferring an identity. Nothing here reads
a command for meaning -- no provider substring, no model prefix, no
heuristic. A built-in adapter is one THIS BUILD RENDERED, so its bytes are
known exactly, and the lookup is equality against those bytes. The moment
a repository overrides the command, the resolved bytes stop matching and
NO identity attaches, which is precisely the "only while it matches"
clause.

WHERE THE DOMAIN NAME COMES FROM: PROVENANCE, NOT TEXT. There are two
built-in sources and this build knows what each one is by construction.
The `dispatcher.codex_models` shorthand renders Codex adapters, so its
bytes carry the `codex` availability domain. The workflow's own declared
adapter defaults are the Anthropic ACP adapters section "Codex ACP node
model pins" ratified in v107 -- the Claude Haiku 4.5 publish default and
the Claude implementer default -- so their bytes carry `anthropic`. Both
names are the existing legacy provider aliases, which is what lets an
unexpired legacy provider record keep covering a built-in candidate until
retirement.

THE CANDIDATE KEY IS A DIGEST OF THE BYTES rather than a parsed model
name, for the same reason: a parsed name would be inference. A digest is
stable across dispatches, opaque, non-secret, and changes exactly when the
built-in adapter changes -- which is what a candidate entitlement key has
to do.

KNOWN LIMIT, recorded rather than hidden: a dispatch TARGET whose own
committed workflow declares a non-Anthropic default would be given the
`anthropic` domain by the workflow-provenance rule above. That costs
nothing today -- no slice consumes these identities yet, and this
repository's graph declares Anthropic defaults -- but it is the assumption
to revisit when typed holds start consuming them.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidateIdentity
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import (
    parse_adapter_string,
    render_adapter,
)
from livespec_orchestrator_beads_fabro.commands._codex_model_tiers import (
    codex_model_tiers_from_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_argv import codex_adapter

__all__: list[str] = [
    "ANTHROPIC_DOMAIN",
    "CODEX_DOMAIN",
    "builtin_acp_identities",
]

ANTHROPIC_DOMAIN = "anthropic"
CODEX_DOMAIN = "codex"

_KEY_LENGTH = 16


def builtin_acp_identities(
    *, workflow_inputs: Mapping[str, str], block: Mapping[str, Any]
) -> Mapping[str, AcpCandidateIdentity]:
    """Map every built-in adapter's exact rendered bytes onto its identity.

    BOTH Codex tiers are rendered unconditionally, even when the target
    configured neither. An entry no dispatch resolves to simply never
    matches, so including it costs a lookup miss; the alternative --
    re-deriving which tiers were explicitly configured -- would put a
    second copy of that predicate here, and two copies of it is how this
    table and the overlay expansion would come to disagree about which
    adapter a node actually runs.
    """
    tiers = codex_model_tiers_from_block(block=dict(block))
    identities: dict[str, AcpCandidateIdentity] = {}
    for declared in sorted(set(workflow_inputs.values())):
        identities[_normalized(text=declared)] = _identity(
            text=declared, domain=ANTHROPIC_DOMAIN, label="Anthropic ACP adapter"
        )
    for tier in (tiers.pr, tiers.implementer):
        rendered = codex_adapter(tier=tier)
        identities[_normalized(text=rendered)] = _identity(
            text=rendered, domain=CODEX_DOMAIN, label="Codex ACP adapter"
        )
    return identities


def _normalized(*, text: str) -> str:
    """The bytes a resolved node renders for this adapter.

    Resolution parses every configured adapter string and re-renders it,
    so the table must key on the SAME round trip rather than on the raw
    configured text -- otherwise an adapter whose env order or quoting
    differs cosmetically would never match its own built-in.
    """
    return render_adapter(adapter=parse_adapter_string(text=text))


def _identity(*, text: str, domain: str, label: str) -> AcpCandidateIdentity:
    """One built-in identity, keyed by a digest of its own rendered bytes."""
    digest = hashlib.sha256(_normalized(text=text).encode("utf-8")).hexdigest()[:_KEY_LENGTH]
    return AcpCandidateIdentity(
        display_name=f"built-in {label}",
        candidate_key=f"builtin-{domain}-{digest}",
        availability_key=domain,
    )
