"""Which ACP nodes a run CANNOT reach its green terminal without.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": "The workflow MUST expose the ACP nodes that dominate every green
terminal path. Those are the success-critical nodes; for the reserved workflow
they are `dod_gate`, `implement`, `proof_capture`, `review`, `proof_verify`,
each of which dominates every green terminal path. ... An unsupported or
ambiguous workflow graph MUST refuse fallback-enabled dispatch instead of
guessing."

DOMINANCE IS THE DEFINITION, AND IT IS NOT REACHABILITY. A node that merely
appears on SOME green path is not success-critical: `fix` and `review_fix` sit
on real green paths and a run that never goes Red reaches `exit` without
either. The success-critical set is the set of nodes on EVERY green path,
which is exactly the classical dominator set of the green terminal. Computing
it as a dominator set rather than enumerating paths also terminates on a cyclic
graph, which this one is -- `janitor -> fix -> janitor` and
`review -> disposition -> review_fix -> janitor -> review` are both live loops.

THIS IS NO LONGER THE ADMISSION-REQUIRED SET, and the distinction is the whole
reason the two derivations are separate modules. v127 widened admission to
every ACP node POTENTIALLY REACHABLE in the submitted graph, which is
`_acp_admission_required`'s question and is strictly wider than this one. The
dominator set still has its own consumers -- the reached-node termination and
the attention surfaces -- so it is computed and carried unchanged rather than
replaced. `reachable_from` is public because both derivations need it: the
reachable subgraph is the domain the dominator iteration is restricted to, and
it is the admission-required set's entire definition.

WHY THE REFUSALS ARE SHAPED AROUND COUNTING. Every fault this can meet is a
graph that does not have exactly one entry and exactly one green exit, and the
two failure directions are told apart deliberately: NONE is unsupported --
there is no green terminal to dominate, so no set exists -- while MORE THAN ONE
is ambiguous, because a set does exist for each and choosing between them is
precisely the guess the contract forbids. A green terminal carrying an outgoing
edge is unsupported for the same reason: it is not a terminal, so the graph is
not the shape this derivation understands.

The derivation refuses rather than fails soft. An empty success-critical set
would admit every dispatch, which is the fail-OPEN direction on the one gate
that exists to hold work back.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._acp_workflow_graph import (
    GREEN_TERMINAL_SHAPE,
    START_SHAPE,
    WorkflowGraph,
)

__all__: list[str] = [
    "SuccessCriticalNodes",
    "derive_success_critical",
    "dominators",
    "reachable_from",
]


@dataclass(frozen=True, kw_only=True)
class SuccessCriticalNodes:
    """The success-critical ACP nodes, and the two graph ends they came from."""

    start: str
    green_terminal: str
    nodes: tuple[str, ...]


def derive_success_critical(*, graph: WorkflowGraph) -> SuccessCriticalNodes | str:
    """The ACP nodes dominating the green terminal, or a deterministic refusal.

    The refusal text names the fault, the count and the offending node names,
    so a reader of a refused dispatch can see which graph shape was rejected
    without re-deriving anything.
    """
    starts = graph.with_shape(shape=START_SHAPE)
    terminals = graph.with_shape(shape=GREEN_TERMINAL_SHAPE)
    end_refusal = _end_refusal(starts=starts, terminals=terminals)
    if end_refusal is not None:
        return end_refusal
    start, terminal = starts[0], terminals[0]
    if graph.successors(node=terminal):
        return (
            f"workflow graph is unsupported for fallback: green terminal {terminal!r} "
            f"declares outgoing edges to {_names(names=graph.successors(node=terminal))}, "
            "so it is not a terminal"
        )
    dominance = dominators(graph=graph, start=start)
    if terminal not in dominance:
        return (
            f"workflow graph is unsupported for fallback: green terminal {terminal!r} "
            f"is unreachable from start {start!r}"
        )
    acp = graph.acp_names
    dominating = dominance[terminal]
    return SuccessCriticalNodes(
        start=start,
        green_terminal=terminal,
        nodes=tuple(name for name in graph.names if name in acp and name in dominating),
    )


def dominators(*, graph: WorkflowGraph, start: str) -> Mapping[str, frozenset[str]]:
    """Each start-reachable node's dominator set, by iteration to a fixed point.

    Restricted to the reachable subgraph on purpose: an unreachable node has no
    path from the start at all, so every node would vacuously dominate it and
    its set would say nothing. Keeping it out also guarantees that every node
    in the working set other than the start has at least one predecessor that
    is itself in the set, which is what makes the intersection below total.
    """
    reachable = reachable_from(graph=graph, start=start)
    everything = frozenset(reachable)
    sets: dict[str, frozenset[str]] = {name: everything for name in reachable}
    sets[start] = frozenset({start})
    changed = True
    while changed:
        changed = False
        for name in reachable:
            if name == start:
                continue
            incoming = [sets[source] for source in graph.predecessors(node=name) if source in sets]
            shared = incoming[0]
            for other in incoming[1:]:
                shared = shared & other
            updated = shared | {name}
            if updated != sets[name]:
                sets[name] = updated
                changed = True
    return sets


def reachable_from(*, graph: WorkflowGraph, start: str) -> tuple[str, ...]:
    """Every node reachable from the start, in first-discovery order.

    Public because the admission-required derivation in
    `_acp_admission_required` is defined on exactly this set, and a second
    traversal there could disagree with this one about which nodes a submitted
    graph can reach -- a disagreement neither answer would announce, because
    each is a well-formed node list.
    """
    order: list[str] = [start]
    seen = {start}
    cursor = 0
    while cursor < len(order):
        for target in graph.successors(node=order[cursor]):
            if target not in seen:
                seen.add(target)
                order.append(target)
        cursor += 1
    return tuple(order)


def _end_refusal(*, starts: tuple[str, ...], terminals: tuple[str, ...]) -> str | None:
    """The counting faults of the graph's two ends, or `None` when both resolve."""
    for role, shape, found in (
        ("start", START_SHAPE, starts),
        ("green terminal", GREEN_TERMINAL_SHAPE, terminals),
    ):
        if not found:
            return (
                f"workflow graph is unsupported for fallback: it declares no {role} node "
                f"(shape={shape})"
            )
        if len(found) > 1:
            return (
                f"workflow graph is ambiguous for fallback: it declares {len(found)} "
                f"{role} nodes (shape={shape}): {_names(names=found)}"
            )
    return None


def _names(*, names: tuple[str, ...]) -> str:
    return ", ".join(sorted(names))
