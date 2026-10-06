"""The structural read of a Fabro workflow graph, and everything it refuses.

`_dispatcher_execution_budget` is the consumer and carries the cases about what
a bound MEANS; this module carries the cases about what the graph SAYS. The
split matters because every defect this parser exists to close looked, at the
consumer, like a perfectly ordinary number: an edge statement dropped because
two of them shared a line, a `max_visits` read out of a label, a node truncated
at a `]` inside a quoted shell script. None of those announce themselves
downstream, so they are pinned here, at the parse.

The refusal cases are the bulk of it, deliberately. A parser for a maximum must
fail CLOSED -- syntax it does not model has to come back as a refusal naming
what was found, never as a partial read -- so each unmodelled construct gets a
case asserting the refusal rather than asserting some tolerated behaviour.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import (
    DotGraph,
    parse_dot_graph,
)


def _parsed(*, text: str) -> DotGraph:
    graph = parse_dot_graph(text=text)
    assert not isinstance(graph, str), graph
    return graph


def _refusal(*, text: str) -> str:
    refusal = parse_dot_graph(text=text)
    assert isinstance(refusal, str), refusal
    return refusal


def test_a_nameless_strict_digraph_header_is_accepted() -> None:
    graph = _parsed(text='strict digraph {\n  a [timeout="1s"]\n}\n')
    assert set(graph.nodes) == {"a"}


def test_a_named_digraph_header_is_accepted() -> None:
    assert set(_parsed(text="digraph Named {\n  a\n}\n").nodes) == {"a"}


def test_several_statements_on_one_line_are_all_read() -> None:
    """Semicolons separate statements; a line is not a statement boundary."""
    graph = _parsed(text="digraph G {\n  a; b; c\n  a -> b; b -> c;\n}\n")
    assert set(graph.nodes) == {"a", "b", "c"}
    assert [(edge.source, edge.destination) for edge in graph.edges] == [("a", "b"), ("b", "c")]


def test_a_chained_edge_statement_yields_one_edge_per_hop() -> None:
    """And every hop carries the statement's attribute list, as the engine does."""
    graph = _parsed(text='digraph G {\n  a; b; c\n  a -> b -> c [label="shared"]\n}\n')
    assert [(edge.source, edge.destination) for edge in graph.edges] == [("a", "b"), ("b", "c")]
    assert all(edge.attributes == {"label": "shared"} for edge in graph.edges)


def test_a_quoted_value_is_opaque_to_the_parse() -> None:
    """A `]`, a `;`, a `->` or a `//` inside a string closes and starts nothing."""
    graph = _parsed(
        text="digraph G {\n  a [script=\"gh pr list --jq '.[0]'; x -> y // z\", "
        'timeout="1800s"]\n}\n'
    )
    assert graph.nodes["a"]["timeout"] == "1800s"
    assert graph.edges == ()


def test_an_escaped_quote_inside_a_value_is_decoded() -> None:
    graph = _parsed(text='digraph G {\n  a [script="echo \\"hi\\""]\n}\n')
    assert graph.nodes["a"]["script"] == 'echo "hi"'


def test_an_attribute_key_may_carry_a_dot() -> None:
    """The shipped graph spells the ACP command as `acp.command`."""
    assert _parsed(text='digraph G {\n  a [acp.command="x"]\n}\n').nodes["a"]["acp.command"] == "x"


def test_attributes_separate_with_a_comma_a_semicolon_or_nothing() -> None:
    for separator in (", ", "; ", " "):
        text = f"digraph G {{\n  a [one=1{separator}two=2]\n}}\n"
        assert _parsed(text=text).nodes["a"] == {"one": "1", "two": "2"}, separator


def test_a_node_declared_twice_merges_its_attributes() -> None:
    graph = _parsed(text="digraph G {\n  a [one=1]\n  a [two=2, one=9]\n}\n")
    assert graph.nodes["a"] == {"one": "9", "two": "2"}


def test_graph_attributes_arrive_from_both_spellings() -> None:
    """DOT writes a graph attribute as a `graph [...]` block or a bare assignment."""
    graph = _parsed(text='digraph G {\n  graph [one=1]\n  two = "2";\n  a\n}\n')
    assert graph.attributes == {"one": "1", "two": "2"}


def test_line_block_and_hash_comments_are_skipped() -> None:
    text = "digraph G {\n  // one\n  # two\n  /* three\n  still three */\n  a\n}\n"
    assert set(_parsed(text=text).nodes) == {"a"}


def test_text_that_does_not_open_a_digraph_is_refused() -> None:
    assert "digraph" in _refusal(text="nonsense\n")


def test_empty_text_is_refused() -> None:
    assert "digraph" in _refusal(text="")


def test_a_header_with_no_opening_brace_is_refused() -> None:
    assert "opening brace" in _refusal(text="digraph G\n")


def test_a_graph_that_never_closes_is_refused() -> None:
    assert "closing brace" in _refusal(text="digraph G {\n  a\n")


def test_a_statement_opening_with_punctuation_is_refused() -> None:
    assert "does not model" in _refusal(text="digraph G {\n  [a=1]\n}\n")


def test_a_default_attribute_statement_is_refused() -> None:
    for keyword in ("node", "edge"):
        assert f"`{keyword}` statement" in _refusal(text=f"digraph G {{\n  {keyword} [a=1]\n}}\n")


def test_a_subgraph_is_refused() -> None:
    assert "`subgraph` statement" in _refusal(text="digraph G {\n  subgraph s { a }\n}\n")


def test_an_undirected_edge_is_refused() -> None:
    assert "undirected" in _refusal(text="digraph G {\n  a -- b\n}\n")


def test_an_unclassifiable_character_is_refused_with_its_offset() -> None:
    refusal = _refusal(text="digraph G {\n  a ?\n}\n")
    assert "does not model" in refusal
    assert "'?'" in refusal


def test_a_graph_assignment_with_no_value_is_refused() -> None:
    assert "assigns `a`" in _refusal(text="digraph G {\n  a = }\n")


def test_a_graph_assignment_cut_off_at_the_end_is_refused() -> None:
    assert "assigns `a`" in _refusal(text="digraph G {\n  a =")


def test_an_attribute_list_opening_with_punctuation_is_refused() -> None:
    assert "attribute list" in _refusal(text="digraph G {\n  a [, ]\n}\n")


def test_an_attribute_list_cut_off_at_the_end_is_refused() -> None:
    assert "attribute list" in _refusal(text="digraph G {\n  a [")


def test_an_attribute_with_no_equals_is_refused() -> None:
    assert "carries no value" in _refusal(text="digraph G {\n  a [one]\n}\n")


def test_an_attribute_whose_value_is_punctuation_is_refused() -> None:
    assert "carries no value" in _refusal(text="digraph G {\n  a [one = ]\n}\n")


def test_an_attribute_cut_off_after_its_equals_is_refused() -> None:
    assert "carries no value" in _refusal(text="digraph G {\n  a [one =")


def test_a_broken_attribute_list_on_the_graph_block_is_refused() -> None:
    """Every statement that can carry an attribute list propagates its refusal."""
    assert "carries no value" in _refusal(text="digraph G {\n  graph [one]\n}\n")


def test_a_broken_attribute_list_on_an_edge_is_refused() -> None:
    assert "carries no value" in _refusal(text="digraph G {\n  a; b\n  a -> b [one]\n}\n")


def test_an_edge_with_no_destination_is_refused() -> None:
    assert "no destination" in _refusal(text="digraph G {\n  a -> }\n")


def test_an_edge_cut_off_after_its_arrow_is_refused() -> None:
    assert "no destination" in _refusal(text="digraph G {\n  a ->")
