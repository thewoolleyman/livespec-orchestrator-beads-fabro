"""This repository declares the `dod_gate` ACP turn timeout at 600 seconds."""

from __future__ import annotations

import json
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


def _fixture_dispatcher_config(*, tmp_path: Path) -> Path:
    _ = (tmp_path / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "dispatcher": {"node_timeouts": {_GATE: _DECLARED_SECONDS}}
                }
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


def test_a_fixture_node_timeout_declares_the_dod_gate_at_600_seconds(tmp_path: Path) -> None:
    """A test-owned dispatcher fixture resolves the gate's 600-second timeout."""
    block = dispatcher_block(cwd=_fixture_dispatcher_config(tmp_path=tmp_path))
    timeouts = node_timeouts_from_block(block=block)

    assert not isinstance(timeouts, str), timeouts
    assert timeouts.seconds_for(node=_GATE) == _DECLARED_SECONDS


def test_a_dispatch_renders_the_fixture_dod_gate_timeout(tmp_path: Path) -> None:
    """The rendered graph carries the fixture's literal gate timeout."""
    timeouts = node_timeouts_from_block(
        block=dispatcher_block(cwd=_fixture_dispatcher_config(tmp_path=tmp_path))
    )
    assert not isinstance(timeouts, str), timeouts

    rendered = render_workflow_graph(
        committed_text=_GRAPH.read_text(encoding="utf-8"), timeouts=timeouts
    )

    assert not isinstance(rendered, str), rendered
    assert node_timeout_seconds(graph_text=rendered.text, node=_GATE) == _DECLARED_SECONDS
