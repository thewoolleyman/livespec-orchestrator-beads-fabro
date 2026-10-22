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
    HEADROOM_SKIP,
    LEGACY_HOLD_SKIP,
    PROBE_SKIP,
    TYPED_HOLD_SKIP,
    NodePreflight,
    SkippedCandidate,
)
from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import (
    AcpCandidate,
    AcpCandidateIdentity,
)
from livespec_orchestrator_beads_fabro.commands._acp_chain_digests import (
    selection_identity_digest,
)
from livespec_orchestrator_beads_fabro.commands._acp_chain_resolution import ResolvedAcpChain
from livespec_orchestrator_beads_fabro.commands._acp_preflight_verdict import AcpPreflightVerdict
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom_records import (
    session_headroom_skip_fields,
)

__all__: list[str] = [
    "ACP_NODE_SELECTION_STAGE",
    "SelectedAcpCandidate",
    "acp_node_selection_record",
    "select_acp_candidates",
    "selected_candidate_identities",
]

# The journal stage one dispatch's per-node selections are recorded under.
# Distinct from the adapter-resolution stage on purpose: that record says what
# each node's CHAIN resolved to, and this one says which position of it ran.
ACP_NODE_SELECTION_STAGE = "acp-node-selection"

# The two skip reasons a DURABLE availability record produced. They are the only
# ones the clause calls holds, which is why the projection keys on this set
# rather than on "not ephemeral": a reason added later must be classified
# deliberately rather than inherited into the hold list by default.
_HOLD_SKIPS: frozenset[str] = frozenset({TYPED_HOLD_SKIP, LEGACY_HOLD_SKIP})


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

    A VERDICT THAT IS NOT FALLBACK-ENABLED SELECTS NOTHING, and is treated here
    exactly as an ABSENT one: every node keeps the primary the three layers
    resolved. Selecting AMONG candidates is the fallback-priority clause's
    feature and a repository that declared no chain has nothing to select among,
    so this is the same additive guarantee `prepare_acp_nodes` records for an
    absent verdict -- "no selection is applied, so every node keeps the
    configured primary the three layers resolved, byte-identical".

    It is a condition rather than an inference from an empty node set, because
    such a verdict DOES carry filtered nodes since the session-headroom clause
    began assessing built-in single-candidate nodes. Reading those as a
    selection instruction changes nothing a dispatch renders -- the only
    no-fallback verdict that reaches here is a viable one, whose every chain
    still holds its primary -- but it compares the ADMISSION-time resolution
    against this launch's, and those two legitimately differ when a dispatch is
    handed a committed workflow manifest the default-variant precedence does not
    reach. Measured on `tests/integration/test_node_timeouts_scenario89.py`,
    which supplies exactly such a manifest: five dispatches died at `acp-nodes`
    reporting that the repository's candidate configuration had changed, on
    repositories that had declared none.
    """
    selected: dict[str, SelectedAcpCandidate] = {}
    for node in sorted(chains):
        one = _select_one(
            chain=chains[node],
            preflight=(
                None
                if verdict is None or not verdict.fallback_enabled
                else verdict.node_preflight(node=node)
            ),
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


def selected_candidate_identities(
    *, selected: Mapping[str, SelectedAcpCandidate]
) -> Mapping[str, AcpCandidateIdentity]:
    """Each node's SELECTED candidate identity, for the run's entitlement labels.

    THE SELECTED CANDIDATE AND NEVER POSITION ZERO. The labels are the only
    venue a provider-limit attribution can read the executed candidate off, so
    a label naming the candidate this dispatch SKIPPED would record a ceiling
    against an allowance nothing spent -- holding an intact account while the
    exhausted one stayed unheld. Both identities are well-formed, so no surface
    downstream could tell the two apart; the only defence is taking the
    identity from the selection rather than from the chain.

    A node whose selected candidate carries NO identity contributes nothing.
    That is the conservative legacy posture of `AcpCandidate.identity`: an
    identity-less arbitrary adapter has no stable entitlement, so there is no
    key to record and a guessed one would join a run to an allowance nobody
    declared.
    """
    return {
        node: one.candidate.identity
        for node, one in sorted(selected.items())
        if one.candidate.identity is not None
    }


def acp_node_selection_record(
    *, selected: Mapping[str, SelectedAcpCandidate], dispatch_id: str | None = None
) -> dict[str, object]:
    """ONE record per dispatch, carrying every node's selection.

    ONE RECORD AND NOT ONE PER NODE. "which candidate did this dispatch select"
    is a question about the dispatch, and spreading the answer across a row per
    node would make a reader collate them before they could answer it -- and
    would leave no way to tell a node whose row is missing from a dispatch that
    never reached that node. Every node the selection visited appears, including
    the ones that stayed at position zero.

    EVERY SKIP IS CLASSIFIED, AND THE THREE LISTS ARE NOT INTERCHANGEABLE. A
    durable availability record is a HOLD; a usage-window reading is a HEADROOM
    skip, which the clause forbids representing as an observed hold; and a
    credential-probe refusal is neither -- it is a local observation about a
    credential, with no typed availability cause. Collapsing any pair would make
    a credential that is merely busy indistinguishable from an entitlement a
    provider refused. The three together also account for EVERY position the
    selection passed over, so `selected_index` is never a number with nothing
    behind it.
    """
    record: dict[str, object] = {
        "stage": ACP_NODE_SELECTION_STAGE,
        "selections": {node: _selection_fields(one=one) for node, one in sorted(selected.items())},
    }
    if dispatch_id is not None:
        record["dispatch_id"] = dispatch_id
    return record


def _selection_fields(*, one: SelectedAcpCandidate) -> dict[str, object]:
    """One node's selection, as the clause enumerates it."""
    identity = one.candidate.identity
    return {
        "selection_identity": one.selection_identity,
        "selected_index": one.index,
        "selected_availability_key": None if identity is None else identity.availability_key,
        "selected_candidate_key": None if identity is None else identity.candidate_key,
        "primary_generation_digest": one.primary_generation,
        "full_chain_digest": one.full_chain,
        "holds": [_hold_fields(skip=skip) for skip in one.skipped if skip.reason in _HOLD_SKIPS],
        "headroom_skips": [
            session_headroom_skip_fields(skip=skip)
            for skip in one.skipped
            if skip.reason == HEADROOM_SKIP
        ],
        "probe_skips": [
            _probe_fields(skip=skip) for skip in one.skipped if skip.reason == PROBE_SKIP
        ],
    }


def _hold_fields(*, skip: SkippedCandidate) -> dict[str, object]:
    """One candidate a DURABLE availability record skipped, with its typed cause."""
    return {
        "availability_key": skip.availability_key,
        "candidate_key": skip.candidate_key,
        "reason": skip.reason,
        "cause": skip.cause,
        "scope": skip.scope,
        "hold_key": skip.hold_key,
    }


def _probe_fields(*, skip: SkippedCandidate) -> dict[str, object]:
    """One candidate the admission credential probe skipped, by its CONDITION.

    No typed availability cause, scope or hold key: the probe creates no
    observed record, so there is nothing of that shape to report and a null one
    would invite a reader to join against a ledger where it matches nothing.
    """
    return {
        "availability_key": skip.availability_key,
        "candidate_key": skip.candidate_key,
        "condition": skip.condition,
    }
