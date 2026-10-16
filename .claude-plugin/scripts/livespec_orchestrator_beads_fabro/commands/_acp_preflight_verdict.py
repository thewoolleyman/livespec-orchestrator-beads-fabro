"""ONE pure verdict: can every admission-required ACP chain still be run?

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": "every ACP node potentially reachable in the submitted graph is
admission-required, success-critical or not. Before submission, every ACP node
potentially reachable in the submitted graph MUST have an eligible candidate.
... Idle-factory and wait attention consume this identical verdict."

TWO SETS RIDE THE VERDICT AND ONLY ONE OF THEM GRADES. `exhausted` is computed
against `admission_required` -- the reachable set -- because that is what
decides a dispatch; `success_critical` is the dominator set, carried because
the refusal journal and the per-node selection record name it and because the
two facts are not interchangeable. A reader that joined on the wrong one would
report a conditional repair node's outage as a loss of the green terminal.

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

THE HEADROOM FLOOR IS CARRIED, AND `None` MEANS "NO POLICY WAS SUPPLIED" --
never "the floor is zero". A floor of 0 is a real, ratified setting that
disables the skip while retaining the reading, so collapsing the two would make
a caller that deliberately disabled the filter indistinguishable from wait
attention and idle-factory, which supply no policy and must issue no usage
request at all. The journal writer keys on exactly that distinction.

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
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom import SessionHeadroomReading
from livespec_orchestrator_beads_fabro.commands._acp_success_critical import (
    derive_admission_required,
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
    "be read, so the admission-required ACP nodes cannot be derived"
)


@dataclass(frozen=True, kw_only=True)
class AcpPreflightVerdict:
    """What one evaluation of every node's candidate chain concluded."""

    fallback_enabled: bool
    nodes: tuple[NodePreflight, ...] = ()
    success_critical: tuple[str, ...] = ()
    admission_required: tuple[str, ...] = ()
    exhausted: tuple[str, ...] = ()
    unobservable: tuple[Mapping[str, object], ...] = ()
    refusal: str | None = None
    assessed_credentials: Mapping[str, str] = field(default_factory=dict)
    headroom_assessments: tuple[SessionHeadroomReading, ...] = ()
    session_headroom_floor_percent: int | None = None

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
            "no candidate remains for admission-required ACP "
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
    graph = parse_workflow_graph(text=graph_text)
    critical = derive_success_critical(graph=graph)
    if isinstance(critical, str):
        return AcpPreflightVerdict(
            fallback_enabled=True,
            unobservable=ledger.unobservable,
            refusal=critical,
        )
    required = derive_admission_required(graph=graph, start=critical.start)
    assessed: dict[str, str] = {}
    preflights = tuple(
        filter_node_candidates(chain=chains[node], inputs=inputs, assessed=assessed)
        for node in sorted(chains)
    )
    return AcpPreflightVerdict(
        fallback_enabled=True,
        nodes=preflights,
        success_critical=critical.nodes,
        admission_required=required,
        exhausted=_exhausted(preflights=preflights, required=required),
        unobservable=ledger.unobservable,
        assessed_credentials=dict(assessed),
        headroom_assessments=_headroom_assessments(preflights=preflights),
        session_headroom_floor_percent=(
            None if inputs.headroom is None else inputs.headroom.floor_percent
        ),
    )


def _headroom_assessments(
    *, preflights: tuple[NodePreflight, ...]
) -> tuple[SessionHeadroomReading, ...]:
    """Every distinct credential's reading across every node, in node order.

    Deduplicated BY CREDENTIAL IDENTITY rather than by value, because that is
    the unit the clause counts -- "One assessment per distinct projected
    credential per admission evaluation" -- and two nodes sharing one credential
    must contribute one row to the journal rather than one each.
    """
    seen: dict[str, SessionHeadroomReading] = {}
    for preflight in preflights:
        for reading in preflight.assessments:
            _ = seen.setdefault(reading.credential_identity, reading)
    return tuple(seen.values())


def _exhausted(
    *, preflights: tuple[NodePreflight, ...], required: tuple[str, ...]
) -> tuple[str, ...]:
    """The admission-required nodes left with no candidate, in graph order.

    An admission-required node the chain table does not mention is NOT
    exhausted: it resolved through the existing layers to exactly one
    candidate, which no typed record can cover because it carries no typed
    identity. Only a node this evaluation actually filtered can report an empty
    chain.
    """
    empty = {preflight.node for preflight in preflights if preflight.exhausted}
    return tuple(node for node in required if node in empty)
