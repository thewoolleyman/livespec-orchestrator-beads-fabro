"""The NEW-GRAMMAR metadata one `dispatcher.acp_nodes` entry may carry.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" adds identity, availability signatures, pricing and an ordered
`fallbacks` array to the existing per-node entry. This module reads that
metadata OFF the entry; it deliberately does NOT read the entry's
`command` / `env` / `args`, which stay the legacy overlay
`_acp_node_repository` already resolves through the three layers. Keeping
the two readers apart is what makes "resolve the primary completely, THEN
attach the chain" a property of the CODE rather than a rule someone has to
remember.

"NEW-GRAMMAR-ENABLED" IS A PRECISE PREDICATE, and getting it wrong in
either direction is a contract violation. It means identity, a signature,
pricing, or a NON-EMPTY fallback field is present. `fallbacks: []` alone
is expressly NOT enabling: the contract calls it the byte-identical no-op,
so an operator can write the key while migrating without changing a single
rendered byte or opening any of the refusals below.

WHY THE ENTRY'S KEY SET IS CLOSED ONLY WHEN ENABLED. From the first
fallback-capable release onward the contract refuses every unknown
`acp_nodes` key. Applying that to a LEGACY entry as well would change the
behaviour of configuration that predates the feature, which is exactly the
byte-identity the first acceptance condition protects. So a legacy entry
keeps the pre-existing tolerance and an enabled one is closed -- the
operator who opts in gets the strict grammar they opted into.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._acp_candidate_pricing import AcpCandidatePricing
from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import (
    CANDIDATE_KEYS,
    AcpCandidate,
    AcpCandidateIdentity,
    parse_candidate_identity,
    parse_candidate_metadata,
    parse_fallback_candidate,
)
from livespec_orchestrator_beads_fabro.commands._acp_candidate_secrets import (
    adapter_secret_refusal,
)
from livespec_orchestrator_beads_fabro.commands._acp_candidate_signatures import (
    AcpAvailabilitySignature,
)
from livespec_orchestrator_beads_fabro.commands._acp_schema_fields import (
    string_map,
    string_tuple,
)

__all__: list[str] = [
    "EMPTY_CHAIN",
    "NODE_ENTRY_KEYS",
    "AcpNodeChain",
    "parse_node_chain",
    "parse_node_chains",
]

_FALLBACKS_KEY = "fallbacks"

# The closed key set for an ENABLED node entry: the legacy primary overlay
# fields plus every candidate field plus the ordered chain itself.
NODE_ENTRY_KEYS: frozenset[str] = CANDIDATE_KEYS | {"command", "env", "args", _FALLBACKS_KEY}

# The keys whose mere PRESENCE opts a node into the new grammar. `fallbacks`
# is absent on purpose: an empty array is the contract's byte-identical
# no-op, so enabling is decided on the parsed array instead.
_ENABLING_KEYS: frozenset[str] = CANDIDATE_KEYS - {"command", "env", "args"}


@dataclass(frozen=True, kw_only=True)
class AcpNodeChain:
    """One node's declared identity, metadata and ordered fallback candidates."""

    identity: AcpCandidateIdentity | None = None
    signatures: tuple[AcpAvailabilitySignature, ...] = ()
    pricing: AcpCandidatePricing | None = None
    fallbacks: tuple[AcpCandidate, ...] = ()
    enabled: bool = False


# What a node with no new-grammar metadata resolves to. Shared rather than
# rebuilt so an identity check against it is meaningful and so the legacy
# path allocates nothing.
EMPTY_CHAIN = AcpNodeChain()


def parse_node_chains(
    *, table: Mapping[str, Any], key_prefix: str
) -> Mapping[str, AcpNodeChain] | str:
    """Parse every configured node's chain metadata, or refuse.

    Nodes are visited in sorted order so a configuration with two faults
    always refuses on the same one, which is what makes a refusal message
    reproducible across dispatches.
    """
    chains: dict[str, AcpNodeChain] = {}
    for node in sorted(table):
        parsed = parse_node_chain(entry=table[node], key=f"{key_prefix}.{node}")
        if isinstance(parsed, str):
            return parsed
        chains[node] = parsed
    return chains


def parse_node_chain(*, entry: object, key: str) -> AcpNodeChain | str:
    """Parse one node entry's chain metadata, or refuse naming the key.

    A STRING entry is the legacy whole-adapter spelling and carries no
    metadata at all, so it resolves to the empty chain rather than
    refusing: the legacy spelling stays valid for a legacy node.
    """
    if not isinstance(entry, dict):
        return EMPTY_CHAIN
    table = cast("dict[str, Any]", entry)
    fallbacks = _fallbacks(table=table, key=key)
    if isinstance(fallbacks, str):
        return fallbacks
    identity = parse_candidate_identity(entry=table, key=key)
    if isinstance(identity, str):
        return identity
    if not _enabled(table=table, fallbacks=fallbacks):
        return EMPTY_CHAIN
    return _enabled_chain(table=table, key=key, identity=identity, fallbacks=fallbacks)


def _enabled_chain(
    *,
    table: Mapping[str, Any],
    key: str,
    identity: AcpCandidateIdentity | None,
    fallbacks: tuple[AcpCandidate, ...],
) -> AcpNodeChain | str:
    """Finish parsing an entry that has opted into the new grammar, or refuse."""
    refusal = _enabled_entry_refusal(table=table, key=key)
    if refusal is not None:
        return refusal
    metadata = parse_candidate_metadata(entry=table, key=key)
    if isinstance(metadata, str):
        return metadata
    return AcpNodeChain(
        identity=identity,
        signatures=metadata.signatures,
        pricing=metadata.pricing,
        fallbacks=fallbacks,
        enabled=True,
    )


def _enabled(*, table: Mapping[str, Any], fallbacks: tuple[AcpCandidate, ...]) -> bool:
    """Whether this entry opts the node into the new grammar.

    An EMPTY `fallbacks` array is not enabling, which is the contract's
    own wording and the reason the predicate reads the PARSED array rather
    than the presence of the key.
    """
    return bool(fallbacks) or any(name in table for name in _ENABLING_KEYS)


def _fallbacks(*, table: Mapping[str, Any], key: str) -> tuple[AcpCandidate, ...] | str:
    """Parse the ordered `fallbacks` array, preserving configured order.

    A present-but-wrong-typed `fallbacks` refuses even for an otherwise
    legacy entry. That is deliberate: the value is unreadable, so the only
    two honest answers are "refuse" and "silently drop the operator's
    fallback configuration", and the second is the failure this whole
    feature exists to prevent.
    """
    if _FALLBACKS_KEY not in table:
        return ()
    raw = table[_FALLBACKS_KEY]
    if not isinstance(raw, list):
        return f"{key}.{_FALLBACKS_KEY} must be an array of candidate tables; got {raw!r}"
    entries = cast("list[object]", raw)
    candidates: list[AcpCandidate] = []
    for index, entry in enumerate(entries):
        parsed = parse_fallback_candidate(entry=entry, key=f"{key}.{_FALLBACKS_KEY}[{index}]")
        if isinstance(parsed, str):
            return parsed
        candidates.append(parsed)
    return tuple(candidates)


def _enabled_entry_refusal(*, table: Mapping[str, Any], key: str) -> str | None:
    """The closed-key and committed-secret refusals an ENABLED entry answers to.

    The secret scan reads the entry's OWN committed `command` / `args` /
    `env` here, which is where a refusal can name the configuration line.
    The RESOLVED primary is scanned again at attach time, because a layer
    below this one can contribute env this entry never mentions.
    """
    unknown = sorted(set(table) - NODE_ENTRY_KEYS)
    if unknown:
        return (
            f"{key} carries unknown key {unknown[0]!r}; allowed keys are "
            f"{', '.join(sorted(NODE_ENTRY_KEYS))}"
        )
    command = table.get("command")
    if command is not None and not isinstance(command, str):
        return f"{key}.command must be a string; got {command!r}"
    args = () if table.get("args") is None else string_tuple(value=table["args"])
    if args is None:
        return f"{key}.args must be an array of strings; got {table['args']!r}"
    empty: Mapping[str, str] = {}
    env = empty if table.get("env") is None else string_map(value=table["env"])
    if env is None:
        return f"{key}.env must be a table of string to string; got {table['env']!r}"
    return adapter_secret_refusal(command=command or "", args=args, env=env, key=key)
