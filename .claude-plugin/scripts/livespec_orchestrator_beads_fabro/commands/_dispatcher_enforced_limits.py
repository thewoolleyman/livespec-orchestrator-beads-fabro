"""What a parsed workflow graph's attributes MEAN as limits the engine enforces.

The reading half of the execution-budget derivation. `_dispatcher_dot_graph`
answers what the graph SAYS -- which statements, which key/value pairs -- and
`_dispatcher_execution_budget` answers how the visits COMPOSE into a wall
clock. In between sits exactly one question, and it is the one with all the
engine knowledge in it: given this node's attributes and this edge's condition,
what does the engine actually GUARANTEE?

WHAT COUNTS AS A GUARD, AND WHY THE TEST IS SO NARROW. A bound is only a bound
if the engine MUST enforce it. The pinned engine's condition AST carries And,
Or and Not (`fabro-workflow/src/condition.rs`), so a `node_visit_count`
substring appearing SOMEWHERE near an edge proves nothing: behind a `||` the
other arm can be taken forever, and under a `!` the sense is inverted. An
independent review reproduced a first build returning the SAME finite figure
for a genuine guard, for a guard behind a `||`, for one sitting in a `label`,
and for one in a trailing `//` comment -- three of which the engine would have
looped on without limit. So the condition arrives as an isolated attribute
value, and a bound is taken only from a FLAT CONJUNCTION -- no `||`, no unary
`!`, no parentheses -- one of whose conjuncts is exactly the visit-count
comparison. Every other shape yields NO bound, which leaves the edge
contributing its source's full visit count and makes an otherwise-uncapped
loop refuse.

A `>=` guard is likewise not a bound: it is the EXHAUST arm, taken once the
`<` arm stops firing, so reading it as a limit would bound the wrong
direction. And the count is 1-based -- `_dispatcher_plan_build` renders
`review_fix_visit_cap = review_fix_cap + 1` precisely so a cap of three fix
rounds becomes a `< 4` guard -- so a `< N` edge fires at most `N - 1` times.

TWO MECHANISMS SET THE ATTEMPT COUNT AND THE ENGINE PREFERS THE PRESET.
`build_retry_policy` consults `retry_policy` BEFORE `max_retries` /
`default_max_retries`, so a node declaring `max_retries=0` and
`retry_policy="standard"` runs FIVE attempts where a retry-budget-only reading
bills one. Both readings are taken here and the LARGER wins; see
`_node_attempts` for why that is the right kind of wrong.

EVERY UNREADABLE LIMIT REFUSES RATHER THAN DEFAULTING, because each of them
defaults in the direction that SHRINKS the maximum: an ignored `max_visits` is
a loop with no cap, and an unrecognised retry preset silently billed at one is
a node under-billed by however many attempts the preset really enforces.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import DotEdge, DotGraph

__all__: list[str] = [
    "NodeLimits",
    "edge_traversal_bound",
    "node_limits",
]

_TIMEOUT_ATTRIBUTE = "timeout"
_MAX_VISITS_ATTRIBUTE = "max_visits"
_MAX_RETRIES_ATTRIBUTE = "max_retries"
_DEFAULT_MAX_RETRIES_ATTRIBUTE = "default_max_retries"
_RETRY_POLICY_ATTRIBUTE = "retry_policy"
_CONDITION_ATTRIBUTE = "condition"

# How many handler executions each NAMED RETRY PRESET enforces, read off the
# pinned engine's `build_retry_policy` (`fabro-workflow/src/retry.rs` at
# 8869e88b2f7e383ec6fceb8d3f6f928dd0339b34).
#
# A name not in this table is REFUSED rather than defaulted: an unrecognised
# preset is a policy whose attempt count this derivation does not know, and
# guessing it low is the direction that shrinks the maximum.
_RETRY_PRESET_ATTEMPTS: Mapping[str, int] = {
    "standard": 5,
    "aggressive": 5,
    "linear": 3,
    "patient": 3,
    "none": 1,
}

# Disjunction, unary negation (`!=` is a comparison, not a negation) and
# grouping. Any of them and no bound is taken from the condition.
_UNSUPPORTED_CONDITION_RE = re.compile(r"\|\||!(?!=)|[()]")
_CONJUNCTION_SEPARATOR = "&&"
# The ONE comparison that counts as a guard, as the engine spells it: the
# fully-qualified field, `<` (never `<=`), and either a literal or a workflow
# input reference. Composed with an explicit `+` because the whole pattern does
# not fit one line and implicit string concatenation is banned in this tree.
_VISIT_COUNT_FIELD = r"context\.internal\.node_visit_count"
_GUARD_BOUND = r"(?:(?P<literal>\d+)|\{\{[ \t]*inputs\.(?P<input>\w+)[ \t]*\}\})"
_VISIT_GUARD_RE = re.compile(_VISIT_COUNT_FIELD + r"[ \t]*<(?!=)[ \t]*" + _GUARD_BOUND)


@dataclass(frozen=True, kw_only=True)
class NodeLimits:
    """One declared node, reduced to what a wall-clock bound needs of it.

    `timed` is whether the node declares a `timeout` at all -- the VALUE comes
    from the dispatch's resolved `NodeTimeouts`, because the Dispatcher
    rewrites every committed literal into the per-dispatch payload. `attempts`
    is handler executions per visit. `max_visits` is the engine's hard entry
    cap, or None when the node declares none.
    """

    timed: bool
    attempts: int
    max_visits: int | None


def node_limits(*, graph: DotGraph) -> dict[str, NodeLimits] | str:
    """Reduce each parsed node to its timed/attempts/cap triple, or refuse.

    A `max_visits`, `max_retries` or `retry_policy` this module cannot read is
    a refusal rather than an ignored attribute: ignoring it would silently drop
    the only cap on a loop, which is the direction that shrinks the maximum.
    """
    graph_default = _count_from(attributes=graph.attributes, key=_DEFAULT_MAX_RETRIES_ATTRIBUTE)
    if isinstance(graph_default, str):
        return graph_default
    graph_preset = _preset_attempts(attributes=graph.attributes)
    if isinstance(graph_preset, str):
        return graph_preset
    default_attempts = 1 if graph_default is None else graph_default + 1
    limits: dict[str, NodeLimits] = {}
    for name, attributes in graph.nodes.items():
        resolved = _limits_for(
            attributes=attributes,
            default_attempts=default_attempts,
            graph_preset=graph_preset,
        )
        if isinstance(resolved, str):
            return resolved
        limits[name] = resolved
    return limits


def edge_traversal_bound(*, edge: DotEdge, graph_inputs: Mapping[str, int]) -> int | None:
    """How often this edge can fire, or None when nothing necessarily bounds it.

    `None` is the answer for every condition this parse cannot prove constrains
    the edge -- an absent condition, a disjunction, a negation, a parenthesised
    group, or a conjunction carrying no visit-count comparison. The bound is the
    SMALLEST of the comparisons a flat conjunction does carry, because every
    conjunct of a conjunction is enforced.

    `graph_inputs` resolves a templated guard -- the shipped graph writes the
    review loop's cap as a workflow input rather than a literal. An input the
    mapping does not name yields no bound rather than a guessed one.
    """
    expression = edge.attributes.get(_CONDITION_ATTRIBUTE)
    if expression is None or _UNSUPPORTED_CONDITION_RE.search(expression) is not None:
        return None
    bounds = [
        bound
        for conjunct in expression.split(_CONJUNCTION_SEPARATOR)
        if (bound := _guard_bound(conjunct=conjunct.strip(), graph_inputs=graph_inputs)) is not None
    ]
    return min(bounds) if bounds else None


def _limits_for(
    *,
    attributes: Mapping[str, str],
    default_attempts: int,
    graph_preset: int | None,
) -> NodeLimits | str:
    retries = _count_from(attributes=attributes, key=_MAX_RETRIES_ATTRIBUTE)
    if isinstance(retries, str):
        return retries
    cap = _count_from(attributes=attributes, key=_MAX_VISITS_ATTRIBUTE)
    if isinstance(cap, str):
        return cap
    preset = _preset_attempts(attributes=attributes)
    if isinstance(preset, str):
        return preset
    return NodeLimits(
        timed=_TIMEOUT_ATTRIBUTE in attributes,
        attempts=_node_attempts(
            retries=retries,
            preset=preset,
            default_attempts=default_attempts,
            graph_preset=graph_preset,
        ),
        max_visits=cap,
    )


def _preset_attempts(*, attributes: Mapping[str, str]) -> int | None | str:
    """A declared `retry_policy`'s attempt count, None when absent, else a refusal."""
    name = attributes.get(_RETRY_POLICY_ATTRIBUTE)
    if name is None:
        return None
    attempts = _RETRY_PRESET_ATTEMPTS.get(name)
    if attempts is None:
        return (
            f"the resolved workflow graph declares `{_RETRY_POLICY_ATTRIBUTE}="
            f"{name}`, a retry policy whose attempt count this derivation does "
            f"not know, so the run has no attempt budget to size a credential "
            f"lifetime against"
        )
    return attempts


def _node_attempts(
    *,
    retries: int | None,
    preset: int | None,
    default_attempts: int,
    graph_preset: int | None,
) -> int:
    """One node's handler executions per visit, taking the LARGER reading.

    Two mechanisms can set this and the engine consults them in one order:
    `build_retry_policy` reads `retry_policy` BEFORE the retry budget, so a
    preset OVERRIDES `max_retries` rather than combining with it. This takes
    the maximum of the two readings anyway, which agrees with the engine
    wherever the preset is the larger one and over-bills -- never under-bills --
    wherever it is not. A maximum is the one direction a credential floor may
    safely be wrong in, and the precedence between a GRAPH-level preset and a
    node's own retry budget is not something this derivation should have to be
    right about.
    """
    budget = default_attempts if retries is None else retries + 1
    declared_preset = preset if preset is not None else graph_preset
    return budget if declared_preset is None else max(budget, declared_preset)


def _count_from(*, attributes: Mapping[str, str], key: str) -> int | None | str:
    raw = attributes.get(key)
    if raw is None:
        return None
    if not raw.isdigit():
        return (
            f"the resolved workflow graph's `{key}` is {raw!r}, which is not a "
            f"count this derivation can bound a run with"
        )
    return int(raw)


def _guard_bound(*, conjunct: str, graph_inputs: Mapping[str, int]) -> int | None:
    """One conjunct's traversal bound, or None when it is not a visit guard.

    `fullmatch` rather than a search: a conjunct that merely CONTAINS the
    comparison is a larger expression this parse has not accounted for, and the
    whole point of reading conjuncts one at a time is that each is evaluated
    whole.
    """
    guard = _VISIT_GUARD_RE.fullmatch(conjunct)
    if guard is None:
        return None
    literal = guard.group("literal")
    if literal is not None:
        return max(int(literal) - 1, 0)
    resolved = graph_inputs.get(guard.group("input"))
    return None if resolved is None else max(resolved - 1, 0)
