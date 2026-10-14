"""Repository publication budgets resolve through the real graph renderer."""

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._config import resolve_node_timeouts
from livespec_orchestrator_beads_fabro.commands._dispatcher_graph_render import (
    render_workflow_graph,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import (
    NodeTimeouts,
    default_node_timeouts,
)

_ROOT = Path(__file__).resolve().parents[2]
_GRAPH = _ROOT / ".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro"


def test_repository_publication_nodes_have_one_hour_budgets() -> None:
    """Scenario 177: this repo raises publication; an adopter still gets 1800s."""
    committed = _GRAPH.read_text(encoding="utf-8")
    defaults = render_workflow_graph(committed_text=committed, timeouts=default_node_timeouts())
    assert not isinstance(defaults, str)
    assert defaults.node_seconds["publish_draft"] == 1800
    assert 'timeout="1800s"' in defaults.text.split("publish_draft [", 1)[1].split("]", 1)[0]
    timeouts = resolve_node_timeouts(cwd=_ROOT)
    assert isinstance(timeouts, NodeTimeouts)
    rendered = render_workflow_graph(committed_text=committed, timeouts=timeouts)
    assert not isinstance(rendered, str)
    for node in ("publish_draft", "pr_refresh"):
        assert rendered.node_seconds[node] == 3600
        assert timeouts.layer_for(node=node) == "repository"
        assert 'timeout="3600s"' in rendered.text.split(f"{node} [", 1)[1].split("]", 1)[0]
