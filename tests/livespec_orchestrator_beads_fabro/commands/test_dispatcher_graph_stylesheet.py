"""What a graph's `model_stylesheet` makes each node's backend, or a refusal.

These cases drive the resolver DIRECTLY. The behaviour an operator sees is graded
through `unguardable_launch_refusal` in
`test_dispatcher_credential_use_routes.py`; what is graded here is the ladder
itself -- the four selector kinds, their specificity order, the engine's
explicit-attribute precedence -- plus every arm of the ported stylesheet grammar,
whose refusals a graph-level test can only reach one at a time.

THE FIDELITY CLAIM IS NARROW AND DELIBERATE: this resolves `backend` and nothing
else, because `backend` is what decides whether a node launches a coding agent at
all. Every assertion below is written against the pinned engine at
`8869e88b2f7e383ec6fceb8d3f6f928dd0339b34`
(`fabro-workflow/src/transforms/stylesheet.rs` for the application rules,
`fabro-graphviz/src/stylesheet.rs` for the grammar), and names the rule it is
reproducing so a future engine bump can be checked against it rather than guessed
at.
"""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import (
    DotGraph,
    parse_dot_graph,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_graph_stylesheet import (
    nodes_with_effective_backend,
)


def _graph(*, text: str) -> DotGraph:
    """Parse through the real DOT parser, so fixtures are engine-acceptable input."""
    graph = parse_dot_graph(text=text)
    assert not isinstance(graph, str), graph
    return graph


def _resolved(*, text: str) -> dict[str, dict[str, str]]:
    """The effective nodes for a graph expected to resolve."""
    nodes = nodes_with_effective_backend(graph=_graph(text=text))
    assert not isinstance(nodes, str), nodes
    return {name: dict(attributes) for name, attributes in nodes.items()}


def _refusal(*, text: str) -> str:
    """The refusal for a graph expected not to resolve."""
    nodes = nodes_with_effective_backend(graph=_graph(text=text))
    assert isinstance(nodes, str), f"expected a refusal, resolved {nodes!r}"
    return nodes


def _styled(*, stylesheet: str, node: str = 'a [acp.command="/x"]', other: str = "") -> str:
    """A two-node graph carrying one stylesheet, for one-difference-at-a-time cases.

    `other` declares the second node `b`, which is otherwise named only by the edge
    and so carries no attributes. Any case whose stylesheet uses a SHAPE selector
    has to declare it, because a shapeless node makes that selector undecidable and
    the refusal would be attributable to `b` rather than to the case's own subject.
    """
    extra = f"  {other}\n" if other else ""
    return (
        f'digraph G {{\n  graph [model_stylesheet="{stylesheet}"]\n  {node}\n{extra}  a -> b\n}}\n'
    )


# --- No stylesheet: the path every shipped graph takes ----------------------------


def test_a_graph_with_no_stylesheet_returns_its_nodes_unchanged() -> None:
    """THE POSITIVE CONTROL for the cheap path, and it is the common one.

    No graph this repository ships carries a `model_stylesheet`, so this is the
    verdict that must not move: the nodes come back exactly as declared.
    """
    resolved = _resolved(text='digraph G {\n  a [backend=acp, timeout="60s"]\n  a -> b\n}\n')
    assert resolved["a"] == {"backend": "acp", "timeout": "60s"}


def test_an_empty_stylesheet_is_treated_as_absent() -> None:
    """A declared-but-blank stylesheet applies nothing rather than refusing."""
    assert _resolved(text=_styled(stylesheet="   ", node="a [backend=command]"))["a"] == {
        "backend": "command"
    }


def test_an_edge_only_endpoint_is_included_with_no_attributes() -> None:
    """The engine's `ensure_node` creates a node for any edge endpoint.

    `b` is named only by the edge, so it exists for the engine and a universal rule
    would reach it. Omitting it here would hide exactly that.
    """
    resolved = _resolved(text="digraph G {\n  a [backend=acp]\n  a -> b\n}\n")
    assert resolved["b"] == {}


# --- The selector ladder ---------------------------------------------------------


def test_a_universal_rule_reaches_every_node() -> None:
    """Specificity 0, and it matches nodes that declare nothing at all."""
    resolved = _resolved(text=_styled(stylesheet="* { backend: acp; }"))
    assert resolved["a"]["backend"] == "acp"
    assert resolved["b"]["backend"] == "acp"


def test_an_id_rule_reaches_only_the_named_node() -> None:
    """Specificity 3, matched against the node's own name."""
    resolved = _resolved(text=_styled(stylesheet="#a { backend: acp; }"))
    assert resolved["a"]["backend"] == "acp"
    assert "backend" not in resolved["b"]


def test_a_class_rule_matches_a_comma_separated_class_attribute() -> None:
    """The engine's `process_node` splits `class` on commas and trims each part."""
    resolved = _resolved(
        text=_styled(
            stylesheet=".code { backend: acp; }",
            node='a [class="planning , code", acp.command="/x"]',
        )
    )
    assert resolved["a"]["backend"] == "acp"


def test_a_class_rule_does_not_match_a_node_without_that_class() -> None:
    """The negative half, so the case above cannot pass by matching everything."""
    resolved = _resolved(
        text=_styled(stylesheet=".code { backend: acp; }", node='a [class="planning"]')
    )
    assert "backend" not in resolved["a"]


def test_a_shape_rule_matches_a_declared_shape() -> None:
    """A bare-word selector names a SHAPE, not a node."""
    resolved = _resolved(
        text=_styled(
            stylesheet="box { backend: acp; }",
            node="a [shape=box]",
            other="b [shape=ellipse]",
        )
    )
    assert resolved["a"]["backend"] == "acp"


def test_a_shape_rule_does_not_match_a_different_declared_shape() -> None:
    """Decidable non-match: the node declares a shape and it is not the selector's."""
    resolved = _resolved(
        text=_styled(
            stylesheet="box { backend: acp; }",
            node="a [shape=ellipse]",
            other="b [shape=ellipse]",
        )
    )
    assert "backend" not in resolved["a"]


# --- Precedence -----------------------------------------------------------------


def test_an_explicit_backend_is_never_overridden() -> None:
    """`apply_stylesheet` inserts only `if !node.attrs.contains_key(prop)`."""
    resolved = _resolved(
        text=_styled(stylesheet="#a { backend: acp; }", node="a [backend=command]")
    )
    assert resolved["a"]["backend"] == "command"


def test_higher_specificity_wins_regardless_of_declaration_order() -> None:
    """The universal rule is written LAST and must still lose to the id rule."""
    resolved = _resolved(text=_styled(stylesheet="#a { backend: acp; } * { backend: command; }"))
    assert resolved["a"]["backend"] == "acp"
    assert resolved["b"]["backend"] == "command"


def test_the_last_rule_wins_among_equal_specificities() -> None:
    """The engine sorts by specificity with a STABLE sort and overwrites on `>=`."""
    resolved = _resolved(text=_styled(stylesheet="#a { backend: command; } #a { backend: acp; }"))
    assert resolved["a"]["backend"] == "acp"


def test_the_last_declaration_within_one_rule_wins() -> None:
    """Equal specificity again, one rule: the later `backend` is the effective one."""
    resolved = _resolved(text=_styled(stylesheet="#a { backend: command; backend: acp; }"))
    assert resolved["a"]["backend"] == "acp"


def test_a_rule_declaring_no_backend_cannot_change_a_verdict() -> None:
    """Only `backend` is resolved, so an ordinary model rule is inert here.

    This is what keeps the undecidable-shape refusal below from firing on a
    stylesheet that merely picks models -- which is what most of them do.
    """
    resolved = _resolved(text=_styled(stylesheet="box { model: opus; }"))
    assert "backend" not in resolved["a"]
    assert "model" not in resolved["a"], "only `backend` is resolved"


# --- The one undecidable case ----------------------------------------------------


def test_a_shape_rule_against_a_node_declaring_no_shape_is_refused() -> None:
    """The engine's default shape lives in `fabro_types`, which is not carried here.

    So whether this rule selects `a` is genuinely unknown, and an unknown resolved
    either way is either an admitted unguarded launch or a refused healthy graph.
    """
    refusal = _refusal(text=_styled(stylesheet="box { backend: acp; }"))
    assert "'a'" in refusal
    assert "declares no shape" in refusal
    assert "'box'" in refusal


def test_a_node_with_an_explicit_backend_is_not_refused_over_an_undecidable_shape() -> None:
    """Precedence runs FIRST: no rule can reach it, so its shape is irrelevant."""
    resolved = _resolved(
        text=_styled(
            stylesheet="box { backend: acp; }",
            node="a [backend=command]",
            other="b [shape=ellipse]",
        )
    )
    assert resolved["a"]["backend"] == "command"


# --- The ported grammar's refusal ladder ----------------------------------------
#
# Each case is the smallest stylesheet that reaches one arm. An unreadable
# stylesheet is refused rather than ignored: the pinned engine drops a
# parse error and runs the graph unstyled, which is safe for the engine and
# useless for a validator that has to enumerate launches.


@pytest.mark.parametrize(
    ("stylesheet", "expected"),
    [
        ("#a { backend acp; }", "expected ':' after the property name"),
        ("#a backend: acp; }", "expected '{' after the selector"),
        ("# { backend: acp; }", "expected an identifier after '#'"),
        (". { backend: acp; }", "expected a class name after '.'"),
        ("%bad { backend: acp; }", "expected a selector"),
        ("#a { backend: acp;", "ended before a rule's closing '}'"),
        ("#a { backend: }", "has an empty value"),
        # A property name that runs to the end of the text, terminated by neither a
        # `:` nor whitespace, and a value that runs to the end terminated by neither
        # a `;` nor a `}`. Both are the end-of-input arm of their own scan, which the
        # cases above reach by finding a terminator instead.
        ("#a { backend", "expected ':' after the property name"),
        ("#a { backend: acp", "ended before a rule's closing '}'"),
    ],
)
def test_an_unreadable_stylesheet_is_refused_naming_what_was_found(
    stylesheet: str, expected: str
) -> None:
    """Every grammar arm refuses with its own diagnostic, carrying the attribute name."""
    refusal = _refusal(text=_styled(stylesheet=stylesheet))
    assert "model_stylesheet" in refusal, refusal
    assert expected in refusal, refusal


def test_a_stray_semicolon_between_declarations_is_skipped() -> None:
    """The engine tolerates it, so refusing would reject a valid stylesheet."""
    resolved = _resolved(text=_styled(stylesheet="#a { ; backend: acp ; ; }"))
    assert resolved["a"]["backend"] == "acp"


def test_a_final_declaration_without_a_trailing_semicolon_is_read() -> None:
    """The value runs to the closing brace."""
    resolved = _resolved(text=_styled(stylesheet="#a { backend: acp }"))
    assert resolved["a"]["backend"] == "acp"


def test_a_class_name_stops_at_an_uppercase_character() -> None:
    """The engine's class charset is ASCII lowercase, digits and `-` only.

    `.coDe` therefore parses as the class `co` followed by `De`, which is not a
    `{`, so the rule is refused rather than silently matching `code`.
    """
    refusal = _refusal(text=_styled(stylesheet=".coDe { backend: acp; }"))
    assert "expected '{' after the selector" in refusal
    assert "'.co'" in refusal


def test_a_non_ascii_selector_character_is_not_a_name_character() -> None:
    """The engine's charsets are ASCII-only, so a non-ASCII leading char is no name."""
    refusal = _refusal(text=_styled(stylesheet="é { backend: acp; }"))
    assert "expected a selector" in refusal


def test_a_selector_name_may_carry_digits_and_underscores() -> None:
    """The id/shape charset is ASCII alphanumerics plus `_` and `-`.

    Only the first two are exercised through a node NAME, because DOT itself does
    not admit `-` in a bare identifier -- so an id selector carrying one can never
    match a node. The hyphen's own coverage is the class case below, where the value
    is a quoted attribute rather than a node name.
    """
    resolved = _resolved(
        text=_styled(
            stylesheet="#proof_capture2 { backend: acp; }",
            node='proof_capture2 [acp.command="/x"]',
        )
    )
    assert resolved["proof_capture2"]["backend"] == "acp"


def test_a_class_name_may_carry_digits_and_hyphens() -> None:
    """The class charset's own positive control, matching `.loop-a2`."""
    resolved = _resolved(
        text=_styled(stylesheet=".loop-a2 { backend: acp; }", node='a [class="loop-a2"]')
    )
    assert resolved["a"]["backend"] == "acp"


# --- Class membership comes from the parser's accumulation -----------------------
#
# Not from the node's final `class` attribute. The engine overwrites `node.attrs`
# per declaration but only pushes onto `node.classes`, and `Selector::Class`
# matches the latter -- so the two disagree whenever a node is declared twice, and
# reconstructing membership from the attribute drops the earlier classes.


def test_a_class_only_an_earlier_declaration_carried_still_selects() -> None:
    """THE REGRESSION, at this module's own seam.

    `a`'s final `class` attribute is `replacement`; its accumulated membership is
    `[retained, replacement]`. A `.retained` rule must still reach it.
    """
    resolved = _resolved(
        text=(
            'digraph G {\n  graph [model_stylesheet=".retained { backend: acp; }"]\n'
            '  a [class="retained"]\n  a [class="replacement"]\n  a -> b\n}\n'
        )
    )
    assert resolved["a"]["backend"] == "acp"


def test_a_class_only_a_later_declaration_carried_also_selects() -> None:
    """The mirror direction, so a first-wins read cannot pass the case above."""
    resolved = _resolved(
        text=(
            'digraph G {\n  graph [model_stylesheet=".replacement { backend: acp; }"]\n'
            '  a [class="retained"]\n  a [class="replacement"]\n  a -> b\n}\n'
        )
    )
    assert resolved["a"]["backend"] == "acp"


def test_a_class_no_declaration_ever_carried_does_not_select() -> None:
    """The negative half: accumulation is a union of what was declared, not a wildcard."""
    resolved = _resolved(
        text=(
            'digraph G {\n  graph [model_stylesheet=".absent { backend: acp; }"]\n'
            '  a [class="retained"]\n  a [class="replacement"]\n  a -> b\n}\n'
        )
    )
    assert "backend" not in resolved["a"]
