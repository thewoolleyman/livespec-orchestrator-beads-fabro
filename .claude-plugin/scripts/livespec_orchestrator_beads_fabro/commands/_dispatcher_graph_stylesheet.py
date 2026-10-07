"""What a graph's `model_stylesheet` makes each node's backend, or a refusal.

WHY THIS EXISTS, and it is the repair of a measured defect rather than a
precaution. A node's backend does NOT have to be written on the node. The pinned
engine runs a `StylesheetApplicationTransform`
(`fabro-workflow/src/transforms/stylesheet_application.rs`) that reads the graph's
`model_stylesheet` attribute and fills in any of five properties a node has not
declared explicitly -- `model`, `provider`, `reasoning_effort`, `speed` and
`backend` (`transforms/stylesheet.rs` `STYLESHEET_PROPERTIES`). So `backend: acp`
can arrive from the stylesheet, and a validator keyed on the literal node
attribute sees an ordinary command node exactly where the engine will launch a
coding agent.

That was MEASURED, not reasoned about: taking the shipped graph, removing ONLY
`implement`'s explicit `backend="acp"`, pointing its `acp.command` at a literal
and adding `model_stylesheet="#implement { backend: acp; }"` left the launch
validator returning None -- admitted -- while the engine would select ACP and run
the literal with no guard in front of it.

THIS MODULE RESOLVES EXACTLY ONE PROPERTY, `backend`, and that narrowness is the
point. `backend` is what decides whether a node launches a coding agent at all,
which is the only question its caller asks; the other four change WHICH model
answers, never WHETHER a credential is spent. A module that claimed to resolve
all five would be claiming a fidelity nothing here exercises.

THE LADDER IS THE ENGINE'S OWN (`fabro-graphviz/src/stylesheet.rs`). Four selector
kinds carry four specificities -- `*` universal 0, a bare word matching the node's
SHAPE 1, `.class` 2, `#id` 3 -- higher specificity wins, and ties go to the rule
declared LAST, because the engine sorts rules by specificity with a stable sort
and overwrites on `spec >= existing`. An EXPLICIT node attribute is never
overridden at all, so a node writing its own `backend` is returned untouched and
no rule can reach it.

EVERY NODE THE ENGINE WILL HAVE, not merely every node the graph DECLARES. The
engine's `ensure_node` creates a node for any edge endpoint, and a universal rule
then reaches it too, so an endpoint named only in an edge is included here with no
attributes. Leaving it out would hide a node that a `*` rule makes ACP.

AND CLASS MEMBERSHIP COMES FROM THE PARSER'S ACCUMULATED LIST, never from the
node's final `class` attribute -- the second measured bypass, and the subtler one
because the two agree on every graph that declares each node once. The engine
OVERWRITES `node.attrs` per declaration but only PUSHES onto `node.classes`, so a
node declared twice ends with the LAST attribute and the UNION of its classes, and
`Selector::Class` matches that union. Re-deriving membership from the attribute
therefore drops whatever only an earlier declaration carried: re-declaring
`implement` with `class="replacement"` made a `.retained` rule read as not
matching, and the literal launch it guarded was ADMITTED. `DotGraph.node_classes`
carries the union; this module must not reconstruct it.

AND TWO DELIBERATE FAIL-CLOSED DEPARTURES, each stricter than the pinned engine,
because this module's answer is used to decide whether a live credential may be
spent with enforcement claimed over it:

- AN UNPARSEABLE STYLESHEET IS A REFUSAL. The engine swallows a stylesheet parse
  error and runs the graph with the stylesheet unapplied, which is safe for the
  engine and useless here: a stylesheet we cannot read is one whose effective
  backends we cannot enumerate, and that is exactly when we must not report them
  as bounded.
- A SHAPE SELECTOR AGAINST A NODE DECLARING NO SHAPE IS A REFUSAL. A bare-word
  selector matches a node's shape, and a node declaring none takes the engine's
  own default -- a value that lives in `fabro_types`, which this repository does
  not carry, so the match is genuinely UNDECIDABLE. An undecidable that resolved
  to "not selected" would admit an unguarded launch; one that resolved to
  "selected" would refuse graphs that are fine. Refusing and naming the rule is
  the honest answer, and it is the one an adopter can act on.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import DotGraph

__all__: list[str] = [
    "nodes_with_effective_backend",
]

_STYLESHEET_ATTRIBUTE = "model_stylesheet"
_BACKEND = "backend"
_SHAPE = "shape"

# The four selector kinds and the engine's specificity for each.
_UNIVERSAL = "universal"
_BY_SHAPE = "shape"
_BY_CLASS = "class"
_BY_ID = "id"
_SPECIFICITY: Mapping[str, int] = {_UNIVERSAL: 0, _BY_SHAPE: 1, _BY_CLASS: 2, _BY_ID: 3}

_DIAGNOSTIC_WIDTH = 20


@dataclass(frozen=True, kw_only=True)
class _Selector:
    """One parsed selector: its kind, what it names, and how it was written."""

    kind: str
    name: str
    text: str


@dataclass(frozen=True, kw_only=True)
class _Rule:
    """One parsed rule. `declarations` keeps the LAST value of a repeated property."""

    selector: _Selector
    declarations: Mapping[str, str]


@dataclass(kw_only=True)
class _Text:
    """The unconsumed stylesheet text, trimmed after every advance as the engine is."""

    rest: str

    def advance(self, *, count: int) -> None:
        self.rest = self.rest[count:].strip()


def nodes_with_effective_backend(*, graph: DotGraph) -> Mapping[str, Mapping[str, str]] | str:
    """Every node the engine will have, with the backend the engine will see.

    Returns a mapping from node name to its attributes, with `backend` added
    wherever the stylesheet supplies one the node did not declare, or ONE refusal
    string naming what could not be established.

    A graph carrying no `model_stylesheet` returns its nodes unchanged, which is
    every graph this repository ships today -- the stylesheet path costs them
    nothing and changes no verdict.
    """
    declared = _every_node(graph=graph)
    stylesheet = graph.attributes.get(_STYLESHEET_ATTRIBUTE, "")
    if not stylesheet.strip():
        return declared
    rules = _parse_stylesheet(text=stylesheet)
    if isinstance(rules, str):
        return f"the graph's {_STYLESHEET_ATTRIBUTE} could not be read: {rules}"
    # Only a rule that declares `backend` can change the answer; filtering here
    # keeps an undecidable SHAPE match from refusing over a rule that merely sets
    # a model, which would refuse graphs whose stylesheets are entirely ordinary.
    deciding = tuple(rule for rule in rules if _BACKEND in rule.declarations)
    resolved: dict[str, Mapping[str, str]] = {}
    for node, attributes in declared.items():
        effective = _effective_node(
            node=node,
            attributes=attributes,
            # The ACCUMULATED membership, never a re-read of the `class`
            # attribute: the two diverge whenever a node is declared twice.
            classes=graph.node_classes.get(node, ()),
            rules=deciding,
        )
        if isinstance(effective, str):
            return effective
        resolved[node] = effective
    return resolved


def _every_node(*, graph: DotGraph) -> dict[str, Mapping[str, str]]:
    """Declared nodes, plus every edge endpoint the engine's `ensure_node` creates."""
    nodes: dict[str, Mapping[str, str]] = dict(graph.nodes)
    for edge in graph.edges:
        for endpoint in (edge.source, edge.destination):
            if endpoint not in nodes:
                nodes[endpoint] = {}
    return nodes


def _effective_node(
    *,
    node: str,
    attributes: Mapping[str, str],
    classes: tuple[str, ...],
    rules: tuple[_Rule, ...],
) -> Mapping[str, str] | str:
    """One node's attributes with its stylesheet-resolved backend, or a refusal."""
    if _BACKEND in attributes:
        # Explicit wins outright: `apply_stylesheet` inserts a property only
        # `if !node.attrs.contains_key(prop)`, so no rule can reach this node.
        return attributes
    undecidable = _undecidable_shape_refusal(node=node, attributes=attributes, rules=rules)
    if undecidable is not None:
        return undecidable
    backend = _styled_backend(node=node, attributes=attributes, classes=classes, rules=rules)
    if backend is None:
        return attributes
    return {**attributes, _BACKEND: backend}


def _undecidable_shape_refusal(
    *, node: str, attributes: Mapping[str, str], rules: tuple[_Rule, ...]
) -> str | None:
    """Refuse when a shape rule could set this node's backend and its shape is unknown."""
    if _SHAPE in attributes:
        return None
    for rule in rules:
        if rule.selector.kind == _BY_SHAPE:
            return (
                f"node {node!r} declares no {_SHAPE}, so this dispatch cannot tell "
                f"whether the {_STYLESHEET_ATTRIBUTE} rule {rule.selector.text!r} "
                f"selects it and makes it a coding-agent launch"
            )
    return None


def _styled_backend(
    *,
    node: str,
    attributes: Mapping[str, str],
    classes: tuple[str, ...],
    rules: tuple[_Rule, ...],
) -> str | None:
    """The winning rule's backend for this node, or None when no rule selects it.

    THE LAST MATCH IN ASCENDING-SPECIFICITY ORDER WINS, and that single rule is the
    whole ladder: a later rule in this order can never have a LOWER specificity, so
    overwriting unconditionally already keeps the most specific match, and `sorted`
    being stable makes the tie among equal specificities go to the rule declared
    last. The engine arrives at the same answer by the same route -- it walks its
    own ascending sort and inserts on `spec >= existing_spec`, a comparison that
    cannot fail for the same reason. Keeping a `best` counter here would be dead
    code that merely looked like the Rust.
    """
    winner: str | None = None
    for rule in sorted(rules, key=lambda rule: _SPECIFICITY[rule.selector.kind]):
        if _selects(node=node, attributes=attributes, classes=classes, selector=rule.selector):
            winner = rule.declarations[_BACKEND]
    return winner


def _selects(
    *,
    node: str,
    attributes: Mapping[str, str],
    classes: tuple[str, ...],
    selector: _Selector,
) -> bool:
    """Whether one selector matches one node. A shape match is decidable by here."""
    if selector.kind == _UNIVERSAL:
        return True
    if selector.kind == _BY_ID:
        return node == selector.name
    if selector.kind == _BY_CLASS:
        # The parser's ACCUMULATED membership, which is what the engine matches.
        # Re-deriving it from the node's `class` attribute would be last-wins and
        # would drop every class an earlier declaration contributed.
        return selector.name in classes
    return attributes.get(_SHAPE) == selector.name


def _parse_stylesheet(*, text: str) -> tuple[_Rule, ...] | str:
    """Port of the pinned `fabro-graphviz/src/stylesheet.rs` grammar, or a refusal."""
    cursor = _Text(rest=text.strip())
    rules: list[_Rule] = []
    while cursor.rest:
        selector = _parse_selector(cursor=cursor)
        if isinstance(selector, str):
            return selector
        if not cursor.rest.startswith("{"):
            return f"expected '{{' after the selector {selector.text!r}"
        cursor.advance(count=1)
        declarations = _parse_declarations(cursor=cursor)
        if isinstance(declarations, str):
            return declarations
        cursor.advance(count=1)
        rules.append(_Rule(selector=selector, declarations=declarations))
    return tuple(rules)


def _parse_selector(*, cursor: _Text) -> _Selector | str:
    """`*`, `#id`, `.class`, or a bare word naming a shape.

    Only the universal selector is handled inline, because it carries no name and so
    has no missing-name arm; the other three are the same NAMED shape differing in
    prefix, charset and diagnostic, which `_named_selector` takes as parameters.
    """
    if cursor.rest.startswith("*"):
        cursor.advance(count=1)
        return _Selector(kind=_UNIVERSAL, name="", text="*")
    if cursor.rest.startswith("#"):
        cursor.advance(count=1)
        return _named_selector(
            cursor=cursor,
            kind=_BY_ID,
            prefix="#",
            identifier=True,
            missing="expected an identifier after '#'",
        )
    if cursor.rest.startswith("."):
        cursor.advance(count=1)
        return _named_selector(
            cursor=cursor,
            kind=_BY_CLASS,
            prefix=".",
            identifier=False,
            missing="expected a class name after '.'",
        )
    return _named_selector(
        cursor=cursor,
        kind=_BY_SHAPE,
        prefix="",
        identifier=True,
        # Safe to read the cursor BEFORE the take: a take that finds no name
        # consumes nothing, so this is what is still unconsumed when it fails.
        missing=(
            f"expected a selector ('*', '#id', '.class', or a shape name), found "
            f"{cursor.rest[:_DIAGNOSTIC_WIDTH]!r}"
        ),
    )


def _named_selector(
    *, cursor: _Text, kind: str, prefix: str, identifier: bool, missing: str
) -> _Selector | str:
    """Consume a selector's name under the engine's charset for its kind, or refuse."""
    name = _take_while(cursor=cursor, identifier=identifier)
    if not name:
        return missing
    return _Selector(kind=kind, name=name, text=f"{prefix}{name}")


def _parse_declarations(*, cursor: _Text) -> dict[str, str] | str:
    """`property: value` pairs up to the closing brace, or a refusal."""
    declarations: dict[str, str] = {}
    while not cursor.rest.startswith("}"):
        if not cursor.rest:
            return "the stylesheet ended before a rule's closing '}'"
        if cursor.rest.startswith(";"):
            cursor.advance(count=1)
            continue
        end = _index_where_property_ends(text=cursor.rest)
        prop = cursor.rest[:end]
        cursor.advance(count=end)
        if not cursor.rest.startswith(":"):
            return f"expected ':' after the property name {prop!r}"
        cursor.advance(count=1)
        stop = _index_of_any(text=cursor.rest, chars=";}")
        value = cursor.rest[:stop].strip()
        cursor.advance(count=stop)
        if not value:
            return f"the property {prop!r} has an empty value"
        declarations[prop] = value
    return declarations


def _take_while(*, cursor: _Text, identifier: bool) -> str:
    """Consume the leading run of selector-name characters the engine accepts.

    `identifier` picks between the engine's two character classes: an id or shape
    name takes ASCII alphanumerics plus `_` and `-`, while a class name takes only
    ASCII lowercase, digits and `-`.
    """
    end = 0
    while end < len(cursor.rest) and _is_name_char(char=cursor.rest[end], identifier=identifier):
        end += 1
    taken = cursor.rest[:end]
    cursor.advance(count=end)
    return taken


def _is_name_char(*, char: str, identifier: bool) -> bool:
    if not char.isascii():
        return False
    if identifier:
        return char.isalnum() or char in {"_", "-"}
    return char.islower() or char.isdigit() or char == "-"


def _index_where_property_ends(*, text: str) -> int:
    for index, char in enumerate(text):
        if char == ":" or char.isspace():
            return index
    return len(text)


def _index_of_any(*, text: str, chars: str) -> int:
    for index, char in enumerate(text):
        if char in chars:
            return index
    return len(text)
