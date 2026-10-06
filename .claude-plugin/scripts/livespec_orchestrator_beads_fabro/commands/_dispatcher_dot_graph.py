"""Read a Fabro workflow graph into nodes, edges and attributes, or refuse.

WHY A PARSER AND NOT A SET OF REGEXES. Every consumer of a workflow graph in
this tree so far has scanned it with patterns, and that is sound for the one
job `_dispatcher_graph_render` does -- REWRITE each `timeout` attribute, which
fails loudly by count if a pattern misses one. It is NOT sound for deriving a
MAXIMUM, where every construct a scan fails to see makes the answer SMALLER and
nothing announces the omission. Three measured instances, each a valid input to
the pinned engine's own grammar (`fabro-graphviz/src/parser/grammar.rs`
accepts `many0(statement)`, optional semicolons, chained edges and quoted
attribute values):

- `start -> a; a -> a; a -> exit;` on ONE line. A line-anchored edge pattern
  sees the first edge and silently drops the other two, including a self-loop
  that makes the graph unbounded.
- `a [timeout="1800s", label="max_visits=3"]`. A body-wide `max_visits` search
  reads a LABEL as an enforced node cap. A label is documentation.
- `script="echo '.[0]'"` before a `timeout`. A body pattern that stops at the
  first `]` truncates the node and loses the timeout entirely.

So this module tokenizes the graph and parses the statement grammar, which
makes an attribute a KEY/VALUE PAIR rather than a substring, an edge chain
every hop it declares, and a quoted value opaque to all of it.

FAIL CLOSED ON ANYTHING NOT MODELLED. A character the lexer cannot classify, a
statement shape this grammar does not cover (`subgraph`, a `{ ... }` block, a
`node [...]` / `edge [...]` default-attribute statement that would silently
re-base every later declaration, an undirected `--` edge), or a graph that ends
before its closing brace all return a refusal STRING naming what was found.
Refusing an input we do not model is honest; parsing half of it and reporting a
maximum is not.

WHAT THIS MODULE DELIBERATELY DOES NOT DO. It does not interpret any attribute.
`condition`, `timeout`, `max_visits` and the rest come back as the raw strings
the graph carries, and what they MEAN -- whether a condition necessarily bounds
an edge, whether a timeout resolves from configuration -- belongs to the caller
that has the policy. An implicitly-declared node (one named only by an edge)
is likewise NOT invented here: it is simply absent from `nodes`, so a caller
that needs every endpoint declared can say so itself.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from itertools import pairwise

__all__: list[str] = [
    "DotEdge",
    "DotGraph",
    "parse_dot_graph",
]

# One pass, longest-construct-first. `string` must precede everything that
# could match a quote (nothing does), and `arrow` / `undirected` must precede
# `word`, whose numeral alternative starts with an optional `-`.
_TOKEN_RE = re.compile(
    r"""
      (?P<space>\s+)
    | (?P<line_comment>//[^\n]*|\#[^\n]*)
    | (?P<block_comment>/\*.*?\*/)
    | (?P<string>"(?:\\.|[^"\\])*")
    | (?P<arrow>->)
    | (?P<undirected>--)
    | (?P<punct>[\[\]{}=,;])
    | (?P<word>[A-Za-z_][A-Za-z_0-9.]*|-?\.?[0-9][0-9.]*)
    """,
    re.VERBOSE | re.DOTALL,
)
_IGNORED_TOKEN_KINDS = frozenset({"space", "line_comment", "block_comment"})
_VALUE_KINDS = frozenset({"word", "string"})
_GRAPH_KEYWORD = "graph"
_HEADER_KEYWORDS = frozenset({"digraph", "graph"})
_STRICT_KEYWORD = "strict"
# Statement-opening words this grammar refuses rather than models. A default
# attribute statement silently re-bases every node or edge declared after it,
# so reading one as an ordinary node declaration would be the same silent-loss
# class this module exists to close.
_UNSUPPORTED_KEYWORDS = frozenset({"subgraph", "node", "edge"})
_STATEMENT_SEPARATOR = ";"


@dataclass(frozen=True, kw_only=True)
class DotEdge:
    """One hop of one edge statement, with that statement's attributes.

    A chained statement `a -> b -> c` yields TWO of these, each carrying the
    same attribute list, which is what the engine does with it.
    """

    source: str
    destination: str
    attributes: Mapping[str, str]


@dataclass(frozen=True, kw_only=True)
class DotGraph:
    """A parsed workflow graph: its own attributes, its nodes, and its edges.

    `nodes` maps a declared node name to its merged attribute mapping -- DOT
    lets a node be declared more than once and the later value of a repeated
    key wins. A node named ONLY by an edge is absent, deliberately; see the
    module docstring.
    """

    attributes: Mapping[str, str]
    nodes: Mapping[str, Mapping[str, str]]
    edges: tuple[DotEdge, ...]


@dataclass(kw_only=True)
class _Cursor:
    """A token list and a position in it, with no lookahead beyond one token."""

    tokens: Sequence[tuple[str, str]]
    index: int = 0

    def peek(self) -> tuple[str, str] | None:
        return self.tokens[self.index] if self.index < len(self.tokens) else None

    def take(self) -> tuple[str, str] | None:
        token = self.peek()
        if token is not None:
            self.index += 1
        return token

    def accept(self, *, value: str) -> bool:
        token = self.peek()
        if token is None or token[1] != value:
            return False
        self.index += 1
        return True


@dataclass(kw_only=True)
class _Body:
    """What a statement accumulates into, so each parse step returns a refusal only."""

    attributes: dict[str, str] = field(default_factory=dict[str, str])
    nodes: dict[str, dict[str, str]] = field(default_factory=dict[str, dict[str, str]])
    edges: list[DotEdge] = field(default_factory=list[DotEdge])


def parse_dot_graph(*, text: str) -> DotGraph | str:
    """Parse one workflow graph, or return a refusal naming what defeated it."""
    tokens = _tokenize(text=text)
    if isinstance(tokens, str):
        return tokens
    cursor = _Cursor(tokens=tokens)
    header = _parse_header(cursor=cursor)
    if header is not None:
        return header
    body = _Body()
    while True:
        token = cursor.peek()
        if token is None:
            return "the workflow graph ends before its closing brace"
        if token[1] == "}":
            _ = cursor.take()
            return DotGraph(
                attributes=body.attributes,
                nodes=body.nodes,
                edges=tuple(body.edges),
            )
        refusal = _parse_statement(cursor=cursor, body=body)
        if refusal is not None:
            return refusal


def _tokenize(*, text: str) -> list[tuple[str, str]] | str:
    """Every meaningful token as `(kind, value)`, or a refusal naming the first
    character this lexer cannot classify.

    A quoted value comes back DECODED, so a `\\"` inside a shell script is one
    character to every later step and can never be mistaken for a delimiter.
    """
    tokens: list[tuple[str, str]] = []
    position = 0
    while position < len(text):
        match = _TOKEN_RE.match(text, position)
        if match is None:
            return (
                f"the workflow graph carries syntax this parse does not model: "
                f"unexpected {text[position]!r} at offset {position}"
            )
        position = match.end()
        kind = match.lastgroup or ""
        if kind in _IGNORED_TOKEN_KINDS:
            continue
        if kind == "undirected":
            return (
                "the workflow graph carries an undirected `--` edge, which this "
                "parse does not model"
            )
        tokens.append((kind, _token_value(kind=kind, raw=match.group())))
    return tokens


def _token_value(*, kind: str, raw: str) -> str:
    if kind != "string":
        return raw
    return re.sub(r"\\(.)", r"\1", raw[1:-1])


def _parse_header(*, cursor: _Cursor) -> str | None:
    """Consume `[strict] (digraph|graph) [name] {`, or refuse."""
    _ = cursor.accept(value=_STRICT_KEYWORD)
    keyword = cursor.take()
    if keyword is None or keyword[1] not in _HEADER_KEYWORDS:
        return "the workflow graph does not open with a `digraph` declaration"
    token = cursor.peek()
    if token is not None and token[0] in _VALUE_KINDS:
        _ = cursor.take()
    if not cursor.accept(value="{"):
        return "the workflow graph's declaration is not followed by an opening brace"
    return None


def _parse_statement(*, cursor: _Cursor, body: _Body) -> str | None:
    """Parse one statement into `body`, or return a refusal."""
    head = cursor.take()
    if head is None or head[0] not in _VALUE_KINDS:
        return f"the workflow graph carries a statement this parse does not model: {head!r}"
    name = head[1]
    if name in _UNSUPPORTED_KEYWORDS:
        return (
            f"the workflow graph carries a `{name}` statement, which this parse " f"does not model"
        )
    if name == _GRAPH_KEYWORD:
        return _parse_graph_attributes(cursor=cursor, body=body)
    if cursor.accept(value="="):
        return _parse_graph_assignment(cursor=cursor, body=body, key=name)
    if cursor.accept(value="->"):
        return _parse_edge_statement(cursor=cursor, body=body, first=name)
    return _parse_node_statement(cursor=cursor, body=body, name=name)


def _parse_graph_attributes(*, cursor: _Cursor, body: _Body) -> str | None:
    attributes = _parse_attribute_list(cursor=cursor)
    if isinstance(attributes, str):
        return attributes
    body.attributes.update(attributes)
    _ = cursor.accept(value=_STATEMENT_SEPARATOR)
    return None


def _parse_graph_assignment(*, cursor: _Cursor, body: _Body, key: str) -> str | None:
    value = cursor.take()
    if value is None or value[0] not in _VALUE_KINDS:
        return f"the workflow graph assigns `{key}` a value this parse does not model"
    body.attributes[key] = value[1]
    _ = cursor.accept(value=_STATEMENT_SEPARATOR)
    return None


def _parse_edge_statement(*, cursor: _Cursor, body: _Body, first: str) -> str | None:
    """Parse `a -> b (-> c)* [attrs]`, emitting one `DotEdge` per hop."""
    chain = [first]
    while True:
        target = cursor.take()
        if target is None or target[0] not in _VALUE_KINDS:
            return "the workflow graph carries an edge with no destination"
        chain.append(target[1])
        if not cursor.accept(value="->"):
            break
    attributes = _parse_attribute_list(cursor=cursor)
    if isinstance(attributes, str):
        return attributes
    body.edges.extend(
        DotEdge(source=source, destination=destination, attributes=attributes)
        for source, destination in pairwise(chain)
    )
    _ = cursor.accept(value=_STATEMENT_SEPARATOR)
    return None


def _parse_node_statement(*, cursor: _Cursor, body: _Body, name: str) -> str | None:
    attributes = _parse_attribute_list(cursor=cursor)
    if isinstance(attributes, str):
        return attributes
    body.nodes.setdefault(name, {}).update(attributes)
    _ = cursor.accept(value=_STATEMENT_SEPARATOR)
    return None


def _parse_attribute_list(*, cursor: _Cursor) -> dict[str, str] | str:
    """Parse an optional `[ key=value, ... ]`; an absent list is an empty one."""
    if not cursor.accept(value="["):
        return {}
    attributes: dict[str, str] = {}
    while True:
        if cursor.accept(value="]"):
            return attributes
        key = cursor.take()
        if key is None or key[0] not in _VALUE_KINDS:
            return "the workflow graph carries an attribute list this parse does not model"
        if not cursor.accept(value="="):
            return f"the workflow graph's attribute `{key[1]}` carries no value"
        value = cursor.take()
        if value is None or value[0] not in _VALUE_KINDS:
            return f"the workflow graph's attribute `{key[1]}` carries no value"
        attributes[key[1]] = value[1]
        # DOT separates attributes with `,`, with `;`, or with nothing at all;
        # the shipped graph uses both of the latter two.
        _ = cursor.accept(value=",") or cursor.accept(value=";")
