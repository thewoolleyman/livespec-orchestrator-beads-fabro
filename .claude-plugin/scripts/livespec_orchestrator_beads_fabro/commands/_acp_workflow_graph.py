"""The workflow graph as NODES, ATTRIBUTES and EDGES -- nothing interpreted.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" requires that "The workflow MUST expose the ACP nodes that
dominate every green terminal path", and that "An unsupported or ambiguous
workflow graph MUST refuse fallback-enabled dispatch instead of guessing."
Both obligations are answered from the graph's OWN declarations, so this
module reads the committed DOT text and answers only three questions: what
nodes exist, what each one declared, and which node points at which.

WHY A READER RATHER THAN A HARD-CODED NODE LIST. The contract names
`implement`, `review` and `pr` as the current graph's success-critical set,
and naming them in code would satisfy today's graph by coincidence: a
registered variant that inserts a second publish node, or renames one, would
keep passing while the set it enforces is silently wrong. The derivation in
`_acp_success_critical` therefore consumes THIS structure, and the contract's
three names are an assertion about the current graph rather than an input.

WHY THE PATTERNS MIRROR `_dispatcher_graph_render`. That module already scans
this exact file shape fail-closed on every dispatch, so its node-block pattern
is the one shape proven against the committed graph. The body admits no `]` of
its own, which is what keeps a single-line declaration (`start [shape=Mdiamond,
...]`) from swallowing the multi-line block that follows it. Edge lines never
match it: a node name must be followed directly by the bracket.

ATTRIBUTES ARE FIRST-WINS, DELIBERATELY. A `script="..."` value carries
backslash-escaped quotes, so a naive quoted-string scan ends that value early
and resumes reading its shell text as though it were attribute syntax. Every
attribute this module is asked for -- `shape`, `backend` -- is declared BEFORE
the script attribute in every node of the committed graph, so taking the first
binding for a key makes a spurious later match unable to displace a real
earlier one.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

__all__: list[str] = [
    "ACP_BACKEND",
    "GRAPH_BLOCK_NAME",
    "GREEN_TERMINAL_SHAPE",
    "START_SHAPE",
    "WorkflowGraph",
    "WorkflowNode",
    "parse_workflow_graph",
]

# The attribute-carrying block that declares graph-level options rather than a
# node. It is filtered out here rather than by every caller, because it is not
# a node in any sense the dominator derivation could use.
GRAPH_BLOCK_NAME = "graph"

# Fabro's own DOT vocabulary for the two ends of a run: `Mdiamond` is the
# entry node and `Msquare` the GREEN terminal. Every other terminal in this
# repository's graph is a plain `parallelogram` command node whose script
# exits non-zero, which is exactly what makes shape the honest discriminator
# rather than a name list.
START_SHAPE = "Mdiamond"
GREEN_TERMINAL_SHAPE = "Msquare"

# The backend value that makes a node an ACP node -- the only nodes a
# candidate chain can attach to.
ACP_BACKEND = "acp"

_NODE_BLOCK_RE = re.compile(r"(?ms)^[ \t]*(?P<name>\w+)[ \t]*\[(?P<body>[^\]]*)\]")
_EDGE_RE = re.compile(r"(?m)^[ \t]*(?P<source>\w+)[ \t]*->[ \t]*(?P<target>\w+)")
_ATTR_RE = re.compile(r'(?P<key>[\w.]+)[ \t]*=[ \t]*(?:"(?P<quoted>[^"]*)"|(?P<bare>[^\s,\]]+))')


@dataclass(frozen=True, kw_only=True)
class WorkflowNode:
    """One declared node and the attributes it carries, verbatim."""

    name: str
    attributes: Mapping[str, str]

    @property
    def shape(self) -> str | None:
        """The declared `shape`, or `None` when the node declares none."""
        return self.attributes.get("shape")

    @property
    def is_acp(self) -> bool:
        """Whether this node runs an ACP adapter, per its own `backend`."""
        return self.attributes.get("backend") == ACP_BACKEND


@dataclass(frozen=True, kw_only=True)
class WorkflowGraph:
    """Declared nodes in declaration order, and the edges between them.

    Declaration order is retained rather than sorted so every derived list
    -- the success-critical set above all -- reads in the order an operator
    sees in the committed file.
    """

    nodes: tuple[WorkflowNode, ...]
    edges: tuple[tuple[str, str], ...]

    @property
    def names(self) -> tuple[str, ...]:
        """Every declared node name, in declaration order."""
        return tuple(node.name for node in self.nodes)

    @property
    def acp_names(self) -> frozenset[str]:
        """Every node whose own `backend` attribute says it is an ACP node."""
        return frozenset(node.name for node in self.nodes if node.is_acp)

    def successors(self, *, node: str) -> tuple[str, ...]:
        """Every node this one points at, in edge-declaration order."""
        return tuple(target for source, target in self.edges if source == node)

    def predecessors(self, *, node: str) -> tuple[str, ...]:
        """Every node pointing at this one, in edge-declaration order."""
        return tuple(source for source, target in self.edges if target == node)

    def with_shape(self, *, shape: str) -> tuple[str, ...]:
        """Every node declaring exactly this shape, in declaration order."""
        return tuple(node.name for node in self.nodes if node.shape == shape)


def parse_workflow_graph(*, text: str) -> WorkflowGraph:
    """Read the committed graph's nodes, attributes and edges.

    Total by construction: a text declaring nothing this recognizes yields an
    empty graph rather than a refusal, because "unsupported" is a judgement
    the derivation makes against what a fallback-enabled dispatch needs, not
    one a reader can make about arbitrary text.
    """
    nodes: list[WorkflowNode] = []
    seen: set[str] = set()
    for match in _NODE_BLOCK_RE.finditer(text):
        name = match.group("name")
        if name == GRAPH_BLOCK_NAME or name in seen:
            continue
        seen.add(name)
        nodes.append(WorkflowNode(name=name, attributes=_attributes(body=match.group("body"))))
    edges = tuple(
        (match.group("source"), match.group("target")) for match in _EDGE_RE.finditer(text)
    )
    return WorkflowGraph(nodes=tuple(nodes), edges=edges)


def _attributes(*, body: str) -> Mapping[str, str]:
    """Bind each attribute key to its FIRST value in this block -- see the docstring."""
    attributes: dict[str, str] = {}
    for match in _ATTR_RE.finditer(body):
        key = match.group("key")
        if key in attributes:
            continue
        quoted = match.group("quoted")
        attributes[key] = quoted if quoted is not None else match.group("bare")
    return attributes
