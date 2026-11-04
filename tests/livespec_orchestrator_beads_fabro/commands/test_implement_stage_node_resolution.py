"""The Red/Green node names retain the implement stage's configuration surface.

The graph changes in a later slice.  This test exercises its future node names
against today's resolver so that the graph split cannot turn `implement` into
three independently configured adapter or timeout keys.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import (
    ACP_NODES,
    AcpNodeOverlay,
)
from livespec_orchestrator_beads_fabro.commands._acp_node_layers import resolve_acp_nodes
from livespec_orchestrator_beads_fabro.commands._dispatcher_graph_adapters import (
    render_acp_commands,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_graph_render import (
    render_workflow_graph,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import (
    DEFAULT_NODE_TIMEOUT_SECONDS,
    default_node_timeouts,
    node_timeouts_from_block,
)

_IMPLEMENT_ADAPTER = "implement-adapter --model compatible"
_IMPLEMENT_TIMEOUT = 4137
_COMMIT_RED_TIMEOUT = 311
_COMMIT_GREEN_TIMEOUT = 719

_GRAPH = """digraph ImplementWorkItem {
    graph [
        stall_timeout="7200s"
    ]

    red [
        backend="acp"
        acp.command="{{ inputs.implement_adapter }}"
        timeout="1800s"
    ]

    commit_red [
        shape=parallelogram
        timeout="1800s"
        script="commit red"
    ]

    green [
        backend="acp"
        acp.command="{{ inputs.implement_adapter }}"
        timeout="1800s"
    ]

    commit_green [
        shape=parallelogram
        timeout="1800s"
        script="commit green"
    ]
}
"""


def test_red_green_and_commit_nodes_keep_the_implement_stage_configuration_boundary() -> None:
    """Red/Green share `implement`; command nodes have only their own timeout keys."""
    resolution = resolve_acp_nodes(
        workflow_inputs={"implement_adapter": "workflow-default"},
        repository={"implement": AcpNodeOverlay(command=_IMPLEMENT_ADAPTER)},
        dispatch={},
    )
    assert not isinstance(resolution, str), resolution
    assert "implement" in ACP_NODES
    assert "red" not in ACP_NODES
    assert "green" not in ACP_NODES
    assert set(resolution.nodes) == {"implement"}

    commands = render_acp_commands(
        graph_text=_GRAPH,
        adapters={"implement_adapter": resolution.nodes["implement"].rendered},
    )
    assert not isinstance(commands, str), commands
    assert commands.node_commands == {
        "red": _IMPLEMENT_ADAPTER,
        "green": _IMPLEMENT_ADAPTER,
    }

    configured = node_timeouts_from_block(
        block={
            "node_timeouts": {
                "implement": _IMPLEMENT_TIMEOUT,
                "commit_red": _COMMIT_RED_TIMEOUT,
                "commit_green": _COMMIT_GREEN_TIMEOUT,
            }
        }
    )
    assert not isinstance(configured, str), configured
    rendered = render_workflow_graph(committed_text=_GRAPH, timeouts=configured)
    assert not isinstance(rendered, str), rendered
    assert rendered.node_seconds == {
        "red": _IMPLEMENT_TIMEOUT,
        "commit_red": _COMMIT_RED_TIMEOUT,
        "green": _IMPLEMENT_TIMEOUT,
        "commit_green": _COMMIT_GREEN_TIMEOUT,
    }
    assert configured.layer_for(node="red") == "repository"
    assert configured.layer_for(node="green") == "repository"
    assert default_node_timeouts().seconds_for(node="red") == DEFAULT_NODE_TIMEOUT_SECONDS
    assert default_node_timeouts().seconds_for(node="green") == DEFAULT_NODE_TIMEOUT_SECONDS
