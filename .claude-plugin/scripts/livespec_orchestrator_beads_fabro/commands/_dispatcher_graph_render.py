"""Literal-duration rendering of the dispatch payload's workflow graph.

WHY THE VALUES ARE WRITTEN IN RATHER THAN TEMPLATED, and why this is not
re-litigable from the source: the pinned Fabro 0.254 build types a quoted
duration attribute as a duration AT PARSE TIME, `Node::timeout` reads it
through an accessor that answers only for that type, and the template
expansion rewrites string values without ever re-typing what it rendered.
So a `timeout` templated from a workflow input renders to a STRING, the
accessor yields nothing, and the node runs with NO TIMEOUT AT ALL -- the
exact opposite of what a configurable timeout is for, with no diagnostic
anywhere. The `acp.command` attribute is a string on both sides, which is
why templating works there and cannot be copied to here.

The Dispatcher therefore renders the resolved values into the payload's own
copy of the graph as literal durations before `fabro run` sees it, and the
paired test asserts that no rendered timeout attribute carries a template
opener. See `SPECIFICATION/contracts.md` section "ACP node timeouts".
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._node_timeouts import NodeTimeouts

__all__: list[str] = [
    "RenderedGraph",
    "node_timeout_seconds",
    "render_workflow_graph",
]

# A node's attribute list: a bare name at line start, then a bracketed body.
# The body admits no `]` of its own, which is what keeps a SINGLE-LINE node
# declaration (`start [shape=Mdiamond, ...]`) from swallowing the multi-line
# block that follows it -- a non-greedy scan to the next standalone `]` line
# would do exactly that, and would then attribute one node's timeout to
# another. Edge lines (`a -> b [label=...]`) never match: the name must be
# followed directly by the bracket.
_NODE_BLOCK_RE = re.compile(r"(?ms)^[ \t]*(?P<name>\w+)[ \t]*\[(?P<body>[^\]]*)\]")

# The negative lookbehind is load-bearing: without it the node-timeout
# pattern also matches the tail of `stall_timeout=`, and the run-level
# watchdog would silently take a node's value.
_TIMEOUT_ATTR_RE = re.compile(r'(?<![\w.])timeout[ \t]*=[ \t]*"[^"]*"')
_STALL_ATTR_RE = re.compile(r'(?<![\w.])stall_timeout[ \t]*=[ \t]*"[^"]*"')

_GRAPH_BLOCK_NAME = "graph"


@dataclass(frozen=True, kw_only=True)
class RenderedGraph:
    """A workflow graph carrying resolved literal durations.

    `node_seconds` is what each node's attribute actually received, so the
    dispatch record reports the rendered values rather than a
    re-derivation of them.
    """

    text: str
    node_seconds: Mapping[str, int]
    stall_seconds: int


def render_workflow_graph(*, committed_text: str, timeouts: NodeTimeouts) -> RenderedGraph | str:
    """Rewrite every timeout attribute to its resolved literal duration.

    Returns the rendered graph, or an actionable refusal message when the
    committed graph does not have the shape this rewrite understands.

    FAIL-CLOSED BY COUNT. Every `timeout` attribute in the committed text
    must be reached by a node block, and the run-level `stall_timeout` must
    appear exactly once; anything else refuses the dispatch rather than
    shipping a graph whose timeouts are PART resolved. That matters more
    than it looks: a partially-rewritten graph runs, and the node the
    rewrite missed keeps a stale literal that no configuration can move --
    a silent divergence between what the record says the run was budgeted
    and what the run actually enforced.
    """
    expected_nodes = len(_TIMEOUT_ATTR_RE.findall(committed_text))
    expected_stalls = len(_STALL_ATTR_RE.findall(committed_text))
    if expected_stalls != 1:
        return (
            "workflow graph is not renderable: expected exactly one "
            f"stall_timeout attribute, found {expected_stalls}"
        )
    rendered = _rewrite_blocks(committed_text=committed_text, timeouts=timeouts)
    if len(rendered.node_seconds) != expected_nodes:
        return (
            "workflow graph is not renderable: "
            f"{expected_nodes} timeout attributes are declared but "
            f"{len(rendered.node_seconds)} resolved to a node"
        )
    return rendered


def node_timeout_seconds(*, graph_text: str, node: str) -> int | None:
    """The literal duration one node's `timeout` attribute carries, in seconds.

    READ BACK OUT of a graph rather than re-derived from configuration, which is
    the whole point: a command node that has to enforce its own limit must
    enforce the one its attribute actually received, and the two can differ --
    a per-dispatch override, a payload rendered from a different resolution, or
    a node the rewrite did not reach. Asking the artifact closes that gap by
    construction instead of by two readings that are hoped to agree.

    Answers None rather than a default when the node is absent, carries no
    timeout, or carries one this reader cannot parse as whole seconds. The
    caller is expected to WITHHOLD the figure in that case, never to substitute
    one: a bound enforced against an invented limit would report that invented
    number as the limit that ended the operation.
    """
    for match in _NODE_BLOCK_RE.finditer(graph_text):
        if match.group("name") != node:
            continue
        attribute = _TIMEOUT_ATTR_RE.search(match.group("body"))
        if attribute is None:
            return None
        digits = attribute.group(0).partition('"')[2].rstrip('"').removesuffix("s")
        return int(digits) if digits.isdigit() else None
    return None


def _rewrite_blocks(*, committed_text: str, timeouts: NodeTimeouts) -> RenderedGraph:
    """Splice each node block's rewritten body back into the graph text."""
    pieces: list[str] = []
    node_seconds: dict[str, int] = {}
    stall_seconds = timeouts.stall_seconds
    cursor = 0
    for match in _NODE_BLOCK_RE.finditer(committed_text):
        name = match.group("name")
        body = match.group("body")
        if name == _GRAPH_BLOCK_NAME:
            body = _STALL_ATTR_RE.sub(f'stall_timeout="{stall_seconds}s"', body)
        else:
            seconds = timeouts.seconds_for(node=name)
            body, applied = _TIMEOUT_ATTR_RE.subn(f'timeout="{seconds}s"', body)
            if applied:
                node_seconds[name] = seconds
        pieces.append(committed_text[cursor : match.start("body")])
        pieces.append(body)
        cursor = match.end("body")
    pieces.append(committed_text[cursor:])
    return RenderedGraph(
        text="".join(pieces),
        node_seconds=node_seconds,
        stall_seconds=stall_seconds,
    )
