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

THE NO-FALLBACK PATH IS THE COMMON ONE AND IT IS A TOTAL NO-OP UNLESS A
SESSION-HEADROOM POLICY WAS SUPPLIED. When no node carries a non-empty fallback
field and no policy arrives, `viable` is true, no graph is read, no refusal can
fire, and nothing about admission changes. This is the additive guarantee the
contract opens with, expressed as an early return rather than as a series of
conditions that happen to be false.

THE ONE THING THAT PATH STILL DOES is assess session headroom, because the
headroom clause's coverage rule names exactly the repositories it would
otherwise miss: "assess every otherwise-selectable covered candidate on an
admission-required ACP node, including covered fallbacks and built-in
single-candidate nodes without fallback metadata". `_no_fallback_graded` below
owns that path and records why it filters on headroom ALONE.

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
from livespec_orchestrator_beads_fabro.commands._acp_hold_records import AcpAvailabilityHold
from livespec_orchestrator_beads_fabro.commands._acp_node_chains import AcpNodeChain
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom import SessionHeadroomReading
from livespec_orchestrator_beads_fabro.commands._acp_success_critical import (
    derive_admission_required,
    derive_success_critical,
)
from livespec_orchestrator_beads_fabro.commands._acp_workflow_graph import parse_workflow_graph

__all__: list[str] = [
    "AcpPreflightVerdict",
    "build_acp_preflight_verdict",
    "chain_source_refusal_verdict",
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
    # The live records THIS evaluation filtered against, carried so the
    # scheduled-reevaluation derivation grades the very holds the nodes above
    # were filtered by. A consumer re-reading the ledger for them would be
    # taking a SECOND measurement, and a record retiring between the two reads
    # would then be surfaced by one half and acted on by the other.
    holds: tuple[AcpAvailabilityHold, ...] = ()
    unobservable: tuple[Mapping[str, object], ...] = ()
    refusal: str | None = None
    assessed_credentials: Mapping[str, str] = field(default_factory=dict)
    headroom_assessments: tuple[SessionHeadroomReading, ...] = ()
    session_headroom_floor_percent: int | None = None
    # The SECOND governing dial, carried for the same reason and keyed on the
    # same distinction: `None` means no policy was supplied, never "the horizon
    # is zero". A horizon of 0 is a ratified setting that disables projection
    # skips while retaining the computation and its record.
    session_headroom_horizon_minutes: int | None = None

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


def chain_source_refusal_verdict(
    *, declared: Mapping[str, AcpNodeChain], refusal: str
) -> AcpPreflightVerdict:
    """The verdict an unreadable chain-source resolution produces.

    TWO DIRECTIONS, DECIDED BY WHAT THE REPOSITORY DECLARED. A repository that
    declared a fallback-enabled chain is REFUSED, which is this feature's
    fail-closed configuration refusal: before-claim is strictly earlier than
    before-run, and a claim taken on configuration that cannot resolve has to
    be released again.

    A repository that declared NONE gets the viable no-op instead, and that
    direction is the whole reason this decision is a function rather than one
    constructor call. Such a repository is only here because a session-headroom
    policy arrived, and the faults reachable in the resolution -- an
    unresolvable workflow variant, an unreadable workflow config, a refused
    overlay table -- belong to gates that report them UNDER THEIR OWN STAGE
    later in the dispatch. Surfacing one here would re-attribute a
    workflow-registry fault to the ACP preflight, which reports it with the
    wrong remedy and SILENTLY DISPLACES the stage that owns it: measured on
    `tests/integration/test_named_workflow_variants.py`, a reserved-name
    registry fault stopped being reported by the registry gate at all. An
    additive headroom assessment must not move another gate's refusal.

    `declared` is the DECLARED table rather than a boolean, because the one
    question asked of it -- whether any chain is enabled -- is the same
    question `build_acp_preflight_verdict` asks of the resolved chains, and
    answering it in the one place that must decide on it keeps a caller from
    spelling it a second way.
    """
    if not any(chain.enabled for chain in declared.values()):
        return no_fallback_verdict()
    return AcpPreflightVerdict(fallback_enabled=True, refusal=refusal)


def build_acp_preflight_verdict(
    *,
    chains: Mapping[str, ResolvedAcpChain],
    graph_text: str | None,
    ledger: AcpHoldLedger,
    inputs: PreflightInputs,
) -> AcpPreflightVerdict:
    """Filter every node's chain once, and grade the success-critical ones.

    The graph is read only once a node is actually fallback-enabled or a
    session-headroom policy arrived, so a repository on the v107 path with no
    policy never pays for a derivation whose answer cannot change its dispatch
    -- and never refuses on a graph shape it does not use.
    """
    if not any(chain.enabled for chain in chains.values()):
        return _no_fallback_graded(chains=chains, graph_text=graph_text, inputs=inputs)
    return _graded(
        fallback_enabled=True,
        chains=chains,
        graph_text=graph_text,
        ledger=ledger,
        inputs=inputs,
    )


def _no_fallback_graded(
    *,
    chains: Mapping[str, ResolvedAcpChain],
    graph_text: str | None,
    inputs: PreflightInputs,
) -> AcpPreflightVerdict:
    """The verdict a repository declaring no fallback-enabled chain gets.

    THE SESSION-HEADROOM POLICY IS STILL APPLIED, and that is the one thing
    this path does beyond the v107 no-op. The headroom clause requires the
    Dispatcher to assess "built-in single-candidate nodes without fallback
    metadata", so a repository whose every node resolves to one built-in Claude
    adapter is squarely inside it -- and short-circuiting left exactly those
    repositories dispatching with no headroom brake at all. Measured
    2026-10-17: a fresh dispatch in a sibling repository that declares no
    chains journaled ZERO assessment records while this repository's own
    evaluations journaled one apiece.

    WITH NO POLICY IT IS STILL THE TOTAL NO-OP, which is what keeps the
    additive guarantee intact and what leaves wait attention and idle-factory
    free of any external call. The test is for the POLICY's absence and never
    for a falsy floor, because a floor of 0 is a ratified setting that disables
    the skip while retaining the reading and its journal row.

    IT FILTERS ON HEADROOM ALONE, which is why the inputs are rebuilt rather
    than forwarded and why no ledger reaches this path at all. The three other
    filters cost nothing to evaluate, so a verdict that applied them here would
    answer DIFFERENTLY depending on whether a policy had been supplied -- and
    "Idle-factory and wait attention consume this identical verdict" is the
    fallback-priority clause's own requirement, with both of those consumers
    supplying none. The headroom clause ratifies that one asymmetry in as many
    words ("Snapshot composition MUST NOT issue a live usage request", with the
    wait surfaced from the recorded evaluation); nothing else may acquire one.
    A typed or legacy availability record on a v107 repository therefore keeps
    reaching the gate that already grades it, scoped to the candidates the
    dispatch renders.

    AND IT FAILS OPEN ON A REFUSAL, the opposite direction from the
    fallback-enabled path and chosen rather than incidental. Both refusals
    `_graded` can reach are about the GRAPH -- an unreadable one, or a
    success-critical derivation that cannot grade its shape -- and a dispatch
    needs neither: `admission_required` exists to decide admission, so these are
    conditions a v107 repository has never been held to. Refusing on one would
    turn an additive assessment into a new refusal class for every such
    repository, and the condition most likely to fire is a legitimate workflow
    shape this derivation does not cover rather than a fault. The CONFIGURATION
    refusals, which a dispatch does need and which `prepare_acp_nodes` refuses
    on in its own right, never reach here -- `_dispatcher_acp_preflight` returns
    those before resolving a verdict at all. No reading is spent on a fail-open
    either: both refusal arms below precede the candidate filter.
    """
    if inputs.headroom is None:
        return no_fallback_verdict()
    graded = _graded(
        fallback_enabled=False,
        chains=chains,
        graph_text=graph_text,
        ledger=AcpHoldLedger(holds=(), unobservable=(), observation_ids=frozenset()),
        inputs=PreflightInputs(builtin_pairs=inputs.builtin_pairs, headroom=inputs.headroom),
    )
    return no_fallback_verdict() if graded.refusal is not None else graded


def _graded(
    *,
    fallback_enabled: bool,
    chains: Mapping[str, ResolvedAcpChain],
    graph_text: str | None,
    ledger: AcpHoldLedger,
    inputs: PreflightInputs,
) -> AcpPreflightVerdict:
    """Derive this graph's graded node sets and filter every chain against them.

    ONE grader for both callers rather than one apiece. They differ only in
    `fallback_enabled`, in the inputs they hand down and in what they do with a
    refusal, and a second copy is how the no-fallback path comes to grade a
    different node set -- or to name a different exhausted order -- than the
    path every assertion about this verdict was written against.
    """
    if graph_text is None:
        return AcpPreflightVerdict(
            fallback_enabled=fallback_enabled,
            unobservable=ledger.unobservable,
            refusal=_MISSING_GRAPH_REFUSAL,
        )
    graph = parse_workflow_graph(text=graph_text)
    critical = derive_success_critical(graph=graph)
    if isinstance(critical, str):
        return AcpPreflightVerdict(
            fallback_enabled=fallback_enabled,
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
        fallback_enabled=fallback_enabled,
        nodes=preflights,
        success_critical=critical.nodes,
        admission_required=required,
        exhausted=_exhausted(preflights=preflights, required=required),
        holds=ledger.holds,
        unobservable=ledger.unobservable,
        assessed_credentials=dict(assessed),
        headroom_assessments=_headroom_assessments(preflights=preflights),
        session_headroom_floor_percent=(
            None if inputs.headroom is None else inputs.headroom.floor_percent
        ),
        session_headroom_horizon_minutes=(
            None if inputs.headroom is None else inputs.headroom.horizon_minutes
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
