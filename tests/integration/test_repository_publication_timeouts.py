"""Scenario 177: publication stages receive this repository's timeout policy."""

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._config import resolve_node_timeouts
from livespec_orchestrator_beads_fabro.commands._dispatcher_graph_render import (
    RenderedGraph,
    render_workflow_graph,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import (
    NodeTimeouts,
    default_node_timeouts,
)


def test_repository_publication_nodes_render_one_hour() -> None:
    """Read the actual repository config and graph, with the default as control."""
    repo = Path(__file__).resolve().parents[2]
    graph = (repo / ".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro").read_text(
        encoding="utf-8"
    )
    defaulted = render_workflow_graph(committed_text=graph, timeouts=default_node_timeouts())
    assert isinstance(defaulted, RenderedGraph)
    assert defaulted.node_seconds["publish_draft"] == 1800
    timeouts = resolve_node_timeouts(cwd=repo)
    assert isinstance(timeouts, NodeTimeouts)
    rendered = render_workflow_graph(committed_text=graph, timeouts=timeouts)
    assert isinstance(rendered, RenderedGraph)
    for node in ("publish_draft", "pr_refresh"):
        assert rendered.node_seconds[node] == 3600
        body = rendered.text.split(f"    {node} [", 1)[1].split("]", 1)[0]
        assert 'timeout="3600s"' in body
        assert timeouts.layer_for(node=node) == "repository"
