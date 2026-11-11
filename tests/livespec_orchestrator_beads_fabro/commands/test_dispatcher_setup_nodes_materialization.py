"""A dispatch carries its setup as command nodes, not as `run.prepare` (bd-ib-dpsiwz).

Upstream Fabro refuses `run.prepare` from `v0.396.0-nightly.0`, so the overlay a
dispatch writes may carry no `[[run.prepare.steps]]` at all: every step the
Dispatcher materializes has to arrive as a `run_prepare_<N>` command node of the
per-dispatch graph, after `start` and before whatever the run enters first, in the
order the steps ran under `run.prepare`. These cases drive `materialize_overlay`,
because that is the function that writes both artifacts and the only surface on
which a step lost between the overlay and the graph is observable.
"""

from __future__ import annotations

import inspect
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest
import tomli
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_credentials,
    _dispatcher_sibling_clones,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credentials import (
    materialize_overlay,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import (
    DotGraph,
    parse_dot_graph,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_git_author import GitAuthor
from livespec_orchestrator_beads_fabro.commands._node_timeouts import (
    WORKFLOW_DEFAULT_LAYER,
    NodeTimeouts,
)

_GIT_AUTHOR = GitAuthor(name="Operator", email="operator@example.com")
_DISPATCH_ID = "01M72SETUPNODES0000000000A"
_FAKE_TOKEN = "setup-nodes-oauth-placeholder"
_FAKE_GITHUB_TOKEN = "setup-nodes-github-placeholder"
_FLEET_MANIFEST_TEXT = json.dumps({"owner": "thewoolleyman", "fleet": [{"repo": "livespec"}]})
_COMMITTED_TOML = '[workflow]\ngraph = "workflow.fabro"\n\n[run.environment]\nid = "livespec-ci"\n'
_LEGACY_STEP = '\n[[run.prepare.steps]]\nscript = "echo committed-step"\n'
_GRAPH = """digraph ImplementWorkItem {
    graph [stall_timeout="7200s"]
    start [shape=Mdiamond, label="Start"]
    exit [shape=Msquare, label="Exit"]
    dod_gate [label="gate", timeout="1800s", script="echo gate"]
    publish_draft [label="publish", timeout="3600s", script="echo publish"]
    start -> dod_gate
    dod_gate -> exit
}
"""
_COMMITTED_CHAIN_GRAPH = """digraph ImplementWorkItem {
    graph [stall_timeout="7200s"]
    start [shape=Mdiamond, label="Start"]
    exit [shape=Msquare, label="Exit"]
    run_prepare_1 [label="a", shape=parallelogram, timeout="1800s", script="echo one"]
    run_prepare_2 [label="b", shape=parallelogram, timeout="1800s", script="echo two"]
    setup_failed [label="f", shape=parallelogram, timeout="600s", script="exit 1"]
    dod_gate [label="gate", timeout="1800s", script="echo gate"]
    start -> run_prepare_1
    run_prepare_1 -> run_prepare_2
    run_prepare_2 -> dod_gate
    run_prepare_1 -> setup_failed [label="x", condition="outcome=failed"]
    run_prepare_2 -> setup_failed [label="x", condition="outcome=failed"]
    dod_gate -> exit
}
"""


def _materialize(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    graph_text: str,
    committed_toml: str = _COMMITTED_TOML,
    node_timeouts: NodeTimeouts | None = None,
    pass_graph: bool = True,
) -> tuple[str | None, str, str]:
    """Materialize one dispatch; return the refusal (if any), the overlay and the graph."""
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"dispatcher": {}}}), encoding="utf-8"
    )
    committed_dir = tmp_path / "ImplementWorkItem"
    committed_dir.mkdir(parents=True, exist_ok=True)
    committed = committed_dir / "workflow.toml"
    _ = committed.write_text(committed_toml, encoding="utf-8")
    _ = (committed_dir / "workflow.fabro").write_text(_GRAPH, encoding="utf-8")
    package_dir = tmp_path / f"fabro-workflow-{_DISPATCH_ID}"
    package_dir.mkdir(parents=True, exist_ok=True)
    rendered_graph = package_dir / "workflow.fabro"
    _ = rendered_graph.write_text(graph_text, encoding="utf-8")
    overlay = tmp_path / f"fabro-run-config-{_DISPATCH_ID}.toml"
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", _FAKE_TOKEN)
    monkeypatch.setattr(
        _dispatcher_sibling_clones, "fetch_fleet_manifest_text", lambda: _FLEET_MANIFEST_TEXT
    )
    monkeypatch.setattr(_dispatcher_credentials.time, "time", lambda: 1_700_000_000)
    extra: dict[str, object] = {} if node_timeouts is None else {"node_timeouts": node_timeouts}
    materialize = cast("Callable[..., str | None]", materialize_overlay)
    error = materialize(
        committed=committed,
        overlay=overlay,
        repo=repo,
        work_item_id="bd-ib-dpsiwz",
        dispatch_id=_DISPATCH_ID,
        token=lambda: _FAKE_GITHUB_TOKEN,
        git_author=_GIT_AUTHOR,
        review_fix_visit_cap=4,
        graph_override=rendered_graph if pass_graph else None,
        fabro_version="fabro 0.255.0 (deadbee 2026-10-10)",
        **extra,
    )
    written = overlay.read_text(encoding="utf-8") if overlay.exists() else ""
    return error, written, rendered_graph.read_text(encoding="utf-8")


def _graph(*, text: str) -> DotGraph:
    graph = parse_dot_graph(text=text)
    assert not isinstance(graph, str), graph
    return graph


def _chain(*, graph: DotGraph, entry: str) -> list[str]:
    """The nodes the unconditional edges lead through from `start` to `entry`."""
    nodes: list[str] = []
    here = "start"
    while here != entry:
        (here,) = [
            edge.destination
            for edge in graph.edges
            if edge.source == here and "condition" not in edge.attributes
        ]
        nodes.append(here)
    return nodes[:-1]


def test_the_written_config_carries_no_run_prepare_at_all(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    error, written, _ = _materialize(tmp_path=tmp_path, monkeypatch=monkeypatch, graph_text=_GRAPH)
    assert error is None
    assert "prepare" not in tomli.loads(written).get("run", {})
    assert "[[run.prepare.steps]]" not in written


def test_every_materialized_step_is_a_numbered_node_between_start_and_the_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    error, _, graph_text = _materialize(
        tmp_path=tmp_path, monkeypatch=monkeypatch, graph_text=_GRAPH
    )
    assert error is None
    graph = _graph(text=graph_text)
    chain = _chain(graph=graph, entry="dod_gate")
    assert len(chain) >= 10
    assert chain == [f"run_prepare_{index}" for index in range(1, len(chain) + 1)]
    for name in chain:
        assert graph.nodes[name]["shape"] == "parallelogram"
        assert any(
            edge.source == name
            and edge.destination == "setup_failed"
            and edge.attributes.get("condition") == "outcome=failed"
            for edge in graph.edges
        ), f"{name} has no failure route"


def test_the_dispatch_marker_step_is_one_of_the_nodes_with_its_dispatch_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, graph_text = _materialize(tmp_path=tmp_path, monkeypatch=monkeypatch, graph_text=_GRAPH)
    graph = _graph(text=graph_text)
    marked = [
        name
        for name, attributes in graph.nodes.items()
        if "livespec.factoryRunId" in attributes.get("script", "")
    ]
    assert len(marked) == 1
    assert _DISPATCH_ID in graph.nodes[marked[0]]["script"]


def test_a_payload_step_keeps_its_bytes_in_the_run_env_table_and_not_in_its_script(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The engine's compact fidelity re-sends every setup script and no environment.

    A step that carries a helper program therefore keeps the program in the run's
    environment table, under a name unique to its step, and leaves only the short
    command that writes it in the node's script. The node carries no environment of
    its own: a graph attribute for one is not something the engine is known to read.
    """
    _, written, graph_text = _materialize(
        tmp_path=tmp_path, monkeypatch=monkeypatch, graph_text=_GRAPH
    )
    graph = _graph(text=graph_text)
    env = tomli.loads(written)["environments"]["livespec-ci"]["env"]
    payloads = {
        name: attributes
        for name, attributes in graph.nodes.items()
        if "PREPARE_PAYLOAD" in attributes.get("script", "")
    }
    assert payloads
    for attributes in payloads.values():
        named = set(
            re.findall(r"LIVESPEC_SETUP_\d+__LIVESPEC_PREPARE_PAYLOAD\w*", attributes["script"])
        )
        assert named
        assert named <= set(env)
        assert "env" not in attributes
        assert not re.search(r"[A-Za-z0-9+/=]{200,}", attributes["script"])
    assert len({key for key in env if "PREPARE_PAYLOAD" in key}) >= len(payloads)


def test_the_chain_continues_after_the_nodes_the_committed_graph_already_declares(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    error, _, graph_text = _materialize(
        tmp_path=tmp_path, monkeypatch=monkeypatch, graph_text=_COMMITTED_CHAIN_GRAPH
    )
    assert error is None
    graph = _graph(text=graph_text)
    chain = _chain(graph=graph, entry="dod_gate")
    assert chain[:2] == ["run_prepare_1", "run_prepare_2"]
    assert chain[2] == "run_prepare_3"
    assert graph.nodes["run_prepare_1"]["script"] == "echo one"
    assert "livespec.factoryRunId" not in graph.nodes["run_prepare_2"]["script"]


def test_a_committed_step_still_in_the_run_config_comes_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, written, graph_text = _materialize(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        graph_text=_GRAPH,
        committed_toml=_COMMITTED_TOML + _LEGACY_STEP,
    )
    assert "committed-step" not in written
    assert _graph(text=graph_text).nodes["run_prepare_1"]["script"] == "echo committed-step"


def test_a_resolved_node_timeout_for_a_setup_node_reaches_the_node(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert "node_timeouts" in inspect.signature(materialize_overlay).parameters
    timeouts = NodeTimeouts(
        configured={"run_prepare_2": 123},
        stall_seconds=7200,
        stall_layer=WORKFLOW_DEFAULT_LAYER,
    )
    _, _, graph_text = _materialize(
        tmp_path=tmp_path, monkeypatch=monkeypatch, graph_text=_GRAPH, node_timeouts=timeouts
    )
    graph = _graph(text=graph_text)
    assert graph.nodes["run_prepare_2"]["timeout"] == "123s"
    assert graph.nodes["run_prepare_1"]["timeout"] == "1800s"


def test_a_graph_with_no_start_edge_to_hang_the_chain_on_refuses_the_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph_text = _GRAPH.replace("    start -> dod_gate\n", "")
    error, _, _ = _materialize(tmp_path=tmp_path, monkeypatch=monkeypatch, graph_text=graph_text)
    assert error is not None
    assert "setup" in error
    assert "run_prepare" in error


def test_a_dispatch_with_no_per_dispatch_graph_keeps_its_steps_in_the_run_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    error, written, graph_text = _materialize(
        tmp_path=tmp_path, monkeypatch=monkeypatch, graph_text=_GRAPH, pass_graph=False
    )
    assert error is None
    assert "[[run.prepare.steps]]" in written
    assert graph_text == _GRAPH
