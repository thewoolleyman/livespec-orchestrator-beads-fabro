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
- `opencode`, `grok-build` and `glm-acp-agent` are SEEDED FROM THE ACP REGISTRY
  SNAPSHOT recorded below. Their ids and their multi-provider/account-domain
  shape come from the contract; their launch distribution and their `version` are
  rendered from the registry's own `distribution` block at the pinned registry
  commit, and `tests/fixtures/acp_registry_snapshot/` holds the verbatim
  `agent.json` documents the render was taken from, so a drifted entry disagrees
  with the registry's bytes rather than merely with a literal.

  THEY CARRIED A FICTION UNTIL 2026-10-06, and it is recorded here because the
  shape recurs. Their commands followed an `@agentclientprotocol/<adapter>` npx
  convention extrapolated from the two measured entries -- no registry has ever
  published `@agentclientprotocol/opencode-acp`, `.../grok-build-acp` or
  `.../glm-acp-agent` -- and their `version` held the snapshot DATE. Both faults
  are invisible to every refusal in the resolution path, because a command is
  only ever a string until a sandbox execs it: a structured candidate naming one
  of them resolved, rendered, journaled and then died at exec with nothing in the
  catalog to explain why.

TWO DIGESTS, ANSWERING TWO DIFFERENT QUESTIONS, AND CONFLATING THEM IS HOW A
SNAPSHOT IDENTITY STOPS NAMING A SNAPSHOT. `agent_catalog_digest` is COMPUTED
from the shipped entries and identifies the catalog THIS BUILD carries, which is
the property a reproducible render needs: it cannot fall out of step with the
entries it names, so two dispatches can prove they rendered against the same
committed bytes. `REGISTRY_SNAPSHOT_DIGEST` is TRANSCRIBED and identifies the
UPSTREAM document the entries were seeded from -- a question no self-digest can
answer, because the catalog holds no copy of the registry to hash. Until
2026-10-06 only the computed one existed, under a record key that promised the
other, so a dispatch could say exactly which bytes it rendered and nothing at all
about where they came from.

A transcribed literal has to be checkable or it is indistinguishable from a typo,
and a dispatch may not fetch the registry to check it. So the evidence is
COMMITTED instead: `tests/fixtures/acp_registry_snapshot/` holds the verbatim
`agent.json` documents of the ratified five ids at `REGISTRY_SNAPSHOT_COMMIT`, and
`test_acp_agent_catalog_registry_seed` re-runs the recipe over them. The recipe
is, in sorted agent-id order, the id, a newline, then that id's verbatim document
bytes, all fed to one sha256. The commit is recorded beside the digest so a reader
can re-fetch those exact documents rather than taking the fixture's word for them.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from livespec_orchestrator_beads_fabro.commands._acp_agent_entry import (
    AcpAgentEntry,
    parse_agent_entry,
)
from livespec_orchestrator_beads_fabro.commands._acp_agent_mechanism import (
    ENV_MECHANISM,
    JSON_ENV_MECHANISM,
    PROTOCOL_MECHANISM,
    AcpModelMechanism,
)
from livespec_orchestrator_beads_fabro.commands._acp_catalog_overrides import catalog_overrides

__all__: list[str] = [
    "AGENT_CATALOG_KEY",
    "ANTHROPIC_PROVIDER",
    "CLAUDE_AGENT_ID",
    "CODEX_AGENT_ID",
    "OPENAI_PROVIDER",
    "REGISTRY_SNAPSHOT_COMMIT",
    "REGISTRY_SNAPSHOT_DATE",
    "REGISTRY_SNAPSHOT_DIGEST",
    "agent_catalog_digest",
    "builtin_agent_catalog",
    "resolve_agent_catalog",
]

# The per-repository additions key, in the committed-configuration-only class
# section "ACP node adapter configuration" assigns it.
AGENT_CATALOG_KEY = "agent_catalog"

# The date the population below was seeded from the ACP registry. It is the date
# a reader checks an entry's currency against, and it is the second half of the
# snapshot identity the registry digest completes.
REGISTRY_SNAPSHOT_DATE = "2026-10-06"

# The `agentclientprotocol/registry` revision the documents behind that date were
# read at, and the digest of those documents. The commit is half the identity: it
# is what lets a reader re-fetch the exact bytes instead of checking the digest
# against the only copy that could ever agree with it.
REGISTRY_SNAPSHOT_COMMIT = "34036ca75eeba8a776837850b96be10b66763e86"
REGISTRY_SNAPSHOT_DIGEST = "06f2cba54a409ef43e84cd218def02ce2126feb647ee6befc2fde89fb167405f"

CLAUDE_AGENT_ID = "claude-acp"
CODEX_AGENT_ID = "codex-acp"

ANTHROPIC_PROVIDER = "anthropic"
OPENAI_PROVIDER = "openai"

# The Codex adapter's baked path and its posture object, restated here rather
# than imported. Section "Built-in ACP node defaults" requires a reader to be
# able to predict the rendered string from the specification alone, and a chain
# of imports defeats that. Restating is only safe because
# `test_acp_agent_catalog_pinned_versions` FAILS when this entry, the argv
# renderer's own constant, and the sandbox image's provisioning script disagree
# -- which is the agreement `SPECIFICATION/constraints.md` section "Pinned agent
# versions" requires. That module also records which half of the constraint is
# NOT checkable here: the VERSION each entry pins is a measurement receipt, not
# a value any committed file can be compared against, because the image's baked
# version arrives as an operator argument.
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
    # The registry declares a per-platform `binary` distribution for `opencode`
    # and NO `npx` package, so its launch triple is the archive's own `cmd` and
    # `args` -- `./opencode acp` -- and the archive itself is a PROVISIONING step
    # that deliberately has no place in a fetch-free entry. Nothing in this
    # repository's sandbox image bakes it today, which is a real gap and is left
    # VISIBLE here rather than papered over with an npx package that would merely
    # move the failure back to exec.
    AcpAgentEntry(
        agent_id="opencode",
        display_name="OpenCode",
        account_domain="opencode",
        version="1.18.34",
        command="./opencode",
        args=("acp",),
        mechanism=AcpModelMechanism(kind=PROTOCOL_MECHANISM, model="model", effort="effort"),
        multi_provider=True,
    ),
    AcpAgentEntry(
        agent_id="grok-build",
        display_name="Grok Build",
        account_domain="xai",
        provider="xai",
        version="1.0.49",
        command="npx -y @xai-official/grok@1.0.49",
        args=("agent", "stdio"),
        mechanism=AcpModelMechanism(kind=PROTOCOL_MECHANISM, model="model", effort="effort"),
    ),
    AcpAgentEntry(
        agent_id="glm-acp-agent",
        display_name="GLM ACP Agent",
        account_domain="zai",
        provider="zai",
        version="1.14.0",
        command="npx -y glm-acp-agent@1.14.0",
        mechanism=AcpModelMechanism(kind=PROTOCOL_MECHANISM, model="model", effort="effort"),
    ),
)


def builtin_agent_catalog() -> Mapping[str, AcpAgentEntry]:
    """The shipped snapshot, keyed by registry agent id."""
    return {entry.agent_id: entry for entry in _BUILTIN_AGENTS}


def resolve_agent_catalog(*, block: Mapping[str, Any]) -> Mapping[str, AcpAgentEntry] | str:
    """The shipped snapshot with this repository's own entries applied, or refuse.

    A repository entry REPLACES a shipped one of the same id rather than
    merging into it, which is what `parse_agent_entry` requires a complete entry
    for. The shipped entries a repository does not name are untouched, so
    overriding `claude-acp` cannot silently change what `codex-acp` renders.
    """
    overrides = catalog_overrides(block=block, config_key=AGENT_CATALOG_KEY)
    if isinstance(overrides, str):
        return overrides
    catalog = dict(builtin_agent_catalog())
    for agent_id, entry in overrides.items():
        parsed = parse_agent_entry(
            agent_id=agent_id,
            entry=entry,
            key=f"dispatcher.{AGENT_CATALOG_KEY}.{agent_id}",
        )
        if isinstance(parsed, str):
            return parsed
        catalog[agent_id] = parsed
    return catalog


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
