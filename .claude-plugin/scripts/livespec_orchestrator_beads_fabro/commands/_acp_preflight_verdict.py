"""ONE pure verdict: can every success-critical ACP chain still be run?

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": "Admission and rework admission refuse before claim only when at
least one such chain has no candidate. ... Idle-factory and wait attention
consume this identical verdict."

FOUR CONSUMERS, ONE ANSWER, AND THAT IS THE POINT. Admission, rework admission,
wait attention and idle-factory each need to know whether the factory can run
this repository's work. Four look-alike predicates would disagree the first
time one of them was updated -- and they would disagree SILENTLY, because each
one's answer is individually plausible. So the decision is computed once, as a
value, and the four consumers read fields off it.

THE VERDICT IS A VALUE, NOT AN ACTION. Nothing here reads a file, writes a
journal, probes a credential or reaches a network; every input arrives as a
parameter. That is what lets wait attention and idle-factory consume it without
an "additional credential probe or external call", and what makes two
invocations against an unchanged store render byte-identical rows.

THE NO-FALLBACK PATH IS THE COMMON ONE AND IT IS A TOTAL NO-OP. When no node
carries a non-empty fallback field, `viable` is true, no graph is read, no
refusal can fire, and nothing about admission changes. This is the additive
guarantee the contract opens with, expressed as an early return rather than as
a series of conditions that happen to be false.

UNKNOWN OBSERVATION VERSIONS RIDE THROUGH, UNREAD. The hold ledger surfaces a
record whose `schema_version` this build does not know as UNOBSERVABLE rather
than dropping it, and this verdict carries that set verbatim onto every
consumer. It is deliberately NOT folded into `viable`: interpreting an unknown
record on v1's field meanings is the silent misreading the contract forbids,
and treating it as ordinary empty hold state is the silent DISCARD it equally
forbids. Carried and uninterpreted is the only honest third answer.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from livespec_orchestrator_beads_fabro.commands._acp_candidate_preflight import (
    NodePreflight,
    PreflightInputs,
    filter_node_candidates,
)
from livespec_orchestrator_beads_fabro.commands._acp_chain_resolution import ResolvedAcpChain
from livespec_orchestrator_beads_fabro.commands._acp_hold_ledger import AcpHoldLedger
from livespec_orchestrator_beads_fabro.commands._acp_success_critical import (
    derive_success_critical,
)
from livespec_orchestrator_beads_fabro.commands._acp_workflow_graph import parse_workflow_graph

__all__: list[str] = [
    "AcpPreflightVerdict",
    "build_acp_preflight_verdict",
    "no_fallback_verdict",
]

_MISSING_GRAPH_REFUSAL = (
    "workflow graph is unsupported for fallback: the dispatch's workflow graph could not "
    "be read, so the success-critical ACP nodes cannot be derived"
)


@dataclass(frozen=True, kw_only=True)
class AcpPreflightVerdict:
    """What one evaluation of every node's candidate chain concluded."""

    fallback_enabled: bool
    nodes: tuple[NodePreflight, ...] = ()
    success_critical: tuple[str, ...] = ()
    exhausted: tuple[str, ...] = ()
    unobservable: tuple[Mapping[str, object], ...] = ()
    refusal: str | None = None
    assessed_credentials: Mapping[str, str] = field(default_factory=dict)

    @property
    def viable(self) -> bool:
        """Whether a dispatch may proceed: the graph resolved and no chain is empty."""
        return self.refusal is None and not self.exhausted

    @property
    def detail(self) -> str:
        """The deterministic explanation a refusal is reported with."""
        if self.refusal is not None:
            return self.refusal
        return (
            "no candidate remains for success-critical ACP "
            f"{'node' if len(self.exhausted) == 1 else 'nodes'} "
            f"{', '.join(self.exhausted)}"
        )

    def node_preflight(self, *, node: str) -> NodePreflight | None:
        """This node's filtered chain, or `None` when the graph carries no such node."""
        for preflight in self.nodes:
            if preflight.node == node:
                return preflight
        return None


def no_fallback_verdict() -> AcpPreflightVerdict:
    """The viable no-op verdict a repository with no fallback configuration gets."""
    return AcpPreflightVerdict(fallback_enabled=False)


def build_acp_preflight_verdict(
    *,
    chains: Mapping[str, ResolvedAcpChain],
    graph_text: str | None,
    ledger: AcpHoldLedger,
    inputs: PreflightInputs,
) -> AcpPreflightVerdict:
    """Filter every node's chain once, and grade the success-critical ones.

    The graph is read only once a node is actually fallback-enabled, so a
    repository on the v107 path never pays for a derivation whose answer cannot
    change its dispatch -- and never refuses on a graph shape it does not use.
    """
    if not any(chain.enabled for chain in chains.values()):
        return no_fallback_verdict()
    if graph_text is None:
        return AcpPreflightVerdict(
            fallback_enabled=True,
            unobservable=ledger.unobservable,
            refusal=_MISSING_GRAPH_REFUSAL,
        )
    critical = derive_success_critical(graph=parse_workflow_graph(text=graph_text))
    if isinstance(critical, str):
        return AcpPreflightVerdict(
            fallback_enabled=True,
            unobservable=ledger.unobservable,
            refusal=critical,
        )
    assessed: dict[str, str] = {}
    preflights = tuple(
        filter_node_candidates(chain=chains[node], inputs=inputs, assessed=assessed)
        for node in sorted(chains)
    )
    return AcpPreflightVerdict(
        fallback_enabled=True,
        nodes=preflights,
        success_critical=critical.nodes,
        exhausted=_exhausted(preflights=preflights, critical=critical.nodes),
        unobservable=ledger.unobservable,
        assessed_credentials=dict(assessed),
    )


def _exhausted(
    *, preflights: tuple[NodePreflight, ...], critical: tuple[str, ...]
) -> tuple[str, ...]:
    """The success-critical nodes left with no candidate, in graph order.

    A success-critical node the chain table does not mention is NOT exhausted:
    it resolved through the existing layers to exactly one candidate, which no
    typed record can cover because it carries no typed identity. Only a node
    this evaluation actually filtered can report an empty chain.
    """
    empty = {preflight.node for preflight in preflights if preflight.exhausted}
    return tuple(node for node in critical if node in empty)
