"""What the engine GUARANTEES, read off one node's attributes or one edge's condition.

These are the falsifying controls of the execution-budget derivation, and they
live here rather than at the composition layer because every one of them is a
statement about the ENGINE rather than about the graph's shape. A bound is only
a bound if the engine must enforce it; the available mistake is to find a
`node_visit_count` or a `max_visits` substring somewhere near an edge or a node
and call it one.

An independent review reproduced exactly that against a first build: a guard
sitting in a `label`, a guard behind a `||` beside an unconditional
alternative, and a guard in a trailing `//` comment each produced the SAME
finite figure as a genuine conjunctive guard -- while the engine, whose
condition AST carries And, Or and Not, would have looped without limit in three
of the four. The same review found `max_visits=3` read out of a label, and a
`retry_policy` preset ignored entirely although `build_retry_policy` consults
it BEFORE the retry budget. Each of those shapes has a case here, and each
negative case is paired with the positive one it is measured against: a
derivation that refused everything would pass the negatives vacuously.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import (
    DotEdge,
    DotGraph,
    parse_dot_graph,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_enforced_limits import (
    NodeLimits,
    edge_traversal_bound,
    node_limits,
)


def _graph(*, text: str) -> DotGraph:
    parsed = parse_dot_graph(text=text)
    assert not isinstance(parsed, str), parsed
    return parsed


def _limits(*, node_attributes: str = "", graph_attributes: str = "") -> dict[str, NodeLimits]:
    resolved = node_limits(
        graph=_graph(
            text=f"digraph G {{\n  graph [{graph_attributes}]\n  a [{node_attributes}]\n}}\n"
        )
    )
    assert not isinstance(resolved, str), resolved
    return resolved


def _limits_refusal(*, node_attributes: str = "", graph_attributes: str = "") -> str:
    refusal = node_limits(
        graph=_graph(
            text=f"digraph G {{\n  graph [{graph_attributes}]\n  a [{node_attributes}]\n}}\n"
        )
    )
    assert isinstance(refusal, str), refusal
    return refusal


def _bound(*, condition: str | None, graph_inputs: dict[str, int] | None = None) -> int | None:
    attributes = {} if condition is None else {"condition": condition}
    return edge_traversal_bound(
        edge=DotEdge(source="a", destination="b", attributes=attributes),
        graph_inputs=graph_inputs or {},
    )


def test_a_node_declaring_a_timeout_is_timed() -> None:
    assert _limits(node_attributes='timeout="1800s"')["a"].timed is True


def test_a_node_declaring_no_timeout_is_not_timed() -> None:
    assert _limits(node_attributes="shape=Mdiamond")["a"].timed is False


def test_a_max_visits_attribute_is_the_node_cap() -> None:
    assert _limits(node_attributes="max_visits=3")["a"].max_visits == 3


def test_a_node_declaring_no_max_visits_has_no_cap() -> None:
    assert _limits(node_attributes="shape=box")["a"].max_visits is None


def test_max_visits_inside_a_label_is_not_a_node_cap() -> None:
    """A label is documentation. Measured against a first build that read it."""
    assert _limits(node_attributes='label="max_visits=3"')["a"].max_visits is None


def test_a_retry_budget_bills_one_more_attempt_than_it_declares() -> None:
    assert _limits(node_attributes="max_retries=1")["a"].attempts == 2


def test_a_node_declaring_nothing_bills_one_attempt() -> None:
    assert _limits(node_attributes="shape=box")["a"].attempts == 1


def test_a_graph_level_retry_default_reaches_a_node_declaring_none() -> None:
    assert _limits(graph_attributes="default_max_retries=2")["a"].attempts == 3


def test_a_node_retry_budget_overrides_the_graph_default() -> None:
    """`default_max_retries` is a DEFAULT; a node declaring its own wins.

    Unlike the preset reading beside it, this precedence is documented engine
    behaviour (`build_retry_policy` falls through to `default_max_retries`
    only when the node declares no `max_retries`), so it is honoured rather
    than maximised -- taking the larger here would over-bill every node in a
    graph that sets a generous default and then tightens one node.
    """
    limits = _limits(node_attributes="max_retries=0", graph_attributes="default_max_retries=2")
    assert limits["a"].attempts == 1


def test_a_retry_preset_overrides_a_smaller_retry_budget() -> None:
    """`build_retry_policy` reads `retry_policy` BEFORE the retry budget.

    A node declaring `max_retries=0` and `retry_policy="standard"` executes up
    to five attempts. Billing it one -- which a retry-budget-only reading does
    -- undercounts that node's wall clock five-fold.
    """
    assert _limits(node_attributes='max_retries=0, retry_policy="standard"')["a"].attempts == 5


def test_a_weaker_retry_preset_never_lowers_a_larger_retry_budget() -> None:
    """The larger reading wins: a maximum may over-bill, never under-bill."""
    assert _limits(node_attributes='max_retries=1, retry_policy="none"')["a"].attempts == 2


def test_each_known_retry_preset_bills_its_own_attempt_count() -> None:
    for preset, attempts in (
        ("standard", 5),
        ("aggressive", 5),
        ("linear", 3),
        ("patient", 3),
        ("none", 1),
    ):
        assert _limits(node_attributes=f'retry_policy="{preset}"')["a"].attempts == attempts, preset


def test_a_graph_level_retry_preset_reaches_a_node_declaring_none() -> None:
    """Whether the engine applies one is not settled, so bill it: over, never under."""
    assert _limits(graph_attributes='retry_policy="linear"')["a"].attempts == 3


def test_an_unknown_retry_preset_is_refused_rather_than_defaulted() -> None:
    assert "retry_policy=turbo" in _limits_refusal(node_attributes='retry_policy="turbo"')


def test_an_unknown_graph_level_retry_preset_is_refused() -> None:
    assert "retry_policy=warp" in _limits_refusal(graph_attributes='retry_policy="warp"')


def test_a_non_integer_visit_cap_is_refused_rather_than_ignored() -> None:
    """Ignoring an unreadable cap would drop the only bound on a loop."""
    assert "max_visits" in _limits_refusal(node_attributes='max_visits="three"')


def test_a_non_integer_retry_budget_is_refused() -> None:
    assert "max_retries" in _limits_refusal(node_attributes='max_retries="lots"')


def test_a_non_integer_graph_retry_default_is_refused() -> None:
    assert "default_max_retries" in _limits_refusal(graph_attributes='default_max_retries="none"')


def test_a_conjunctive_visit_guard_bounds_the_edge_one_below_its_literal() -> None:
    """The POSITIVE control every refusal below is measured against.

    The engine's visit count is 1-based -- `review_fix_visit_cap` is rendered
    as the configured cap PLUS ONE for exactly that reason -- so `< 3` admits
    two traversals.
    """
    assert _bound(condition="outcome=failed && context.internal.node_visit_count < 3") == 2


def test_a_guard_as_the_whole_condition_bounds_the_edge() -> None:
    assert _bound(condition="context.internal.node_visit_count < 3") == 2


def test_an_edge_with_no_condition_is_unbounded() -> None:
    assert _bound(condition=None) is None


def test_a_condition_carrying_no_visit_guard_is_unbounded() -> None:
    assert _bound(condition="outcome=failed") is None


def test_a_guard_behind_a_disjunction_is_not_a_bound() -> None:
    """`||` means the other arm can be taken forever; the guard constrains nothing."""
    assert _bound(condition="context.internal.node_visit_count < 3 || outcome=failed") is None


def test_a_negated_guard_is_not_a_bound() -> None:
    assert _bound(condition="!(context.internal.node_visit_count >= 3)") is None


def test_a_parenthesised_condition_is_not_read_as_a_bound() -> None:
    """Grouping changes which operator a conjunct belongs to; refuse rather than guess."""
    condition = "(context.internal.node_visit_count < 3 || outcome=failed) && outcome!=succeeded"
    assert _bound(condition=condition) is None


def test_an_exhaust_guard_is_not_read_as_a_bound() -> None:
    """`>=` is the arm taken once the loop stops, never a limit on it."""
    assert _bound(condition="context.internal.node_visit_count >= 3") is None


def test_a_less_than_or_equal_guard_is_not_read_as_a_bound() -> None:
    assert _bound(condition="context.internal.node_visit_count <= 3") is None


def test_a_bare_visit_count_without_the_context_path_is_not_a_bound() -> None:
    """`node_visit_count` alone is not the field the engine exposes."""
    assert _bound(condition="node_visit_count < 3") is None


def test_a_guard_embedded_in_a_larger_conjunct_is_not_a_bound() -> None:
    """Each conjunct is evaluated whole, so a partial match is not one."""
    assert _bound(condition="x context.internal.node_visit_count < 3") is None


def test_the_tightest_conjunct_governs_when_a_condition_carries_two_guards() -> None:
    """Every conjunct of a conjunction is enforced, so the smallest one binds."""
    condition = "context.internal.node_visit_count < 4 && context.internal.node_visit_count < 2"
    assert _bound(condition=condition) == 1


def test_a_templated_guard_resolves_from_the_supplied_inputs() -> None:
    condition = "context.internal.node_visit_count < {{ inputs.review_fix_visit_cap }}"
    assert _bound(condition=condition, graph_inputs={"review_fix_visit_cap": 4}) == 3


def test_an_unresolvable_templated_guard_yields_no_bound() -> None:
    """An input nobody supplied must not be guessed at."""
    condition = "context.internal.node_visit_count < {{ inputs.review_fix_visit_cap }}"
    assert _bound(condition=condition, graph_inputs={}) is None


def test_a_zero_guard_admits_no_traversal_rather_than_a_negative_one() -> None:
    assert _bound(condition="context.internal.node_visit_count < 0") == 0
