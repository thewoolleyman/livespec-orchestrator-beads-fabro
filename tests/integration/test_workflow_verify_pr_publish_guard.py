"""The publish breaker: a pr stage that publishes nothing must not finish green.

Binds work-item `bd-ib-b6zc`, which re-lands the intent of `bd-ib-32xd` (the
`bd-ib-loks` tail). The `pr` node is an ACP node, and the pinned fabro build can
report an ACP turn that ERRORED as `outcome=succeeded` -- measured 2026-09-08/09,
when an unsupported pr-tier model slug drew an HTTP 400: the turn died, the node
reported succeeded, the run took `pr -> exit` and finished GREEN, and no publish
branch and no pull request existed. The Dispatcher's downstream report was a
generic "no PR found for branch", which reads as a defect in the WORK ITEM rather
than in the pr stage.

WHY THIS MODULE EXISTS TWICE. The first delivery (af366d59, released as 0.146.0)
wired `pr -> verify_pr -> exit` out of three CONDITIONAL edges, which left BOTH
`pr` and `verify_pr` with no unconditional fallback. Fabro rejects that graph with
`all_conditional_edges` on each, so every dispatch on that build died before
running a node, five repositories resolved it, and it was reverted (bc71a9eb). The
original module asserted the two conditions were PRESENT, which is why it passed:
it never asked the question the engine asks. So the assertions that carry this
re-landing are the FALLBACK ones below, and they are written as a whole-graph
invariant with a mutant control rather than as two spot-checks -- inserting a
breaker consumes the SOURCE node's own fallthrough, so the node that breaks is not
always the node that was edited.

The acceptance target is the SHIPPED graph at
`.claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro`, read the
same way the `dead_implementer` breaker's own acceptance reads it, plus the two
production seams that consume a node: the Dispatcher's literal-duration graph
render, and the `fabro run` subprocess ceiling derived from the graph's worst-case
path. `fabro validate` itself is the OTHER half of this guard and is not run here:
`check-fabro-graph-validity` hands every committed graph to the engine, and the
binary is structurally absent inside a Fabro sandbox where this suite runs.

TWO FURTHER ASSERTIONS EXIST BECAUSE THE OBVIOUS CHECK CANNOT FAIL. `verify_pr` is
worthless if `pr -> exit` survives beside it, so the exit edge is asserted to be
verify_pr's ALONE rather than merely present -- an added node with the old edge
left in place satisfies "the node exists" and changes nothing. And the node's
`script` is asserted to survive `render_workflow_graph`, because that rewrite
matches a node block with `[^\\]]*`: a `]` anywhere in a script body silently
truncates the block, the node's timeout never resolves, and the dispatch is
refused by a count mismatch that names no node.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_graph_render import (
    RenderedGraph,
    render_workflow_graph,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import (
    DEFAULT_FABRO_TIMEOUT_SECONDS,
    NodeTimeouts,
    default_node_timeouts,
    derive_fabro_timeout_seconds,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW_DOT = (
    _REPO_ROOT
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "workflow.fabro"
)

_NOT_CREATED = "LIVESPEC_PR_NOT_CREATED"
_CHECK_FAILED = "LIVESPEC_PR_NOT_CREATED_CHECK_FAILED"

# An edge STATEMENT, matched on a stripped line. Every `->` in this graph that is
# not an edge sits inside a `//` comment, which cannot match `\w+` at position
# zero, so comment lines are skipped explicitly and the rest are matched whole.
_EDGE_RE = re.compile(r"^(?P<source>\w+)\s*->\s*(?P<target>\w+)\s*(?:\[(?P<attrs>[^\]]*)\])?$")

# The mutant control: the committed `pr -> verify_pr` fallthrough, and the
# conditional form the reverted release shipped it as.
_FALLTHROUGH = "pr -> verify_pr"
_MUTANT_FALLTHROUGH = 'pr -> verify_pr [condition="outcome=succeeded"]'


@dataclass(frozen=True, kw_only=True)
class _Edge:
    """One `a -> b` statement, and whether fabro would treat it as conditional."""

    source: str
    target: str
    conditional: bool


def _dot_text() -> str:
    return _WORKFLOW_DOT.read_text(encoding="utf-8")


def _verify_pr_body() -> str:
    """The `verify_pr` node's attribute body, or an empty string when absent."""
    block = re.search(r"\bverify_pr\s*\[(?P<body>[^\]]*)\]", _dot_text())
    return "" if block is None else block.group("body")


def _edges(*, text: str) -> tuple[_Edge, ...]:
    """Every edge statement in the graph, in source order."""
    parsed: list[_Edge] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("//"):
            continue
        match = _EDGE_RE.match(line)
        if match is None:
            continue
        attrs = match.group("attrs") or ""
        parsed.append(
            _Edge(
                source=match.group("source"),
                target=match.group("target"),
                conditional="condition=" in attrs,
            )
        )
    return tuple(parsed)


def _sources_lacking_an_unconditional_edge(*, edges: tuple[_Edge, ...]) -> set[str]:
    """Node names whose every outgoing edge carries a condition.

    This is the `all_conditional_edges` rule fabro enforces, evaluated in-repo so
    the invariant is guarded on a suite that runs where the binary does not.
    """
    lacking: set[str] = set()
    for source in {edge.source for edge in edges}:
        outgoing = [edge for edge in edges if edge.source == source]
        if all(edge.conditional for edge in outgoing):
            lacking.add(source)
    return lacking


def test_verify_pr_is_a_script_breaker_in_the_existing_dot_vocabulary() -> None:
    """The guard is a plain script node, like the `implementation_diff` breaker."""
    body = _verify_pr_body()

    assert body != ""
    assert "shape=parallelogram" in body
    assert "script=" in body


def test_verify_pr_asserts_the_publish_branch_carries_this_runs_work() -> None:
    """The check reads origin, and matches a `feat/` head against this run's HEAD.

    Ancestry rather than sha equality is the load-bearing part: fabro commits a
    stage checkpoint once a node completes, so HEAD moves past the sha the pr
    node pushed and an equality test would fail every healthy run.
    """
    body = _verify_pr_body()

    assert "git ls-remote --heads origin" in body
    assert "refs/heads/feat/" in body
    assert "git merge-base --is-ancestor" in body


def test_verify_pr_emits_the_not_created_sentinel_when_nothing_was_published() -> None:
    """A reachable origin carrying no such branch fails with the sentinel.

    Matched WITH its trailing colon, because the unreachable-origin sentinel
    below has this one as a prefix: a bare substring probe passes on the wrong
    arm alone and could never report the missing one.
    """
    body = _verify_pr_body()

    assert f"{_NOT_CREATED}:" in body
    assert "exit 1" in body


def test_an_unanswerable_lookup_is_not_reported_as_an_unpublished_run() -> None:
    """An origin that could not answer carries its OWN sentinel and exit status.

    Both arms fail closed, so a single-sentinel design would pass a naive
    presence check while telling an operator the wrong thing about the run.
    """
    body = _verify_pr_body()

    assert f"{_CHECK_FAILED}:" in body


def test_the_pr_stage_falls_through_to_verify_pr_before_exit() -> None:
    """pr reaches verify_pr, and pr no longer reaches exit itself."""
    edges = _edges(text=_dot_text())
    from_pr = {(edge.target, edge.conditional) for edge in edges if edge.source == "pr"}

    assert ("verify_pr", False) in from_pr
    assert "exit" not in {target for target, _ in from_pr}


def test_verify_pr_owns_the_only_edge_into_exit() -> None:
    """Nothing else reaches exit, so the breaker cannot be routed around.

    The control that matters: `verify_pr` existing beside a surviving
    `pr -> exit` would satisfy every other assertion in this module and change
    nothing about the failure this guard exists to catch.
    """
    edges = _edges(text=_dot_text())
    into_exit = {edge.source for edge in edges if edge.target == "exit"}

    assert into_exit == {"verify_pr"}
    assert any(
        edge.source == "verify_pr" and edge.target == "exit" and edge.conditional for edge in edges
    )


def test_the_pr_node_carries_an_unconditional_outgoing_edge() -> None:
    """pr keeps the fallthrough that inserting the breaker consumed at 0.146.0.

    Named on its own rather than only inside the whole-graph invariant below,
    because `pr` is the node the reverted delivery broke WITHOUT editing its own
    edges: the guard was added after it, and the guard took its fallback.
    """
    assert "pr" not in _sources_lacking_an_unconditional_edge(edges=_edges(text=_dot_text()))


def test_the_verify_pr_node_carries_an_unconditional_outgoing_edge() -> None:
    """The breaker's own failure route is the fallback, not a third condition."""
    edges = _edges(text=_dot_text())

    assert "verify_pr" not in _sources_lacking_an_unconditional_edge(edges=edges)
    assert any(
        edge.source == "verify_pr" and edge.target == "needs_human" and not edge.conditional
        for edge in edges
    )


def test_no_node_in_the_graph_has_only_conditional_outgoing_edges() -> None:
    """The `all_conditional_edges` rule, over the WHOLE graph rather than one node.

    Twice now a merged graph has taken the factory down on this rule -- the
    `review` node on 2026-07-16, `pr` and `verify_pr` on 2026-09-09 -- and both
    times the change carried tests of the node it MEANT to add.
    """
    assert _sources_lacking_an_unconditional_edge(edges=_edges(text=_dot_text())) == set()


def test_the_fallback_invariant_rejects_the_graph_the_revert_undid() -> None:
    """The instrument is POINTED CORRECTLY, not merely present.

    A checker that can only return "no violations" is indistinguishable from a
    healthy graph, so it is run against a mutant of the COMMITTED text: making
    `pr -> verify_pr` conditional reproduces exactly the shape release 0.146.0
    shipped, and `pr` -- not `verify_pr` -- is what must be reported. The
    replacement is asserted to have LANDED, because a mutation that silently
    matched nothing would report the same clean result as a surviving mutant.
    """
    committed = _dot_text()
    mutant = committed.replace(_FALLTHROUGH, _MUTANT_FALLTHROUGH)

    assert mutant != committed
    assert _sources_lacking_an_unconditional_edge(edges=_edges(text=mutant)) == {"pr"}


def test_the_dispatcher_resolves_a_literal_timeout_for_verify_pr() -> None:
    """The node survives the payload's literal-duration rewrite.

    A `]` in the script body would truncate the node block, leaving the node
    with no resolved timeout and refusing the dispatch on a count mismatch that
    names no node -- so this is the assertion that proves the graph is
    dispatchable, not merely well-worded.
    """
    rendered = render_workflow_graph(
        committed_text=_dot_text(),
        timeouts=default_node_timeouts(),
    )

    assert isinstance(rendered, RenderedGraph)
    assert rendered.node_seconds["verify_pr"] == 1800


def test_the_subprocess_ceiling_budgets_the_verify_pr_node() -> None:
    """The `fabro run` ceiling follows the graph, so a new main-path node counts."""
    lengthened = NodeTimeouts(
        configured={"verify_pr": 3600},
        stall_seconds=default_node_timeouts().stall_seconds,
        stall_layer="repository",
    )

    assert derive_fabro_timeout_seconds(timeouts=lengthened) > DEFAULT_FABRO_TIMEOUT_SECONDS
