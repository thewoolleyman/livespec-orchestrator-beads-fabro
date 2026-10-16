"""How one resumed run enters at its unfinished stage, on the published head.

`SPECIFICATION/contracts.md` section "Resume from a published pull request
(`resume --item`)" requires the resumed run to run "the workflow the earlier run's
dispatch record names, with a sandbox that checks out the publish branch at the
published head, entered at the resumed-at stage", and to visit neither `dod_gate`
nor `implement` nor "any other node the earlier run completed". It then names the
latitude this module takes and bounds it: whether the engine is entered at the
node directly "or through a graph the Dispatcher derives from that workflow for
the one run is implementation surface", and "a derived graph is not a registered
variant, is never selectable by the variant precedence, and is never recorded as
the item's workflow."

TWO HALVES, AND THEY FAIL DIFFERENTLY. The graph rewrite decides WHICH STAGE runs;
the prepare step decides WHICH TREE it runs on. Either alone is worse than
neither: entering at `pr` on the default branch publishes nothing the records
describe, and checking out the published head while entering at `dod_gate` spends
a whole sandbox re-implementing work that is already on the branch.

WHY THE REWRITE PRUNES WHAT THE MOVED EDGE ORPHANS. Moving the `start` edge and
leaving every node declared was the earlier shape, and it was accepted by the
pinned 0.254 engine. The Petri-era engine's graph validator REJECTS a declared
node with no route from the start node: measured 2026-10-15T23:36Z against the
hp-candidate server, a `resume --item` died at run-create with
`attractor.unreachable_node: dod_gate is not reachable from the start node`, and
three further nodes named the same way, so no run was ever created and the item
went back to `ready`. The move is therefore paired with a PRUNE of every node the
move orphans, which makes the clause's "no such visit" a property of the graph on
both engines rather than a hope about either.

WHY THE REACHABLE SET IS COMPUTED BY THE SHARED PARSER AND NOT BY A SCAN. This is
the derivation `_dispatcher_dot_graph`'s own docstring warns about: an edge a
line-anchored pattern fails to see makes the reachable set SMALLER, and a smaller
reachable set PRUNES A LIVE NODE — a graph that is not merely unvalidated but
wrong, with nothing announcing the omission. So the node and edge sets come from
`parse_dot_graph`, which tokenizes the grammar, and a graph that parser REFUSES
refuses the derivation too rather than being edited on faith.

The text edit itself is still a span splice, because the derived graph must be the
committed graph MINUS what the prune removes — every surviving node keeps its own
attributes and its own comments, which a re-render from the parsed form would
discard. So the two patterns that LOCATE spans are paired with a POSTCONDITION:
the spliced text is parsed again and must declare exactly the nodes that survived
the prune, with every edge naming one of them. Anything a pattern failed to
locate therefore refuses the derivation instead of reaching a run, which is why
neither pattern has to be as careful as the parser.

WHY AN UNDECLARED NODE REFUSES HERE. The resumed-at stage can come from a factory
run record, which names whatever node THAT engine was executing — possibly a node
this workflow does not declare, if the earlier run ran a different variant.
Pointing `start` at an undeclared name yields a graph that fails validation at
run-create time, which reads as a Dispatcher fault; refusing here names the real
cause, before any run exists.

WHY THE CHECKOUT FETCHES THE BRANCH AND THEN TAKES THE HEAD FROM IT. A forge does
not reliably serve a bare sha (`uploadpack.allowReachableSHA1InWant` is off by
default), so the BRANCH is fetched and the head is checked out from what arrived —
which has the second virtue of proving the head is on that branch rather than
merely reachable somewhere in the repository. And the step fails the run when it
cannot land: a swallowed failure would run the resumed stage against whatever the
clone happens to carry, which is the default branch, and publish a record for a
tree nobody proved.
"""

from __future__ import annotations

import argparse
import re
import shlex
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import (
    DotGraph,
    parse_dot_graph,
)

__all__: list[str] = [
    "RESUME_ENTRY_NODE_ARG",
    "RESUME_HEAD_ARG",
    "ResumeCheckout",
    "graph_entered_at",
    "resume_checkout_for",
    "resume_checkout_prepare_steps_block",
]

# The two `argparse.Namespace` attributes a resume carries into the ordinary
# dispatch path. Named constants rather than literals because they are read
# DEFENSIVELY at two seams that no other command sets them at, and a typo at
# either read is invisible: the attribute simply resolves absent, the dispatch
# proceeds as a plain one, and the resumed run re-implements from `start`.
RESUME_ENTRY_NODE_ARG = "resume_entry_node"
RESUME_HEAD_ARG = "resume_head"

# The unconditional `start` edge, as the committed graph spells it: a bare
# `start -> <target>` line carrying no attribute list. The CONDITIONAL form is
# deliberately not matched — `start` carries exactly one outgoing edge, and fabro
# rejects a node whose every outgoing edge is conditional, so a conditional
# `start` edge is a graph that could never have run.
_START_EDGE = re.compile(r"(?m)^(?P<indent>[ \t]*)start[ \t]*->[ \t]*(?P<target>\w+)[ \t]*$")

# A node DECLARATION and its whole attribute body: a bare name at line start
# followed directly by its attribute bracket. The same shape
# `_dispatcher_graph_render` matches, and for the same reason — an edge line never
# matches, because the name must be followed by the bracket with nothing between.
# Used only to LOCATE the span of a node the parser has already decided to prune,
# never to decide whether a node exists.
_NODE_DECLARATION = r"(?ms)^[ \t]*{name}[ \t]*\[[^\]]*\]"

# One EDGE statement on its own line, with or without an attribute list. Used
# only to LOCATE the span of an edge the parser has already placed, for the same
# reason the declaration pattern is: the parser decides WHICH edges go, and a
# pattern that failed to see one simply leaves that edge in the text, where the
# postcondition below catches it.
_EDGE = re.compile(
    r"(?m)^[ \t]*(?P<source>\w+)[ \t]*->[ \t]*(?P<target>\w+)[ \t]*(?:\[[^\]]*\])?[ \t]*$"
)

_NODE_NAME = re.compile(r"^\w+$")

# The graph's own start node, which is never a prune candidate: it is the root the
# reachability walk starts from, so asking whether it is reachable from itself is
# not a question the derivation has.
_START_NODE = "start"


@dataclass(frozen=True, kw_only=True)
class ResumeCheckout:
    """The publish branch and head one resumed run's sandbox is placed on.

    A pair rather than the head alone, because the fetch needs the BRANCH and the
    checkout needs the HEAD, and taking the head from a branch tip read at
    prepare time would defeat the whole point: the tip may have moved since the
    record was published, which is precisely the state the head-moved refusal
    exists to catch.
    """

    branch: str
    head: str


def graph_entered_at(*, graph_text: str, node: str) -> str | None:
    """The one run's derived graph, entered at `node`, or `None` when it cannot be.

    `None` for five conditions, each of which would otherwise produce a graph
    that fails at run-create time rather than a refusal an operator can read: a
    node name that is not a bare identifier (so it could never be one), a graph
    the shared parser refuses, a node this workflow does not declare, a graph
    carrying no unconditional `start` edge to move, and a spliced result that is
    not the graph the prune intended.
    """
    if _NODE_NAME.match(node) is None:
        return None
    graph = parse_dot_graph(text=graph_text)
    if isinstance(graph, str) or node not in graph.nodes:
        return None
    edge = _START_EDGE.search(graph_text)
    if edge is None:
        return None
    orphaned = _orphaned_by_entering(graph=graph, entry=node)
    derived = _spliced(
        text=graph_text,
        edits=[
            (edge.start(), edge.end(), f"{edge.group('indent')}start -> {node}"),
            *_declaration_spans(graph_text=graph_text, names=orphaned),
            *_edge_spans(graph_text=graph_text, names=orphaned, moved=edge.span()),
        ],
    )
    return _validated(text=derived, declared=frozenset(graph.nodes) - orphaned, entry=node)


def _orphaned_by_entering(*, graph: DotGraph, entry: str) -> frozenset[str]:
    """Every declared node the moved `start` edge leaves with no route to it.

    The walk runs from `entry` rather than from `start`, because `start`'s one
    outgoing edge is the one being rewritten and the committed text still carries
    its old destination. `start` itself is excluded from the result for the reason
    the constant records.
    """
    reached = {entry}
    frontier = [entry]
    while frontier:
        source = frontier.pop()
        for edge in graph.edges:
            if edge.source == source and edge.destination not in reached:
                reached.add(edge.destination)
                frontier.append(edge.destination)
    return frozenset(graph.nodes) - reached - {_START_NODE}


def _declaration_spans(*, graph_text: str, names: frozenset[str]) -> list[tuple[int, int, str]]:
    """A deletion edit for each declaration of each named node.

    Each name is matched as a LITERAL, and every occurrence is taken rather than
    the first: DOT lets a node be declared more than once, and the parser merges
    those declarations into the one node this prune removes.
    """
    spans: list[tuple[int, int, str]] = []
    for name in names:
        pattern = _NODE_DECLARATION.format(name=re.escape(name))
        spans.extend((found.start(), found.end(), "") for found in re.finditer(pattern, graph_text))
    return spans


def _edge_spans(
    *, graph_text: str, names: frozenset[str], moved: tuple[int, int]
) -> list[tuple[int, int, str]]:
    """A deletion edit for each edge line either end of which is a pruned node.

    No REACHABLE node can lose an outgoing edge here, and that is what keeps the
    prune from tripping fabro's `all_conditional_edges` rejection: an edge from a
    reachable source makes its target reachable by definition, so every edge this
    removes has a pruned SOURCE. The one exception is the `start` edge itself,
    whose old target is usually pruned — it is excluded by span, because the
    splice is already rewriting it and two edits for one span would corrupt the
    text rather than merely disagree.
    """
    return [
        (found.start(), found.end(), "")
        for found in _EDGE.finditer(graph_text)
        if found.span() != moved and {found.group("source"), found.group("target")} & names
    ]


def _validated(*, text: str, declared: frozenset[str], entry: str) -> str | None:
    """The derived text, or `None` when it is not the graph the prune intended.

    A POSTCONDITION rather than a second opinion, and it is what lets the two
    span patterns above stay simple: they LOCATE what the parser decided to
    remove, and anything they fail to locate — a declaration whose body carries
    a `]`, an edge chained onto one line — survives into this read and refuses
    the derivation instead of shipping a graph nobody wrote.

    The three questions are the three the engine's own validator asks: does it
    still parse, does it declare exactly the nodes that survived the prune, and
    does every edge name a node it declares. The last one also refuses a
    committed graph carrying an IMPLICITLY declared node — one named only by an
    edge — which this derivation cannot reason about, since such a node is
    absent from `nodes` and so is never a prune candidate however orphaned the
    move leaves it. Refusing a resume there is a resume that does not happen;
    deriving from it is a run created against a graph whose edges do not all
    resolve.
    """
    graph = parse_dot_graph(text=text)
    if (
        isinstance(graph, str)
        or frozenset(graph.nodes) != declared
        or any(
            endpoint not in graph.nodes
            for found in graph.edges
            for endpoint in (found.source, found.destination)
        )
        or not any(
            found.source == _START_NODE and found.destination == entry for found in graph.edges
        )
    ):
        return None
    return text


def _spliced(*, text: str, edits: list[tuple[int, int, str]]) -> str:
    """`text` with each `(start, end, replacement)` edit applied, in offset order.

    Sorted here rather than at each caller because the edits are COLLECTED by
    concern — the moved edge, then the orphaned declarations, then the orphaned
    edges — and a splice walks the text once, so the collection order and the
    offset order are different things.
    """
    pieces: list[str] = []
    cursor = 0
    for start, end, replacement in sorted(edits):
        pieces.append(text[cursor:start])
        pieces.append(replacement)
        cursor = end
    pieces.append(text[cursor:])
    return "".join(pieces)


def resume_checkout_prepare_steps_block(*, checkout: ResumeCheckout | None) -> str:
    """The prepare step that puts the sandbox clone on the published head.

    Rendered as the LAST appended prepare step, which is where the overlay places
    it: the committed steps provision the clone — unshallowing it, installing the
    toolchain and the hooks — and every one of those acts on `.git` or on
    untracked state that a checkout does not disturb, while a checkout performed
    BEFORE them would be unshallowed out from under.

    `""` for no resume, byte-for-byte what the overlay carried before this
    existed, so an ordinary dispatch is untouched by the resume path.
    """
    if checkout is None:
        return ""
    script = " && ".join(
        (
            "set -e",
            f"git fetch --no-tags origin {shlex.quote(f'refs/heads/{checkout.branch}')}",
            f"git checkout --detach {shlex.quote(checkout.head)}",
        )
    )
    return (
        "\n# --- Dispatcher-materialized resume checkout: the publish branch at the\n"
        "# --- head the anchoring Proof of Done record names ---\n"
        "[[run.prepare.steps]]\n"
        f"script = {_toml_basic_string(value=script)}\n"
    )


def resume_checkout_for(*, args: argparse.Namespace, branch: str) -> ResumeCheckout | None:
    """The checkout this dispatch is a resume ONTO, or `None` for a plain dispatch.

    The head is read off the invocation rather than from the branch tip, and the
    difference is the whole guarantee: a tip read here, at prepare time, may have
    moved since the anchoring record was published — which is exactly the state
    the head-moved refusal exists to catch, so resolving it here would quietly
    undo that refusal for every resume that got past it.

    Read DEFENSIVELY, because every dispatch entry point reaches the overlay
    through this seam and only the resume one sets these attributes.

    The BRANCH is a parameter rather than derived here from the work-item id,
    because the one function that derives it lives downstream of the engine and
    importing it would close a cycle through the overlay this module feeds. The
    caller already holds the item, so it is the party with nothing to resolve.
    """
    head = getattr(args, RESUME_HEAD_ARG, None)
    if not isinstance(head, str) or not head:
        return None
    return ResumeCheckout(branch=branch, head=head)


def _toml_basic_string(*, value: str) -> str:
    """One TOML basic string, escaping what a basic string cannot carry raw.

    Spelled here rather than borrowed from the overlay's own escaper because this
    module must not import the overlay: the overlay imports THIS one to render the
    block, and the reverse edge would close a cycle.
    """
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
