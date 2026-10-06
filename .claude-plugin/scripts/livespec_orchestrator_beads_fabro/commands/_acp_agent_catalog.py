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

  SO A SEEDED ENTRY NOW NAMES THE RUN THAT LAUNCHED IT, OR IT DOES NOT SHIP. That
  is the whole point of `verification_run` and of
  `registry_entries_naming_a_verification_run`: being faithful to the registry is
  not the same as being true of a sandbox, and a transcription nobody has ever run
  is indistinguishable from a working entry at every surface except the exec. The
  withholding arm is what makes the distinction cost something.

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
    "BUILTIN_AGENT_IDS",
    "CLAUDE_AGENT_ID",
    "CODEX_AGENT_ID",
    "OPENAI_PROVIDER",
    "REGISTRY_SNAPSHOT_COMMIT",
    "REGISTRY_SNAPSHOT_DATE",
    "REGISTRY_SNAPSHOT_DIGEST",
    "agent_catalog_digest",
    "builtin_agent_catalog",
    "registry_entries_naming_a_verification_run",
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

# The two entries that are BUILT IN rather than registry-seeded, and so owe no
# recorded verification run of their own: section "Built-in ACP node defaults"
# ratifies their adapter strings literally and every dispatch this factory has run
# exercised one of them.
BUILTIN_AGENT_IDS: frozenset[str] = frozenset({CLAUDE_AGENT_ID, CODEX_AGENT_ID})

# The recorded run that launched each registry-seeded distribution below. It is the
# Fabro run of work-item `bd-ib-5tk7bx`, which re-seeded those three entries; the
# measurement each one produced is recorded beside the entry it verified.
#
# WHAT THIS RUN VERIFIED, AND WHAT IT DID NOT. It launched each distribution and
# completed an ACP `initialize` handshake against it, reading the agent's own
# self-reported version out of the response -- which is exactly the property an
# unverified entry lacked, since a transcribed command is only a string until a
# sandbox execs it. It did NOT verify a resolved MODEL: each of the three requires
# an account credential this factory does not hold, so the model-resolution half of
# the duty in section "Built-in ACP node defaults" is still owed and still belongs
# to the first dispatch routed through one of them.
_LAUNCH_VERIFICATION_RUN = "01M47AF21ST90D9XJFFPXPBZTW"

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

_MEASURED_AGENTS: tuple[AcpAgentEntry, ...] = (
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
)

# The entries seeded from the registry snapshot, each naming the run that launched
# it. A member of this tuple reaches the catalog only through
# `registry_entries_naming_a_verification_run`, so dropping a verification record
# withdraws the entry rather than quietly shipping an unrun adapter.
_REGISTRY_SEEDED_AGENTS: tuple[AcpAgentEntry, ...] = (
    # The registry declares a per-platform `binary` distribution for `opencode` and
    # NO `npx` package, so its launch triple is the archive's own `cmd` and `args`
    # -- `./opencode acp` -- and the archive itself is a PROVISIONING step that
    # deliberately has no place in a fetch-free entry. Nothing in this repository's
    # sandbox image bakes it today, which is a real gap and is left VISIBLE here
    # rather than papered over with an npx package that would merely move the
    # failure back to exec.
    #
    # Verified: the registry's `linux-x86_64` archive fetched to the declared
    # sha256 `0f22479647226d1d2dd99595d20082ee7bda3870b62dc6a90b41efc1a71d7e9a`,
    # and `./opencode acp` answered `initialize` with
    # `agentInfo {"name":"OpenCode","version":"1.18.34"}`.
    AcpAgentEntry(
        agent_id="opencode",
        display_name="OpenCode",
        account_domain="opencode",
        version="1.18.34",
        command="./opencode",
        args=("acp",),
        mechanism=AcpModelMechanism(kind=PROTOCOL_MECHANISM, model="model", effort="effort"),
        multi_provider=True,
        verification_run=_LAUNCH_VERIFICATION_RUN,
    ),
    # Verified: `npx -y @xai-official/grok@1.0.49 agent stdio` answered `initialize`
    # with `_meta.agentVersion "1.0.49"`. The response also advertised reasoning
    # efforts `low`, `medium`, `high` and `xhigh` on its `grok-4.6` default; the
    # entry still declares NO `effort_levels`, which refuses any effort pin rather
    # than admitting one on a single handshake's word -- the levels an adapter
    # reaches are a property of the account catalog behind it, and that is what the
    # model-resolution half of the verification duty is for.
    AcpAgentEntry(
        agent_id="grok-build",
        display_name="Grok Build",
        account_domain="xai",
        provider="xai",
        version="1.0.49",
        command="npx -y @xai-official/grok@1.0.49",
        args=("agent", "stdio"),
        mechanism=AcpModelMechanism(kind=PROTOCOL_MECHANISM, model="model", effort="effort"),
        verification_run=_LAUNCH_VERIFICATION_RUN,
    ),
    # Verified: `npx -y glm-acp-agent@1.14.0` answered `initialize` with
    # `agentInfo {"name":"glm-acp-agent","version":"1.14.0"}`.
    AcpAgentEntry(
        agent_id="glm-acp-agent",
        display_name="GLM ACP Agent",
        account_domain="zai",
        provider="zai",
        version="1.14.0",
        command="npx -y glm-acp-agent@1.14.0",
        mechanism=AcpModelMechanism(kind=PROTOCOL_MECHANISM, model="model", effort="effort"),
        verification_run=_LAUNCH_VERIFICATION_RUN,
    ),
)


def registry_entries_naming_a_verification_run(
    *, entries: tuple[AcpAgentEntry, ...]
) -> tuple[AcpAgentEntry, ...]:
    """The subset of a registry-seeded population that may SHIP, in order.

    This is the exclusive or the section's verification duty comes to: an entry
    either names the recorded run that verified its launch distribution, or it is
    withheld from the catalog. Withholding and shipping are the only two outcomes
    on purpose -- an unverified entry PRESENT in the catalog is the one shape that
    resolves, renders, journals, prices and then dies at exec, with nothing in the
    catalog to explain why, and a refusal-at-resolution arm would buy nothing a
    plain absence does not: the resolver already names every agent it knows.

    It takes the population as an argument rather than reading the module's own
    constant so BOTH arms are reachable from a test. A rule whose withholding arm
    only ever ran against a shipped population that happened to be fully verified
    would be a rule nobody had ever seen withhold anything.
    """
    return tuple(entry for entry in entries if entry.verification_run != "")


def builtin_agent_catalog() -> Mapping[str, AcpAgentEntry]:
    """The shipped snapshot, keyed by registry agent id."""
    shipped = (
        *_MEASURED_AGENTS,
        *registry_entries_naming_a_verification_run(entries=_REGISTRY_SEEDED_AGENTS),
    )
    return {entry.agent_id: entry for entry in shipped}


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

    `verification_run` is in the projection even though it changes no rendered
    byte, and that exception is the point: it is the one field that says whether
    the entry has ever been run, so a digest blind to it would let a re-seed drop
    every verification record while two dispatches went on agreeing they had
    rendered the same catalog.
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
                entry.verification_run,
            ]
            for agent_id, entry in sorted(catalog.items())
        ]
    )


def _digest(*, payload: object) -> str:
    """The sha256 of one canonical JSON serialization."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
