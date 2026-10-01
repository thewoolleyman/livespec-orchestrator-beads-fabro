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
The workflow's own declared adapter defaults are the Anthropic ACP adapters
section "Built-in ACP node defaults" ratified in v107 -- the Claude Haiku 4.5
publish default and the Claude implementer default -- so their bytes carry
`anthropic`. The UN-PINNED CODEX BASE STRINGS, in both postures, are the
other: section "Built-in ACP node defaults" spells them out literally and
names them the explicit un-pinned opt-out, so they are bytes this build
renders and their domain is `codex`. Both names are the existing legacy
provider aliases, which is what lets an unexpired legacy provider record
keep covering a built-in candidate until retirement.

WHY THE CODEX ENTRIES ARE THE UN-PINNED BASES AND NOTHING ELSE. While
`dispatcher.codex_models` existed, this table rendered both of its tiers so
a shorthand-expanded adapter could match its own built-in. That key is
retired, and a PINNED Codex adapter now reaches a dispatch only as a
STRUCTURED entry -- whose identity is DERIVED from the catalogs by
`_acp_structured_identity`, never matched by bytes. So the only Codex bytes
left for byte-equality to attach to are the two un-pinned opt-out strings,
which have no structured spelling and therefore no derived identity.

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

from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidateIdentity
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import (
    parse_adapter_string,
    render_adapter,
)
from livespec_orchestrator_beads_fabro.commands._codex_model_tiers import CodexModelTier
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_argv import (
    CODEX_AGENT_MODE_READ_ONLY,
    CODEX_AGENT_MODE_WRITE,
    codex_adapter,
)

__all__: list[str] = [
    "ANTHROPIC_DOMAIN",
    "CODEX_DOMAIN",
    "builtin_acp_identities",
]

ANTHROPIC_DOMAIN = "anthropic"
CODEX_DOMAIN = "codex"

_KEY_LENGTH = 16


def builtin_acp_identities(
    *, workflow_inputs: Mapping[str, str]
) -> Mapping[str, AcpCandidateIdentity]:
    """Map every built-in adapter's exact rendered bytes onto its identity.

    BOTH Codex postures are rendered unconditionally, even when no node
    resolves to either. An entry no dispatch resolves to simply never
    matches, so including it costs a lookup miss; the alternative --
    re-deriving which nodes opted out of the pin -- would put a second copy
    of that predicate here, and two copies of it is how this table and the
    resolved adapter would come to disagree about which adapter a node runs.
    """
    identities: dict[str, AcpCandidateIdentity] = {}
    for declared in sorted(set(workflow_inputs.values())):
        identities[_normalized(text=declared)] = _identity(
            text=declared, domain=ANTHROPIC_DOMAIN, label="Anthropic ACP adapter"
        )
    unpinned = CodexModelTier(model="", reasoning_effort="")
    for agent_mode in (CODEX_AGENT_MODE_WRITE, CODEX_AGENT_MODE_READ_ONLY):
        rendered = codex_adapter(tier=unpinned, agent_mode=agent_mode)
        identities[_normalized(text=rendered)] = _identity(
            text=rendered, domain=CODEX_DOMAIN, label="un-pinned Codex ACP adapter"
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
