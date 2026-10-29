"""This repository declares the `dod_gate` ACP turn timeout at 600 seconds."""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block
from livespec_orchestrator_beads_fabro.commands._dispatcher_graph_render import (
    node_timeout_seconds,
    render_workflow_graph,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import node_timeouts_from_block

_REPO_ROOT = Path(__file__).resolve().parents[1]
_GRAPH = (
    _REPO_ROOT
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "workflow.fabro"
)
_GATE = "dod_gate"
_DECLARED_SECONDS = 600


def test_the_committed_node_timeouts_declare_the_dod_gate_at_600_seconds() -> None:
    """`dispatcher.node_timeouts.dod_gate` is 600 in the committed `.livespec.jsonc`."""
    block = dispatcher_block(cwd=_REPO_ROOT)
    timeouts = node_timeouts_from_block(block=block)

    assert not isinstance(timeouts, str), timeouts
    assert timeouts.seconds_for(node=_GATE) == _DECLARED_SECONDS


def test_a_dispatch_renders_the_dod_gate_with_a_600_second_turn_timeout() -> None:
    """The rendered graph carries the declared figure as the gate's literal timeout."""
    timeouts = node_timeouts_from_block(block=dispatcher_block(cwd=_REPO_ROOT))
    assert not isinstance(timeouts, str), timeouts

    rendered = render_workflow_graph(
        committed_text=_GRAPH.read_text(encoding="utf-8"), timeouts=timeouts
    )

    assert not isinstance(rendered, str), rendered
    assert node_timeout_seconds(graph_text=rendered.text, node=_GATE) == _DECLARED_SECONDS
