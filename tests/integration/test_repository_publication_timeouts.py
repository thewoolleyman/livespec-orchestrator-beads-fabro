"""The publication stages resolve their budgets through the real renderer.

Binds the FIRST sub-scenario of `SPECIFICATION/scenarios.md` Scenario 177 --
"publish_draft resolves its timeout from configuration" -- and this
repository's own raise of it, for work-item ``bd-ib-xi63mq``.

WHY BOTH HALVES SIT IN ONE CASE. The scenario's claim is that the node
RESOLVES its limit, and a reading taken at only one layer cannot establish
that: a node whose timeout were still a hard literal would render 1800s for
an unconfigured target exactly as a resolving node does, so the default arm
alone passes for a graph that reads no configuration at all. The repository
arm is what discriminates them, and the default arm is what keeps the
repository arm from being satisfied by a graph that happens to say 3600
everywhere. Neither arm is evidence without the other.

The renderer is the REAL one and the graph is the COMMITTED one, because what
the contract's "Rendering, literally" clause governs is the bytes `fabro run`
receives: the pinned engine types a quoted duration at parse time and never
re-types a rendered string, so a value that reached the attribute as anything
but a literal duration leaves the node with NO timeout at all. Asserting the
rendered `timeout="..."` text, rather than only the resolved integer, is what
reads that byte.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._config import resolve_node_timeouts
from livespec_orchestrator_beads_fabro.commands._dispatcher_graph_render import (
    RenderedGraph,
    render_workflow_graph,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import (
    DEFAULT_NODE_TIMEOUT_SECONDS,
    REPOSITORY_LAYER,
    NodeTimeouts,
    default_node_timeouts,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GRAPH = (
    _REPO_ROOT
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "workflow.fabro"
)

# The budget this repository's publication stages take, and the nodes that take
# it. Both run the repository's declared check suite in a push hook, so both are
# raised together: a refresh bounded at half its sibling's budget fails on the
# same suite one stage later.
_PUBLICATION_NODES = ("publish_draft", "pr_refresh")
_PUBLICATION_SECONDS = 3600


def _rendered(*, timeouts: NodeTimeouts) -> RenderedGraph:
    rendered = render_workflow_graph(
        committed_text=_GRAPH.read_text(encoding="utf-8"), timeouts=timeouts
    )
    assert not isinstance(rendered, str), rendered
    return rendered


def _node_body(*, rendered: RenderedGraph, node: str) -> str:
    """The node's own attribute list, so a sibling's duration cannot satisfy it."""
    after = rendered.text.split(f"{node} [", 1)
    assert len(after) == 2, f"{node} declares no attribute list in the rendered graph"
    return after[1].split("]", 1)[0]


def test_publish_draft_takes_the_unconfigured_default_duration() -> None:
    """Scenario 177: an adopter configuring nothing still renders 1800s."""
    rendered = _rendered(timeouts=default_node_timeouts())

    assert rendered.node_seconds["publish_draft"] == DEFAULT_NODE_TIMEOUT_SECONDS
    body = _node_body(rendered=rendered, node="publish_draft")
    assert f'timeout="{DEFAULT_NODE_TIMEOUT_SECONDS}s"' in body


def test_this_repository_budgets_both_publication_stages_for_one_hour() -> None:
    """Scenario 177: this repository's own node_timeouts raise both stages."""
    timeouts = resolve_node_timeouts(cwd=_REPO_ROOT)
    assert isinstance(timeouts, NodeTimeouts), timeouts
    rendered = _rendered(timeouts=timeouts)

    for node in _PUBLICATION_NODES:
        assert rendered.node_seconds[node] == _PUBLICATION_SECONDS, node
        assert timeouts.layer_for(node=node) == REPOSITORY_LAYER, node
        body = _node_body(rendered=rendered, node=node)
        assert f'timeout="{_PUBLICATION_SECONDS}s"' in body, node
