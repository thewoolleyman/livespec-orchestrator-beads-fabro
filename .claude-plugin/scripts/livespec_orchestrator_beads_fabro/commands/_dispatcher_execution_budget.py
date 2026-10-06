"""The resolved workflow graph's own maximum wall clock, derived not assumed.

WHAT THIS ANSWERS, and why nothing else in the tree answers it. "How long can
one dispatch of this workflow run?" had two existing answers and neither is a
maximum. `_node_timeouts.derive_fabro_timeout_seconds` sums a HAND-WRITTEN
`_WORST_CASE_VISITS` table that a graph edit silently invalidates -- the table
still assumes three janitor visits and two fix attempts while the shipped graph
returns to `fix` from `proof_capture` and `proof_verify` as well, and protects
`fix` with `max_visits=10`. And `CODEX_FRESHNESS_RUN_BUDGET_SECONDS` was the
`implement` node's own ceiling, standing in for the whole run on the reasoning
that the dominant node dominates. A credential gate sized off either number is
sized off a guess.

This module derives the bound from the GRAPH THE DISPATCH WILL RUN -- read
structurally by `_dispatcher_dot_graph`, never scanned for substrings -- using
only mechanisms Fabro actually enforces:

- `max_visits` on a node, which ABORTS the run at entry rather than running the
  node, so it is a hard cap on that node's visits.
- `max_retries` on a node (and the graph-level `default_max_retries`), which
  re-executes the HANDLER inside one visit, so it multiplies the node's wall
  clock per visit rather than its visit count.
- A `context.internal.node_visit_count < N` conjunct in an edge's `condition`,
  which stops that edge firing once the source node has been visited N times.
  The count is 1-based in this engine -- `_dispatcher_plan_build` renders
  `review_fix_visit_cap = review_fix_cap + 1` precisely so a cap of three fix
  rounds becomes a `< 4` guard -- so such an edge fires at most `N - 1` times.
- Reachability itself: a node is entered at most as often as its predecessors
  are visited, and a TERMINAL node (no outgoing edge) ends the run, so it is
  entered at most once however many predecessors point at it.

WHAT COUNTS AS A GUARD, and what an attribute is allowed to mean, lives next
door in `_dispatcher_enforced_limits`. That split is the cohesion seam of this
derivation: reading the engine's guarantees out of one node's attributes or one
edge's condition is a different concern from composing those guarantees into a
wall clock, and all of the engine knowledge sits on that side.

WHAT THIS FIGURE IS NOT: AN ENFORCED TOTAL. It is an ALLOWANCE derived from
per-operation bounds, and a sum of separately-bounded sub-operations is not a
deadline anything enforces. The gap is not small and it is not closeable by
deriving harder, so it must not be papered over by whoever consumes this:

- `sandbox_git.rs` spends `commit_timeout_ms` INDEPENDENTLY on `git add`, on
  `git diff --cached` and on `git commit`, then another ten seconds on
  `git_head_sha`. This repository's `commit_timeout = "10m"` is therefore a
  1810-second ceiling per checkpoint, not a 600-second one -- before
  `write_file` / `delete_file` are counted at all.
- `node_handler.rs` resolves artifact context BEFORE its optional handler
  timeout, and does context and edge selection after it. Neither is inside the
  node timeout.
- `acp.rs` runs a changed-file scan on BOTH sides of `run_acp_turn`
  (`changed_files.rs`: thirty seconds each, plus an optional five-second
  last-file lookup), and a bounded credential mint before the turn.
- Retry backoff is configured separately again, and the jitter in
  `fabro-util/src/backoff.rs` multiplies the capped delay by [0.5, 1.5) -- so
  the sixty-second base cap admits ninety.

`per_attempt_overhead_seconds` is therefore a CALLER-SUPPLIED input covering
those per-attempt costs, and supplying it proves nothing on its own. A caller
sizing a CREDENTIAL against this figure owes an actually enforced absolute
credential-use deadline beside it -- one that also covers the later node starts
an inter-stage or queue delay pushes out -- or an honest refusal. What it must
not do is call the allowance a maximum.

WHY AN UNACCOUNTED-FOR GRAPH REFUSES RATHER THAN DEFAULTING. Everything this
derivation cannot stand behind comes back as a refusal STRING: syntax the parse
does not model, a cycle nothing bounds, an edge naming a node the graph never
declares (DOT admits one, and dropping it would delete an executable path from
a figure still presented as a maximum), a non-integer visit or retry budget,
and a graph with no timed node at all. The one thing this module must never do
is name a number it cannot stand behind: a credential gate sized off an
invented default is the defect this module exists to retire, wearing a
derivation's clothes.

THE DERIVED FIGURE IS AN UPPER BOUND, NOT A PREDICTION. Visits are summed over
distinct predecessors, which over-counts whenever two predecessors cannot both
reach their own maxima in one run; no run reaches it. That is the correct
direction for a credential floor and the wrong one for a cost estimate -- do
not reuse this number as a forecast.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph
from livespec_orchestrator_beads_fabro.commands._dispatcher_enforced_limits import (
    NodeLimits,
    edge_traversal_bound,
    node_limits,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import NodeTimeouts

__all__: list[str] = [
    "VISIT_CEILING",
    "ExecutionBudget",
    "execution_budget",
]

# The visit count past which a graph is reported UNBOUNDED rather than
# budgeted. The fixpoint below is monotone, so a cycle with no enforced cap
# grows without limit and crosses this on its own; a graph whose genuine bound
# is above it would be budgeted at over a thousand visits of a single node,
# which is not a workflow anyone meant to write. Either way the answer is the
# same refusal, which is why one constant serves both.
VISIT_CEILING = 1000


@dataclass(frozen=True, kw_only=True)
class ExecutionBudget:
    """One workflow's derived maximum wall clock, with the counts behind it.

    `node_visits` and `node_attempts` ride along so a diagnostic or a journal
    record can show WHICH node dominates the figure. A bare number invites the
    reader to re-derive it by hand, and a hand derivation of this graph is the
    thing that was wrong.
    """

    seconds: int
    node_visits: Mapping[str, int]
    node_attempts: Mapping[str, int]


def execution_budget(
    *,
    graph_text: str,
    timeouts: NodeTimeouts,
    per_attempt_overhead_seconds: int,
    graph_inputs: Mapping[str, int] | None = None,
) -> ExecutionBudget | str:
    """Derive the graph's maximum wall clock, or refuse naming what defeated it.

    Each node's duration comes from `timeouts`, never from the literal in the
    committed text: the Dispatcher rewrites every one of those literals into the
    per-dispatch payload (`_dispatcher_graph_render`), so reading the committed
    value would budget a graph no run executes. The committed `timeout`
    attribute is read for ONE thing -- whether the node has a duration at all.

    `graph_inputs` resolves a templated visit guard -- the shipped graph writes
    the review loop's cap as a workflow input rather than a literal. An input
    this mapping does not name leaves that edge UNGUARDED, which is the
    conservative direction: the edge then contributes its source's full visit
    count and the destination's own `max_visits` is what bounds it.
    """
    parsed = parse_dot_graph(text=graph_text)
    if isinstance(parsed, str):
        return parsed
    nodes = node_limits(graph=parsed)
    if isinstance(nodes, str):
        return nodes
    if not any(node.timed for node in nodes.values()):
        return (
            "the resolved workflow graph declares no node carrying a timeout, "
            "so it has no wall clock to bound"
        )
    edges = [
        (
            edge.source,
            edge.destination,
            edge_traversal_bound(edge=edge, graph_inputs=graph_inputs or {}),
        )
        for edge in parsed.edges
    ]
    undeclared = _undeclared_endpoints(nodes=nodes, edges=edges)
    if undeclared is not None:
        return undeclared
    visits = _visit_bounds(nodes=nodes, edges=edges)
    if isinstance(visits, str):
        return visits
    attempts = {name: node.attempts for name, node in nodes.items() if node.timed}
    seconds = sum(
        visits[name]
        * node.attempts
        * (timeouts.seconds_for(node=name) + per_attempt_overhead_seconds)
        for name, node in nodes.items()
        if node.timed
    )
    return ExecutionBudget(
        seconds=seconds,
        node_visits={name: visits[name] for name in attempts},
        node_attempts=attempts,
    )


def _undeclared_endpoints(
    *,
    nodes: Mapping[str, NodeLimits],
    edges: list[tuple[str, str, int | None]],
) -> str | None:
    """Refuse an edge naming a node the graph never declares.

    DOT lets an edge introduce a node implicitly, and such a node has no
    attributes to read -- no timeout, no `max_visits`. Dropping the edge would
    remove an executable path from the figure; billing the node would invent
    attributes for it. Neither is honest, so the graph is refused.
    """
    endpoints = {name for source, dest, _ in edges for name in (source, dest)}
    unknown = sorted(endpoints - set(nodes))
    if not unknown:
        return None
    return (
        f"the resolved workflow graph has edges naming nodes it never declares "
        f"({', '.join(unknown)}), so the derived maximum would omit a path the "
        f"run can execute"
    )


def _visit_bounds(
    *,
    nodes: Mapping[str, NodeLimits],
    edges: list[tuple[str, str, int | None]],
) -> dict[str, int] | str:
    """The least fixpoint of "entered at most as often as its predecessors are".

    Monotone by construction -- every sweep can only raise a bound -- so the
    loop either reaches a fixpoint or grows past `VISIT_CEILING`, and there is
    no third outcome to guard against with an iteration counter.
    """
    incoming = _incoming(nodes=nodes, edges=edges)
    terminal = _terminal(nodes=nodes, edges=edges)
    bounds = dict.fromkeys(nodes, 0)
    while True:
        changed = False
        for name in nodes:
            value = _entry_bound(
                bounds=bounds,
                incoming=incoming[name],
                node=nodes[name],
                terminal=name in terminal,
            )
            if value <= bounds[name]:
                continue
            if value > VISIT_CEILING:
                return (
                    f"the resolved workflow graph does not bound how often node "
                    f"{name!r} can be entered: no max_visits on it, and no edge "
                    f"reaching it carries a condition that necessarily limits its "
                    f"visit count, so the run has no finite wall clock to size a "
                    f"credential lifetime against"
                )
            bounds[name] = value
            changed = True
        if not changed:
            return bounds


def _entry_bound(
    *,
    bounds: Mapping[str, int],
    incoming: Mapping[str, int | None],
    node: NodeLimits,
    terminal: bool,
) -> int:
    if not incoming:
        # No predecessor at all: an entry node, entered exactly once.
        value = 1
    else:
        value = sum(
            bounds[source] if bound is None else min(bounds[source], bound)
            for source, bound in incoming.items()
        )
    if node.max_visits is not None:
        value = min(value, node.max_visits)
    return min(value, 1) if terminal else value


def _incoming(
    *,
    nodes: Mapping[str, NodeLimits],
    edges: list[tuple[str, str, int | None]],
) -> dict[str, dict[str, int | None]]:
    """Each node's distinct predecessors, with the loosest bound of each pair.

    Parallel edges between one pair collapse rather than add, because one visit
    of the source takes exactly ONE of its outgoing edges: three guarded arms
    from `review` to `needs_human` are three ways to spend one visit, not three
    visits' worth of entries. Every endpoint is a declared node by the time this
    runs -- `_undeclared_endpoints` has already refused a graph where one is not.
    """
    incoming: dict[str, dict[str, int | None]] = {name: {} for name in nodes}
    for source, destination, bound in edges:
        _merge_bound(pair=incoming[destination], source=source, bound=bound)
    return incoming


def _merge_bound(*, pair: dict[str, int | None], source: str, bound: int | None) -> None:
    if source not in pair:
        pair[source] = bound
        return
    existing = pair[source]
    pair[source] = None if bound is None or existing is None else max(existing, bound)


def _terminal(
    *,
    nodes: Mapping[str, NodeLimits],
    edges: list[tuple[str, str, int | None]],
) -> set[str]:
    """Nodes with no outgoing edge: entering one ends the run, so once at most."""
    sources = {source for source, _, _ in edges}
    return {name for name in nodes if name not in sources}
