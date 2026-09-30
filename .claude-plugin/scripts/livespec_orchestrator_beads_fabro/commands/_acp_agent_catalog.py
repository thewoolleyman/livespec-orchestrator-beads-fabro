"""The COMMITTED agent-catalog snapshot, and the digest that identifies it.

`SPECIFICATION/contracts.md` section "Agent and model catalogs": entries "are
keyed by Agent Client Protocol registry agent id (`claude-acp`, `codex-acp`,
`opencode`, `grok-build`, `glm-acp-agent`, and the rest of the registry's
population)", and "the Dispatcher MUST NOT fetch a registry, a provider, or a
catalog service at dispatch time, so a dispatch depends only on committed
bytes". This module IS those bytes.

WHAT IS MEASURED AND WHAT IS SEEDED -- read this before pinning a node to an
agent below. The distinction is recorded rather than smoothed over, because an
entry that reads as measured and is not is how a dispatch fails at launch with
nothing in the catalog to explain why.

- `claude-acp` and `codex-acp` are MEASURED. Their launch distributions,
  environment mappings and rendered bytes are the ones sections "Built-in ACP
  node defaults" and "ACP node adapter configuration" ratify literally, and both
  are already exercised end to end by this repository's own dispatches; the
  Codex baked path and its `CODEX_CONFIG` posture object carry the measurement
  receipts recorded in `_dispatcher_fabro_argv`.
- `opencode`, `grok-build` and `glm-acp-agent` are SEEDED FROM THE RATIFIED
  REGISTRY POPULATION, not measured from a sandbox. Their ids and their
  multi-provider/account-domain shape come from the contract; their launch
  distribution follows the `@agentclientprotocol/<adapter>` npx convention the
  two measured entries both follow, and their `version` records the registry
  snapshot rather than a verified package version. A first dispatch through one
  of them is therefore a VERIFICATION RUN under section "Built-in ACP node
  defaults": the run transcript's resolved model must be checked and recorded on
  the work-item that made the change. Do not read an unmeasured entry as proof
  that its adapter starts.

THE DIGEST IS COMPUTED FROM THE SHIPPED ENTRIES, NEVER TRANSCRIBED. A literal
digest cannot tell a deliberate re-seed from a silent drift, and nothing in a
dispatch can re-read the upstream registry document to check one against it. A
digest over the catalog's own canonical projection identifies the snapshot THIS
BUILD carries -- which is the property a reproducible render needs -- and it
cannot fall out of step with the entries it names.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

from livespec_orchestrator_beads_fabro.commands._acp_agent_entry import AcpAgentEntry
from livespec_orchestrator_beads_fabro.commands._acp_agent_mechanism import (
    ENV_MECHANISM,
    JSON_ENV_MECHANISM,
    PROTOCOL_MECHANISM,
    AcpModelMechanism,
)

__all__: list[str] = [
    "AGENT_CATALOG_KEY",
    "ANTHROPIC_PROVIDER",
    "CLAUDE_AGENT_ID",
    "CODEX_AGENT_ID",
    "OPENAI_PROVIDER",
    "REGISTRY_SNAPSHOT_DATE",
    "agent_catalog_digest",
    "builtin_agent_catalog",
]

# The per-repository additions key, in the committed-configuration-only class
# section "ACP node adapter configuration" assigns it.
AGENT_CATALOG_KEY = "agent_catalog"

# The date the population below was seeded from the ratified registry. It is the
# date a reader checks an entry's currency against, and it is the second half of
# the snapshot identity the digest completes.
REGISTRY_SNAPSHOT_DATE = "2026-09-30"

CLAUDE_AGENT_ID = "claude-acp"
CODEX_AGENT_ID = "codex-acp"

ANTHROPIC_PROVIDER = "anthropic"
OPENAI_PROVIDER = "openai"

# The Codex adapter's baked path and its posture object, restated here rather
# than imported. Section "Built-in ACP node defaults" requires a reader to be
# able to predict the rendered string from the specification alone, and the
# binding between this catalog entry and the renderer's own constant is asserted
# by a test -- so a renderer change has to be made twice before the binding
# stops failing, which is exactly the property a transcribed literal buys.
_CODEX_BAKED_PATH = "/opt/livespec/codex-acp/bin/codex-acp"
_CODEX_POSTURE_JSON = '{"approval_policy":"never","sandbox_mode":"danger-full-access"}'

_AGENT_FULL_ACCESS = "agent-full-access"
_READ_ONLY = "read-only"

# The effort levels the Claude adapter accepts on `CLAUDE_CODE_EFFORT_LEVEL`.
_CLAUDE_EFFORT_LEVELS: tuple[str, ...] = ("low", "medium", "high")

# The Codex reasoning tiers read off the account catalog measured 2026-09-09
# (`_codex_model_tiers` carries the full measurement record). The per-MODEL
# ceiling differs -- the gpt-5.6 line reaches `ultra` while gpt-5.5 stops at
# `xhigh` -- and the catalog declares effort levels per AGENT, so this is the
# union. A pin naming a level the chosen model does not reach is refused by the
# backend rather than here; section "Built-in ACP node defaults" already says
# the reachable set is a property of the baked adapter, not of this file.
_CODEX_EFFORT_LEVELS: tuple[str, ...] = ("low", "medium", "high", "xhigh", "max", "ultra")

_BUILTIN_AGENTS: tuple[AcpAgentEntry, ...] = (
    AcpAgentEntry(
        agent_id=CLAUDE_AGENT_ID,
        display_name="Claude ACP",
        account_domain=ANTHROPIC_PROVIDER,
        provider=ANTHROPIC_PROVIDER,
        version="0.44.0",
        command="npx -y @agentclientprotocol/claude-agent-acp",
        mechanism=AcpModelMechanism(
            kind=ENV_MECHANISM,
            model="ANTHROPIC_MODEL",
            effort="CLAUDE_CODE_EFFORT_LEVEL",
        ),
        effort_levels=_CLAUDE_EFFORT_LEVELS,
    ),
    AcpAgentEntry(
        agent_id=CODEX_AGENT_ID,
        display_name="Codex ACP",
        account_domain="codex",
        provider=OPENAI_PROVIDER,
        version="1.6.2",
        command=_CODEX_BAKED_PATH,
        env={"CODEX_CONFIG": _CODEX_POSTURE_JSON, "INITIAL_AGENT_MODE": _AGENT_FULL_ACCESS},
        read_only_env={"CODEX_CONFIG": _CODEX_POSTURE_JSON, "INITIAL_AGENT_MODE": _READ_ONLY},
        mechanism=AcpModelMechanism(
            kind=JSON_ENV_MECHANISM,
            env="CODEX_CONFIG",
            model="model",
            effort="model_reasoning_effort",
        ),
        effort_levels=_CODEX_EFFORT_LEVELS,
    ),
    AcpAgentEntry(
        agent_id="opencode",
        display_name="OpenCode",
        account_domain="opencode",
        version=REGISTRY_SNAPSHOT_DATE,
        command="npx -y @agentclientprotocol/opencode-acp",
        mechanism=AcpModelMechanism(kind=PROTOCOL_MECHANISM, model="model", effort="effort"),
        multi_provider=True,
    ),
    AcpAgentEntry(
        agent_id="grok-build",
        display_name="Grok Build",
        account_domain="xai",
        provider="xai",
        version=REGISTRY_SNAPSHOT_DATE,
        command="npx -y @agentclientprotocol/grok-build-acp",
        mechanism=AcpModelMechanism(kind=PROTOCOL_MECHANISM, model="model", effort="effort"),
    ),
    AcpAgentEntry(
        agent_id="glm-acp-agent",
        display_name="GLM ACP Agent",
        account_domain="zai",
        provider="zai",
        version=REGISTRY_SNAPSHOT_DATE,
        command="npx -y @agentclientprotocol/glm-acp-agent",
        mechanism=AcpModelMechanism(kind=PROTOCOL_MECHANISM, model="model", effort="effort"),
    ),
)


def builtin_agent_catalog() -> Mapping[str, AcpAgentEntry]:
    """The shipped snapshot, keyed by registry agent id."""
    return {entry.agent_id: entry for entry in _BUILTIN_AGENTS}


def agent_catalog_digest(*, catalog: Mapping[str, AcpAgentEntry]) -> str:
    """A deterministic digest of one agent catalog's complete content.

    Every field that can change a rendered byte is in the projection, and the
    projection is sorted at both levels, so the digest is a function of the
    catalog's MEANING rather than of the order its entries happened to be
    assembled in. That is what lets two dispatches prove they rendered against
    the same snapshot.
    """
    return _digest(
        payload=[
            [
                agent_id,
                entry.display_name,
                entry.account_domain,
                entry.version,
                entry.command,
                list(entry.args),
                sorted(entry.env.items()),
                sorted(entry.read_only_env.items()),
                [entry.mechanism.kind, entry.mechanism.model, entry.mechanism.effort],
                entry.mechanism.env,
                list(entry.effort_levels),
                entry.provider,
                entry.multi_provider,
            ]
            for agent_id, entry in sorted(catalog.items())
        ]
    )


def _digest(*, payload: object) -> str:
    """The sha256 of one canonical JSON serialization."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
