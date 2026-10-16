"""WHICH ONE of a node's candidates this dispatch renders, as a pure decision.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" -> "Per-node selection": "For each node, the Dispatcher MUST choose
the first candidate in configured order that has no covering live hold, has
satisfied any outstanding post-expiry availability confirmation, has not been
skipped by the admission-time credential-usability probe for this evaluation,
and has not been skipped by the admission session-headroom filter for this
evaluation. ... Selection is made once per dispatch from one consistent read of
the availability evidence."

THE FOUR CONDITIONS ARE NOT RE-EVALUATED HERE, AND THAT IS THE DESIGN. Each one
is a question about live evidence, a credential probe or a usage reading, and
`_acp_candidate_preflight` already answered all four at ONE fixed evaluation
time. This module reads the surviving list off the verdict admission produced
and takes its head. Re-asking any of the four would be a SECOND read of the
availability evidence, which the clause forbids in as many words -- and the
disagreement would be invisible, because both reads produce a perfectly
well-formed candidate.

THE POSITION IS FOUND BY EQUALITY, NEVER BY IDENTITY. The verdict is resolved
before the claim, from its own read of the repository's configuration, while the
chains reach this module from the dispatch's own read at materialization. The
two therefore hold DIFFERENT OBJECTS describing one configuration, so an `is`
search would miss on every real dispatch. An equality search that MISSES is a
different fact and is refused: the chain was edited between the two reads, and
there is no position to report.

FOUR ANSWERS, NOT TWO, AND THE TWO EMPTY-CHAIN ARMS ARE OPPOSITES. A node the
verdict never filtered keeps its configured primary -- that is the additive
guarantee for every caller that resolved no verdict, and for a legacy node in a
fallback-enabled repository. A node the verdict filtered to NOTHING is refused
when the graph makes it admission-required, because the clause says the
Dispatcher "MUST NOT render or start a candidate covered by a live hold,
including for conditional repair or adjudication nodes" -- and admission already
refuses such an item before claim, so reaching here means something is wrong and
falling back to the held primary would run exactly what was held. But a node
PROVEN UNREACHABLE in the submitted graph "imposes no candidate requirement", so
its empty chain keeps its primary rather than killing a dispatch over a node
this graph cannot execute.

THE SELECTION IDENTITY IS A FUNCTION OF THE SELECTION AND NOTHING ELSE. It
digests the node, the chosen candidate and the full-chain digest, so two
dispatches that selected the same position of the same chain render the same
identity and a dispatch that fell back renders a different one. Nothing about
the moment it was taken enters it, which is what makes it comparable across runs
rather than merely unique.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._acp_candidate_preflight import (
    NodePreflight,
    SkippedCandidate,
)
from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidate
from livespec_orchestrator_beads_fabro.commands._acp_chain_digests import (
    selection_identity_digest,
)
from livespec_orchestrator_beads_fabro.commands._acp_chain_resolution import ResolvedAcpChain
from livespec_orchestrator_beads_fabro.commands._acp_preflight_verdict import AcpPreflightVerdict

__all__: list[str] = [
    "SelectedAcpCandidate",
    "select_acp_candidates",
]


@dataclass(frozen=True, kw_only=True)
class SelectedAcpCandidate:
    """The ONE candidate a node renders, its position, and what it passed over.

    `skipped` is the LEADING run of this node's skips -- the candidates the
    filter rejected before the survivor it chose -- and never the whole skip
    list. The filter keeps grading after the first survivor, so a later skip
    describes a candidate this selection never considered; reporting it would
    say a hold had moved the selection when it had not.

    The two digests ride along rather than being looked up again by whoever
    records this, because a record that re-derived them from a second read of
    the chain could report a generation this selection was not taken against.
    """

    node: str
    index: int
    candidate: AcpCandidate
    selection_identity: str
    primary_generation: str
    full_chain: str
    skipped: tuple[SkippedCandidate, ...]


def select_acp_candidates(
    *, chains: Mapping[str, ResolvedAcpChain], verdict: AcpPreflightVerdict | None
) -> Mapping[str, SelectedAcpCandidate] | str:
    """Choose one candidate per node, or refuse naming the node that defeated it.

    Nodes are visited in sorted order so a configuration with two faults always
    refuses on the same one, which keeps a refusal reproducible across
    dispatches -- the same reason `attach_acp_chains` sorts.
    """
    selected: dict[str, SelectedAcpCandidate] = {}
    for node in sorted(chains):
        one = _select_one(
            chain=chains[node],
            preflight=None if verdict is None else verdict.node_preflight(node=node),
            admission_required=() if verdict is None else verdict.admission_required,
        )
        if isinstance(one, str):
            return one
        selected[node] = one
    return selected


def _select_one(
    *,
    chain: ResolvedAcpChain,
    preflight: NodePreflight | None,
    admission_required: tuple[str, ...],
) -> SelectedAcpCandidate | str:
    """This node's selected candidate, or the refusal its chain earned."""
    ordered = (chain.primary, *chain.fallbacks)
    if preflight is None:
        return _selection(chain=chain, index=0, candidate=chain.primary, skipped=())
    if not preflight.candidates:
        if chain.node in admission_required:
            return (
                f"ACP node {chain.node!r} has no eligible candidate: every one of its "
                f"{len(ordered)} configured candidates was skipped by this dispatch's "
                "admission evaluation, and a candidate covered by a live hold must not be "
                "rendered"
            )
        return _selection(chain=chain, index=0, candidate=chain.primary, skipped=())
    chosen = preflight.candidates[0]
    if chosen not in ordered:
        return (
            f"ACP node {chain.node!r} selected a candidate this dispatch did not resolve: the "
            "repository's candidate configuration changed between the admission evaluation and "
            "this launch, so the selected position cannot be identified"
        )
    index = ordered.index(chosen)
    return _selection(
        chain=chain, index=index, candidate=chosen, skipped=tuple(preflight.skipped[:index])
    )


def _selection(
    *,
    chain: ResolvedAcpChain,
    index: int,
    candidate: AcpCandidate,
    skipped: tuple[SkippedCandidate, ...],
) -> SelectedAcpCandidate:
    """One node's selection, with its stable identity computed over it."""
    return SelectedAcpCandidate(
        node=chain.node,
        index=index,
        candidate=candidate,
        selection_identity=selection_identity_digest(
            node=chain.node, candidate=candidate, full_chain=chain.full_chain
        ),
        primary_generation=chain.primary_generation,
        full_chain=chain.full_chain,
        skipped=skipped,
    )
