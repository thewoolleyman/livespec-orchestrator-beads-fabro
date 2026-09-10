"""Attaching identity and the fallback chain to an ALREADY-RESOLVED primary.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" opens with the ordering rule this module exists to make
structural: "Resolve the primary before attaching the chain." Candidate
zero comes through the existing workflow-default, `codex_models`,
repository `command`/`env`/`args` and per-dispatch layers in their current
order; ONLY THEN may identity metadata and `fallbacks` attach. A
fallback-only `acp_nodes` table must not shadow a `codex_models` primary
or restore the workflow default.

That is why this takes an `AcpNodeResolution` -- the finished output of
`_acp_node_layers` -- rather than participating in the merge. There is no
code path here that can change a rendered byte of candidate zero, so
"fallback-only configuration cannot replace the primary" is not a rule
that has to be tested for every field: the field does not exist.

THE THREE REFUSALS, and why each fires here rather than at parse time:

- A LEGACY `--acp-node` STRING on a new-grammar-enabled node. Only this
  layer knows which nodes the command line overrode. The contract keeps
  the legacy spelling valid for a node with no new-grammar metadata and
  refuses it for one that has any, because the string carries no stable
  candidate or domain identity -- and it must not become hold-exempt or
  retain stale metadata, so the refusal comes before any identity
  attaches.
- A FALLBACK-ENABLED ARBITRARY PRIMARY WITH NO EXPLICIT IDENTITY. Whether
  the primary is arbitrary is a fact about the RESOLVED bytes, which parse
  time cannot see.
- A DUPLICATE ENTITLEMENT PAIR WITHIN ONE NODE. The primary's identity may
  arrive from the built-in table rather than from configuration, so the
  complete identity set for a node exists only after attachment. Reuse
  ACROSS nodes stays legal and is checked per node for exactly that
  reason.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import (
    IDENTITY_FIELDS,
    AcpCandidate,
    AcpCandidateIdentity,
)
from livespec_orchestrator_beads_fabro.commands._acp_candidate_secrets import (
    adapter_secret_refusal,
)
from livespec_orchestrator_beads_fabro.commands._acp_chain_digests import (
    full_chain_digest,
    primary_generation_digest,
    redacted_structural_record,
)
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import AcpNodeOverlay
from livespec_orchestrator_beads_fabro.commands._acp_node_chains import EMPTY_CHAIN, AcpNodeChain
from livespec_orchestrator_beads_fabro.commands._acp_node_layers import (
    AcpNodeResolution,
    ResolvedAcpNode,
)

__all__: list[str] = [
    "AcpChainResolution",
    "ResolvedAcpChain",
    "attach_acp_chains",
]

_CONFIG_PREFIX = "dispatcher.acp_nodes"


@dataclass(frozen=True, kw_only=True)
class ResolvedAcpChain:
    """One node's resolved candidate zero, its ordered fallbacks, its digests."""

    node: str
    primary: AcpCandidate
    fallbacks: tuple[AcpCandidate, ...]
    enabled: bool
    primary_generation: str
    full_chain: str
    redacted: Mapping[str, object]


@dataclass(frozen=True, kw_only=True)
class AcpChainResolution:
    """Every ACP node's candidate chain for one dispatch."""

    chains: Mapping[str, ResolvedAcpChain]

    @property
    def redacted_nodes(self) -> Mapping[str, Mapping[str, object]]:
        """The structural record for each node whose adapter must be redacted.

        Only new-grammar-enabled nodes appear. A no-fallback legacy node
        keeps v107's journal behaviour verbatim, which is what the
        contract means by retaining the arbitrary-adapter env behaviour
        and Scenario 88 unchanged.
        """
        return {node: chain.redacted for node, chain in self.chains.items() if chain.enabled}


def attach_acp_chains(
    *,
    resolution: AcpNodeResolution,
    chains: Mapping[str, AcpNodeChain],
    dispatch: Mapping[str, AcpNodeOverlay],
    builtins: Mapping[str, AcpCandidateIdentity],
) -> AcpChainResolution | str:
    """Attach identity and fallbacks to every resolved node, or refuse.

    Nodes are visited in sorted order so a configuration with two faults
    always refuses on the same one, which keeps a refusal message
    reproducible across dispatches.
    """
    attached: dict[str, ResolvedAcpChain] = {}
    for node in sorted(resolution.nodes):
        one = _attach_one(
            node=node,
            resolved=resolution.nodes[node],
            chain=chains.get(node, EMPTY_CHAIN),
            overridden=node in dispatch,
            builtins=builtins,
        )
        if isinstance(one, str):
            return one
        attached[node] = one
    return AcpChainResolution(chains=attached)


def _attach_one(
    *,
    node: str,
    resolved: ResolvedAcpNode,
    chain: AcpNodeChain,
    overridden: bool,
    builtins: Mapping[str, AcpCandidateIdentity],
) -> ResolvedAcpChain | str:
    """Attach one node's chain to its already-resolved adapter, or refuse."""
    refusal = _preconditions_refusal(
        node=node, resolved=resolved, chain=chain, overridden=overridden, builtins=builtins
    )
    if refusal is not None:
        return refusal
    primary = AcpCandidate(
        adapter=resolved.adapter,
        identity=chain.identity or builtins.get(resolved.rendered),
        signatures=chain.signatures,
        pricing=chain.pricing,
    )
    duplicate = _duplicate_identity_refusal(node=node, primary=primary, fallbacks=chain.fallbacks)
    if duplicate is not None:
        return duplicate
    generation = primary_generation_digest(primary=primary)
    full_chain = full_chain_digest(primary=primary, fallbacks=chain.fallbacks)
    return ResolvedAcpChain(
        node=node,
        primary=primary,
        fallbacks=chain.fallbacks,
        enabled=chain.enabled,
        primary_generation=generation,
        full_chain=full_chain,
        redacted=redacted_structural_record(
            resolved=resolved,
            primary_generation=generation,
            full_chain=full_chain,
            fallback_count=len(chain.fallbacks),
        ),
    )


def _preconditions_refusal(
    *,
    node: str,
    resolved: ResolvedAcpNode,
    chain: AcpNodeChain,
    overridden: bool,
    builtins: Mapping[str, AcpCandidateIdentity],
) -> str | None:
    """Every refusal that must fire BEFORE any identity attaches to this node."""
    if not chain.enabled:
        return None
    if overridden:
        return (
            f"--acp-node overrides node {node!r} with a legacy adapter string, but "
            f"{_CONFIG_PREFIX}.{node} carries fallback-priority metadata; the legacy "
            "string carries no stable candidate or availability identity and is refused "
            "for a new-grammar-enabled node"
        )
    secret = adapter_secret_refusal(
        command=resolved.adapter.command,
        args=resolved.adapter.args,
        env=resolved.adapter.env,
        key=f"{_CONFIG_PREFIX}.{node} resolved adapter",
    )
    if secret is not None:
        return secret
    if chain.fallbacks and chain.identity is None and resolved.rendered not in builtins:
        return (
            f"{_CONFIG_PREFIX}.{node} declares fallbacks, but its resolved primary adapter "
            f"is not a built-in; an arbitrary primary must declare {', '.join(IDENTITY_FIELDS)} "
            "rather than retain a replaced built-in's identity"
        )
    return None


def _duplicate_identity_refusal(
    *, node: str, primary: AcpCandidate, fallbacks: tuple[AcpCandidate, ...]
) -> str | None:
    """Refuse one node repeating an `(availability_key, candidate_key)` pair.

    Reuse across NODES is intentional and untouched: this scans one node's
    own chain, so two nodes naming the same shared entitlement both pass
    while one node naming it twice cannot.
    """
    seen: set[tuple[str, str]] = set()
    for candidate in (primary, *fallbacks):
        identity = candidate.identity
        if identity is None:
            continue
        if identity.pair in seen:
            return (
                f"{_CONFIG_PREFIX}.{node} repeats candidate identity "
                f"{identity.availability_key}/{identity.candidate_key} within one chain; "
                "identity reuse is intentional across nodes but not within one"
            )
        seen.add(identity.pair)
    return None
