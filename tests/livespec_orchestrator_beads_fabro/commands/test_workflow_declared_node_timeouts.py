"""Scenario 325's workflow/default/repository/argument timeout resolution."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_graph_render import (
    node_timeout_seconds,
    render_workflow_graph,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import (
    ARGUMENT_LAYER,
    BUILT_IN_DEFAULT_LAYER,
    REPOSITORY_LAYER,
    WORKFLOW_LAYER,
    default_node_timeouts,
    node_timeouts_from_block,
    node_timeouts_journal_record,
    node_timeouts_with_arguments,
)

_GRAPH = """digraph ImplementWorkItem {
    graph [
        stall_timeout="7200s"
    ]
    fix_commit_settle [
        timeout="3900s"
        script="runner settle --timeout-seconds 3600"
    ]
    pr_route [
        timeout="600s"
    ]
    undeclared_node [
        shape=parallelogram
    ]
}
"""


def test_resolution_layers_render_and_journal_their_effective_values() -> None:
    """Workflow, repository, argument and built-in values stay distinguishable."""
    configured = node_timeouts_from_block(block={"node_timeouts": {"pr_route": 900}})
    assert not isinstance(configured, str), configured
    resolved = node_timeouts_with_arguments(timeouts=configured, arguments=("pr_route=1200",))
    assert not isinstance(resolved, str), resolved

    rendered = render_workflow_graph(committed_text=_GRAPH, timeouts=resolved)

    assert not isinstance(rendered, str), rendered
    assert rendered.node_seconds == {
        "fix_commit_settle": 3900,
        "pr_route": 1200,
        "undeclared_node": 1800,
    }
    assert node_timeout_seconds(graph_text=rendered.text, node="undeclared_node") == 1800
    assert "settle --timeout-seconds 3600" in rendered.text
    record = node_timeouts_journal_record(timeouts=rendered.timeouts, nodes=rendered.node_seconds)
    assert record["node_timeouts"] == {
        "fix_commit_settle": {"seconds": 3900, "layer": WORKFLOW_LAYER},
        "pr_route": {"seconds": 1200, "layer": ARGUMENT_LAYER},
        "undeclared_node": {"seconds": 1800, "layer": BUILT_IN_DEFAULT_LAYER},
    }
    assert configured.layer_for(node="pr_route") == REPOSITORY_LAYER


def test_a_short_settle_timeout_rewrites_its_wait_and_refuses_without_room() -> None:
    """The settle script ends 300 seconds before the engine can cut it."""
    configured = node_timeouts_from_block(block={"node_timeouts": {"fix_commit_settle": 1800}})
    assert not isinstance(configured, str), configured
    rendered = render_workflow_graph(committed_text=_GRAPH, timeouts=configured)
    assert not isinstance(rendered, str), rendered
    assert "settle --timeout-seconds 1500" in rendered.text

    too_short = node_timeouts_from_block(block={"node_timeouts": {"fix_commit_settle": 300}})
    assert not isinstance(too_short, str), too_short
    refusal = render_workflow_graph(committed_text=_GRAPH, timeouts=too_short)
    assert isinstance(refusal, str)
    assert "fix_commit_settle" in refusal
    assert "300" in refusal


def test_an_invalid_workflow_declaration_refuses_before_rendering() -> None:
    """The workflow layer must name a positive literal duration."""
    refusal = render_workflow_graph(
        committed_text=_GRAPH.replace('timeout="600s"', 'timeout="later"'),
        timeouts=default_node_timeouts(),
    )
    assert isinstance(refusal, str)
    assert "pr_route" in refusal
    assert "invalid timeout" in refusal


def test_node_timeout_argument_requires_a_named_positive_integer() -> None:
    """Malformed per-dispatch overrides refuse before a workflow is rendered."""
    for argument in ("", "fix", "fix=", "fix=0", "fix=true"):
        refusal = node_timeouts_with_arguments(
            timeouts=default_node_timeouts(), arguments=(argument,)
        )
        assert isinstance(refusal, str)
        assert "--node-timeout" in refusal
