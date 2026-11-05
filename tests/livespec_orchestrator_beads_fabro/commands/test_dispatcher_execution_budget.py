"""The resolved workflow graph's maximum wall clock, derived from the graph.

Most cases drive `execution_budget` over a SYNTHETIC graph rather than the
shipped one, deliberately: the shipped graph changes, and a test asserting a
number read off it would fail for a graph edit that is not a defect. What must
hold across every edit is the DERIVATION -- that a visit cap caps, that a retry
multiplies a node's wall clock rather than its visit count, that a terminal
node is entered once, and that an unbounded cycle is refused instead of
defaulted. One case does read the shipped graph, and asserts only that the
parse reaches a finite answer over real syntax, which is the control that would
catch a parser quietly failing on the one graph this factory actually runs.

THE FALSIFYING CONTROLS ARE THE POINT OF THIS MODULE'S TEST SUITE. A bound is
only a bound if the engine MUST enforce it, and the available mistake is to
find a `node_visit_count` substring somewhere near an edge and call it one. An
independent review reproduced exactly that: a first build read the substring out
of arbitrary edge text, so a guard sitting in a `label`, a guard behind a `||`
beside an unconditional alternative, and a guard in a trailing `//` comment each
produced the SAME finite figure as a genuine conjunctive guard -- while the
engine, whose condition AST carries And, Or and Not, would have looped without
limit in three of the four. Each of those four shapes therefore has a case here,
and three of them assert that NO bound is taken.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._node_timeouts import NodeTimeouts

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_execution_budget"
_MODULE_PATH = (
    _REPO_ROOT
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_execution_budget.py"
)
_SHIPPED_GRAPH_PATH = (
    _REPO_ROOT
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "workflow.fabro"
)

_OVERHEAD = 30
_DEFAULT_TIMEOUT = 1800

# One loop bounded by an edge guard, one retrying node, one terminal reached
# from a node visited more than once. The `done` node's own `600s` literal is
# deliberately different from every other node's: the derivation resolves each
# node's timeout through `NodeTimeouts`, exactly as the payload renderer does,
# so a literal left in the committed graph must NOT reach the figure.
_GRAPH = """digraph G {
    graph [
        default_max_retries=0
        stall_timeout="7200s"
    ]

    start [shape=Mdiamond, label="Start"]
    exit  [shape=Msquare, label="Exit"]

    work [
        timeout="1800s"
        max_retries=1
    ]

    loop [
        timeout="1800s"
        max_visits=5
    ]

    done [
        timeout="600s"
    ]

    fail [
        timeout="1800s"
    ]

    start -> work
    work -> loop [label="again", condition="outcome!=succeeded && \
context.internal.node_visit_count < 3"]
    work -> fail [label="dead end"]
    work -> done
    loop -> work
    done -> exit
}
"""

# The one guarded edge of `_GRAPH`, verbatim, so every falsifying control below
# substitutes the WHOLE edge rather than a fragment of it and cannot silently
# match nothing.
_GUARDED_EDGE = (
    '    work -> loop [label="again", condition="outcome!=succeeded && '
    'context.internal.node_visit_count < 3"]\n'
)


def _with_edge(*, edge: str) -> str:
    """`_GRAPH` with its one guarded edge replaced by `edge`."""
    assert _GUARDED_EDGE in _GRAPH, "the control substitutes an edge the graph does not carry"
    return _GRAPH.replace(_GUARDED_EDGE, edge)


def _budget(
    *,
    graph_text: str = _GRAPH,
    timeouts: NodeTimeouts | None = None,
    graph_inputs: dict[str, int] | None = None,
) -> Any:
    module = importlib.import_module(_MODULE)
    return module.execution_budget(
        graph_text=graph_text,
        timeouts=timeouts if timeouts is not None else _timeouts(),
        per_attempt_overhead_seconds=_OVERHEAD,
        graph_inputs=graph_inputs,
    )


def _timeouts(*, configured: dict[str, int] | None = None) -> NodeTimeouts:
    return NodeTimeouts(
        configured=configured if configured is not None else {},
        stall_seconds=7200,
        stall_layer="default",
    )


def _unbounded_refusal(*, graph_text: str, graph_inputs: dict[str, int] | None = None) -> str:
    """Assert the graph was refused as unbounded, and return the refusal.

    `loop` carries `max_visits=5`, so a control that merely weakened the guard
    would still land on a finite figure and prove nothing. Every control below
    therefore removes that cap as well, which makes "unbounded" the ONLY honest
    answer for an edge the engine does not necessarily constrain -- and makes
    a finite result a falsification rather than a smaller number.
    """
    refusal = _budget(
        graph_text=graph_text.replace("        max_visits=5\n", ""), graph_inputs=graph_inputs
    )
    assert isinstance(refusal, str), f"expected an unbounded refusal, got {refusal!r}"
    return refusal


def test_budget_derives_from_visit_caps_retries_and_configured_timeouts() -> None:
    """The anchor: the figure is the graph's own enforced worst case.

    `work` is entered three times (once from `start`, twice from the
    guard-capped `loop`), runs twice per visit because it declares
    `max_retries=1`, and is therefore billed six attempts. `loop` is capped at
    two entries by the `< 3` guard rather than by its own `max_visits=5`, and
    `fail` is entered once despite three `work` visits because it ends the run.
    """
    assert _MODULE_PATH.is_file(), "the execution-budget derivation module does not exist yet"
    budget = _budget()
    assert budget.node_visits == {"work": 3, "loop": 2, "done": 3, "fail": 1}
    assert budget.node_attempts == {"work": 2, "loop": 1, "done": 1, "fail": 1}
    per_attempt = _DEFAULT_TIMEOUT + _OVERHEAD
    assert budget.seconds == (3 * 2 + 2 + 3 + 1) * per_attempt


def test_a_conjunctive_guard_without_the_node_cap_still_bounds_the_loop() -> None:
    """The POSITIVE control the falsifying ones below are measured against.

    Same graph, same removed `max_visits`, and the genuine guard: a finite
    answer here is what makes each refusal below a statement about the
    CONDITION rather than about the missing cap.
    """
    budget = _budget(graph_text=_GRAPH.replace("        max_visits=5\n", ""))
    assert budget.node_visits["loop"] == 2


def test_a_guard_behind_a_disjunction_is_not_a_bound() -> None:
    """`||` means the other arm can be taken forever; the guard constrains nothing."""
    refusal = _unbounded_refusal(
        graph_text=_with_edge(
            edge='    work -> loop [condition="context.internal.node_visit_count < 3 '
            '|| outcome=failed"]\n'
        )
    )
    assert "does not bound how often node" in refusal


def test_a_negated_guard_is_not_a_bound() -> None:
    """A `!` anywhere in the condition inverts what the parse would be reading."""
    _ = _unbounded_refusal(
        graph_text=_with_edge(
            edge='    work -> loop [condition="!(context.internal.node_visit_count >= 3)"]\n'
        )
    )


def test_a_parenthesised_condition_is_not_read_as_a_bound() -> None:
    """Grouping changes which operator a conjunct belongs to; refuse rather than guess."""
    _ = _unbounded_refusal(
        graph_text=_with_edge(
            edge='    work -> loop [condition="(context.internal.node_visit_count < 3 '
            '|| outcome=failed) && outcome!=succeeded"]\n'
        )
    )


def test_a_guard_sitting_in_a_label_is_not_a_bound() -> None:
    """Label text is documentation; the engine evaluates `condition` and nothing else."""
    _ = _unbounded_refusal(
        graph_text=_with_edge(
            edge='    work -> loop [label="context.internal.node_visit_count < 3", '
            'condition="outcome=failed"]\n'
        )
    )


def test_a_guard_sitting_in_a_trailing_comment_is_not_a_bound() -> None:
    """A comment is not evaluated, so the edge beside it is unconditional."""
    _ = _unbounded_refusal(
        graph_text=_with_edge(edge="    work -> loop  // context.internal.node_visit_count < 3\n")
    )


def test_a_bare_visit_count_without_the_context_path_is_not_a_bound() -> None:
    """`node_visit_count` alone is not the field the engine exposes."""
    _ = _unbounded_refusal(
        graph_text=_with_edge(edge='    work -> loop [condition="node_visit_count < 3"]\n')
    )


def test_the_tightest_conjunct_governs_when_a_condition_carries_two_guards() -> None:
    """Every conjunct of a conjunction is enforced, so the smallest one binds."""
    budget = _budget(
        graph_text=_with_edge(
            edge='    work -> loop [condition="context.internal.node_visit_count < 4 && '
            'context.internal.node_visit_count < 2"]\n'
        )
    )
    assert budget.node_visits["loop"] == 1


def test_configured_node_timeout_moves_the_figure() -> None:
    """A repository that lengthens one node lengthens the derived bound."""
    budget = _budget(timeouts=_timeouts(configured={"work": 3600}))
    billed_elsewhere = (2 + 3 + 1) * (_DEFAULT_TIMEOUT + _OVERHEAD)
    assert budget.seconds == 3 * 2 * (3600 + _OVERHEAD) + billed_elsewhere


def test_a_templated_visit_guard_resolves_from_the_supplied_inputs() -> None:
    """The shipped graph writes the review loop's cap as a workflow input.

    A `< 4` guard admits three traversals, because the engine's visit count is
    1-based -- `review_fix_visit_cap` is rendered as the configured cap PLUS
    ONE for exactly that reason.
    """
    graph = _GRAPH.replace("node_visit_count < 3", "node_visit_count < {{ inputs.loop_cap }}")
    budget = _budget(graph_text=graph, graph_inputs={"loop_cap": 4})
    assert budget.node_visits["loop"] == 3
    assert budget.node_visits["work"] == 4


def test_an_unresolvable_templated_guard_leaves_the_edge_unguarded() -> None:
    """An input nobody supplied must not be guessed at; the node cap bounds it.

    `loop` then falls back to its own `max_visits=5`, which is the
    conservative direction: a guard whose value is unknown contributes no
    bound rather than a convenient one.
    """
    graph = _GRAPH.replace("node_visit_count < 3", "node_visit_count < {{ inputs.loop_cap }}")
    assert _budget(graph_text=graph, graph_inputs={}).node_visits["loop"] == 5


def test_an_exhaust_guard_is_not_read_as_a_bound() -> None:
    """`>=` is the arm taken once the loop stops, never a limit on it."""
    assert _budget(graph_text=_GRAPH.replace("count < 3", "count >= 3")).node_visits["loop"] == 5


def test_parallel_edges_between_one_pair_collapse_to_the_loosest_bound() -> None:
    """One visit of the source takes exactly one of its outgoing edges."""
    graph = _GRAPH.replace("node_visit_count < 3", "node_visit_count < 5").replace(
        "    loop -> work\n",
        '    loop -> work [condition="context.internal.node_visit_count < 2"]\n'
        '    loop -> work [condition="context.internal.node_visit_count < 4"]\n',
    )
    # `loop` is entered four times here, so the looser `< 4` arm binds at three
    # traversals and `work` is entered once from `start` plus three times from
    # `loop`. Collapsing to the TIGHTER `< 2` arm would have admitted one, and
    # `work` would read two.
    assert _budget(graph_text=graph).node_visits["work"] == 4


def test_an_unguarded_parallel_edge_removes_the_pair_bound() -> None:
    """A guarded arm beside an unguarded one cannot bound the pair."""
    graph = _GRAPH.replace(
        "    loop -> work\n",
        '    loop -> work [condition="context.internal.node_visit_count < 2"]\n'
        "    loop -> work\n",
    )
    assert _budget(graph_text=graph).node_visits["work"] == 3


def test_an_unguarded_edge_declared_before_a_guarded_one_removes_the_bound() -> None:
    """The collapse is order-independent: the unguarded arm wins either way."""
    graph = _GRAPH.replace(
        "    loop -> work\n",
        "    loop -> work\n"
        '    loop -> work [condition="context.internal.node_visit_count < 2"]\n',
    )
    assert _budget(graph_text=graph).node_visits["work"] == 3


def test_an_edge_naming_an_undeclared_node_is_refused() -> None:
    """A node this parse cannot see is a node the derived maximum does not bill.

    DOT lets an edge introduce a node implicitly. Dropping such an edge
    silently -- which the first build did -- removes an executable path from a
    figure still presented as a maximum, so it refuses instead.
    """
    graph = _GRAPH.replace("    done -> exit\n", "    done -> nowhere\n")
    refusal = _budget(graph_text=graph)
    assert isinstance(refusal, str)
    assert "nowhere" in refusal


def test_a_bracket_inside_a_quoted_script_does_not_truncate_the_node() -> None:
    """A quoted value is opaque: `]` inside a shell script closes nothing.

    The shipped `publish_draft` node carries `--jq '.[0].number'` in a script
    declared before its own `timeout`. A body scan that stopped at the first
    `]` would lose that timeout and bill the node at nothing -- a silent
    under-count of the very thing being maximised.
    """
    graph = _GRAPH.replace(
        "    fail [\n",
        "    odd [\n        script=\"gh pr list --jq '.[0].number'\"\n"
        '        timeout="1800s"\n    ]\n\n    work -> odd\n\n    fail [\n',
    )
    budget = _budget(graph_text=graph)
    assert budget.node_attempts["odd"] == 1
    assert budget.node_visits["odd"] == 1


def test_semicolon_separated_edges_on_one_line_are_all_read() -> None:
    """Fabro's grammar admits several statements per line; so must this parse.

    A line-anchored edge scan reads `start -> a` and silently drops the
    self-loop beside it, reporting a finite figure for a graph that cannot
    terminate. Measured against a first build: 1830 seconds and one visit of
    `a`, with the unconditional `a -> a` nowhere in the answer.
    """
    graph = (
        "digraph G {\n"
        "    start [shape=Mdiamond]\n"
        "    exit [shape=Msquare]\n"
        '    a [timeout="1800s"]\n'
        "    start -> a; a -> a; a -> exit;\n"
        "}\n"
    )
    refusal = _budget(graph_text=graph)
    assert isinstance(refusal, str), refusal
    assert "does not bound how often node" in refusal


def test_a_chained_edge_statement_is_read_as_every_hop() -> None:
    """`a -> b -> c` declares two edges, and the second one is reachable."""
    graph = (
        "digraph G {\n"
        "    start [shape=Mdiamond]\n"
        '    a [timeout="1800s"]\n'
        '    b [timeout="1800s"]\n'
        "    start -> a -> b -> a\n"
        "}\n"
    )
    refusal = _budget(graph_text=graph)
    assert isinstance(refusal, str), refusal
    assert "does not bound how often node" in refusal


def test_max_visits_inside_a_label_is_not_a_node_cap() -> None:
    """A label is documentation; only the `max_visits` ATTRIBUTE caps a node.

    Measured against a first build, which read the substring out of the label
    and returned 5490 seconds with three visits of a node nothing bounds.
    """
    graph = (
        "digraph G {\n"
        "    start [shape=Mdiamond]\n"
        "    exit [shape=Msquare]\n"
        '    a [timeout="1800s", label="max_visits=3"]\n'
        "    start -> a\n"
        "    a -> a\n"
        "    a -> exit\n"
        "}\n"
    )
    refusal = _budget(graph_text=graph)
    assert isinstance(refusal, str), refusal
    assert "does not bound how often node" in refusal


def test_a_real_max_visits_attribute_still_caps_the_same_graph() -> None:
    """The positive control for the label case: the ATTRIBUTE does bound it."""
    graph = (
        "digraph G {\n"
        "    start [shape=Mdiamond]\n"
        "    exit [shape=Msquare]\n"
        '    a [timeout="1800s", max_visits=3]\n'
        "    start -> a\n"
        "    a -> a\n"
        "    a -> exit\n"
        "}\n"
    )
    assert _budget(graph_text=graph).node_visits["a"] == 3


def test_a_non_integer_visit_cap_is_refused_rather_than_ignored() -> None:
    """Ignoring an unreadable cap would drop the only bound on the loop."""
    graph = (
        "digraph G {\n"
        "    start [shape=Mdiamond]\n"
        '    a [timeout="1800s", max_visits="three"]\n'
        "    start -> a\n"
        "    a -> a\n"
        "}\n"
    )
    refusal = _budget(graph_text=graph)
    assert isinstance(refusal, str), refusal
    assert "max_visits" in refusal


def test_a_non_integer_retry_budget_is_refused() -> None:
    graph = _GRAPH.replace("max_retries=1", 'max_retries="lots"')
    refusal = _budget(graph_text=graph)
    assert isinstance(refusal, str), refusal
    assert "max_retries" in refusal


def test_a_non_integer_graph_retry_default_is_refused() -> None:
    graph = _GRAPH.replace("default_max_retries=0", 'default_max_retries="none"')
    refusal = _budget(graph_text=graph)
    assert isinstance(refusal, str), refusal
    assert "default_max_retries" in refusal


def test_an_absent_default_max_retries_bills_one_attempt_per_visit() -> None:
    graph = _GRAPH.replace("        default_max_retries=0\n", "")
    assert _budget(graph_text=graph).node_attempts["loop"] == 1


def test_a_graph_level_default_max_retries_bills_every_unretried_node() -> None:
    graph = _GRAPH.replace("default_max_retries=0", "default_max_retries=2")
    attempts = _budget(graph_text=graph).node_attempts
    assert attempts["loop"] == 3
    # A node declaring its OWN budget keeps it; the graph default is a default.
    assert attempts["work"] == 2


def test_a_retry_preset_overriding_a_zero_retry_budget_is_billed_at_its_attempts() -> None:
    """`build_retry_policy` reads `retry_policy` BEFORE the retry budget.

    A node declaring `max_retries=0` and `retry_policy="standard"` executes up
    to five attempts. Billing it one -- which a retry-budget-only reading does
    -- undercounts that node's wall clock four-fold.
    """
    graph = _GRAPH.replace("        max_retries=1\n", '        retry_policy="standard"\n')
    assert _budget(graph_text=graph).node_attempts["work"] == 5


def test_a_weaker_retry_preset_never_lowers_a_larger_retry_budget() -> None:
    """The larger reading wins: a maximum may over-bill, never under-bill."""
    graph = _GRAPH.replace(
        "        max_retries=1\n", '        max_retries=1\n        retry_policy="none"\n'
    )
    assert _budget(graph_text=graph).node_attempts["work"] == 2


def test_each_known_retry_preset_bills_its_own_attempt_count() -> None:
    for preset, attempts in (("aggressive", 5), ("linear", 3), ("patient", 3), ("none", 1)):
        graph = _GRAPH.replace(
            '        timeout="600s"\n',
            f'        timeout="600s"\n        retry_policy="{preset}"\n',
        )
        assert _budget(graph_text=graph).node_attempts["done"] == attempts, preset


def test_a_graph_level_retry_preset_reaches_a_node_declaring_none() -> None:
    """Whether the engine applies one is not settled, so bill it: over, never under."""
    graph = _GRAPH.replace(
        "        default_max_retries=0\n",
        '        default_max_retries=0\n        retry_policy="linear"\n',
    )
    assert _budget(graph_text=graph).node_attempts["done"] == 3


def test_an_unknown_retry_preset_is_refused_rather_than_defaulted() -> None:
    """A policy whose attempt count is unknown has no honest number."""
    graph = _GRAPH.replace("        max_retries=1\n", '        retry_policy="turbo"\n')
    refusal = _budget(graph_text=graph)
    assert isinstance(refusal, str), refusal
    assert "retry_policy=turbo" in refusal


def test_an_unknown_graph_level_retry_preset_is_refused() -> None:
    graph = _GRAPH.replace("        default_max_retries=0\n", '        retry_policy="warp"\n')
    refusal = _budget(graph_text=graph)
    assert isinstance(refusal, str), refusal
    assert "retry_policy=warp" in refusal


def test_a_graph_with_no_timed_node_is_refused_rather_than_budgeted_at_zero() -> None:
    graph = "digraph G {\n    start [shape=Mdiamond]\n    exit [shape=Msquare]\n"
    graph += "    start -> exit\n}\n"
    refusal = _budget(graph_text=graph)
    assert isinstance(refusal, str)
    assert "no node carrying a timeout" in refusal


def test_an_unbounded_cycle_is_refused_and_names_the_node() -> None:
    """No max_visits and no visit guard anywhere in the cycle: no finite clock."""
    graph = (
        "digraph G {\n"
        "    start [shape=Mdiamond]\n"
        '    a [ timeout="1800s" ]\n'
        '    b [ timeout="1800s" ]\n'
        "    start -> a\n"
        "    a -> b\n"
        "    b -> a\n"
        "}\n"
    )
    refusal = _budget(graph_text=graph)
    assert isinstance(refusal, str)
    assert "does not bound how often node" in refusal
    assert "credential" in refusal


def test_a_default_attribute_statement_is_refused_rather_than_misread() -> None:
    """`node [...]` re-bases every later declaration; this parse does not model it."""
    graph = _GRAPH.replace(
        "    start [shape=Mdiamond", "    node [max_visits=2]\n    start [shape=Mdiamond"
    )
    refusal = _budget(graph_text=graph)
    assert isinstance(refusal, str), refusal
    assert "`node` statement" in refusal


def test_a_subgraph_is_refused_rather_than_partly_read() -> None:
    graph = _GRAPH.replace("    done -> exit\n", "    subgraph cluster_x { done -> exit }\n")
    refusal = _budget(graph_text=graph)
    assert isinstance(refusal, str), refusal
    assert "`subgraph` statement" in refusal


def test_an_undirected_edge_is_refused() -> None:
    graph = _GRAPH.replace("    done -> exit\n", "    done -- exit\n")
    refusal = _budget(graph_text=graph)
    assert isinstance(refusal, str), refusal
    assert "undirected" in refusal


def test_a_character_the_lexer_cannot_classify_is_refused() -> None:
    graph = _GRAPH.replace("    loop -> work\n", "    loop -> work ?\n")
    refusal = _budget(graph_text=graph)
    assert isinstance(refusal, str), refusal
    assert "does not model" in refusal


def test_a_graph_that_never_closes_is_refused() -> None:
    refusal = _budget(graph_text=_GRAPH.rstrip().removesuffix("}"))
    assert isinstance(refusal, str), refusal
    assert "closing brace" in refusal


def test_text_that_does_not_open_a_digraph_is_refused() -> None:
    refusal = _budget(graph_text="not a graph at all\n")
    assert isinstance(refusal, str), refusal
    assert "digraph" in refusal


def test_a_declaration_with_no_opening_brace_is_refused() -> None:
    refusal = _budget(graph_text="digraph G\n")
    assert isinstance(refusal, str), refusal
    assert "opening brace" in refusal


def test_a_graph_level_assignment_statement_is_read() -> None:
    """DOT also spells a graph attribute as a bare `key = value` statement."""
    graph = _GRAPH.replace("        default_max_retries=0\n", "").replace(
        "    start -> work\n", "    default_max_retries = 1;\n    start -> work\n"
    )
    assert _budget(graph_text=graph).node_attempts["loop"] == 2


def test_an_attribute_with_no_value_is_refused() -> None:
    graph = _GRAPH.replace('        timeout="600s"\n', "        timeout\n")
    refusal = _budget(graph_text=graph)
    assert isinstance(refusal, str), refusal
    assert "carries no value" in refusal


def test_an_edge_with_no_destination_is_refused() -> None:
    graph = _GRAPH.replace("    done -> exit\n", "    done ->\n}\n")
    refusal = _budget(graph_text=graph)
    assert isinstance(refusal, str), refusal
    assert "no destination" in refusal


def test_the_shipped_graph_derives_a_finite_budget() -> None:
    """The positive control over REAL syntax, not a synthetic subset of it.

    No number is asserted -- the graph is edited often and the figure moves
    with it. What is asserted is that the parse reaches an answer at all over
    the comments, quoted shell scripts, templated conditions and parallel
    terminal arms the shipped graph actually contains, and that the normal
    configuration therefore stays ADMISSIBLE rather than refusing vacuously.
    """
    graph_text = _SHIPPED_GRAPH_PATH.read_text(encoding="utf-8")
    budget = _budget(
        graph_text=graph_text,
        timeouts=_timeouts(configured={"implement": 14400, "janitor": 3600, "fix": 3600}),
        graph_inputs={"review_fix_visit_cap": 4},
    )
    assert not isinstance(budget, str), budget
    assert budget.seconds > 0
    # Every node the graph declares a timeout for is billed at least one visit:
    # a zero would mean the parse lost a reachable node rather than bounded it.
    assert all(visits >= 1 for visits in budget.node_visits.values())
    assert {"implement", "janitor", "fix", "review", "pr"} <= set(budget.node_visits)
