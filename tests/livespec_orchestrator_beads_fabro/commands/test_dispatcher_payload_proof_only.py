"""The payload materialization seam ships the proof-only arm when asked for it."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_materialize import (
    MaterializationRefusal,
    materialize_dispatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_payload import (
    WorkflowPayload,
    materialize_workflow_payload,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import default_node_timeouts

_REPO_ROOT = Path(__file__).resolve().parents[3]
_GIT_AUTHOR = {"operator_name": "Operator", "operator_email": "operator@example.com"}
_COMMITTED_WORKFLOW_TOML = '_version = 1\n\n[workflow]\ngraph = "workflow.fabro"\n\n[run.environment]\nid = "livespec-ci"\n'
_NO_PROOF_STAGES_GRAPH = (
    'digraph G {\n    graph [stall_timeout="7200s"]\n    start\n    exit\n    start -> exit\n}\n'
)
_FULL_GRAPH = """digraph ImplementWorkItem {
    graph [stall_timeout="7200s"]
    start [shape=Mdiamond]
    exit [shape=Msquare]
    implement [timeout="14400s"]
    proof_capture [timeout="14400s"]
    proof_verify [timeout="14400s"]
    proof_grade [timeout="14400s"]
    review [timeout="14400s"]

    start -> implement
    implement -> proof_capture
    proof_capture -> proof_verify
    proof_capture -> review [label="fix"]
    proof_verify -> proof_grade
    proof_verify -> implement [label="fix"]
    proof_grade -> review
    review -> exit
}
"""


class _NullJournal:
    def append(self, *, record: dict[str, object]) -> None:
        _ = record


def _committed(*, root: Path, graph_text: str) -> Path:
    workflow_dir = root / "workflow"
    workflow_dir.mkdir(parents=True)
    _ = (workflow_dir / "workflow.fabro").write_text(graph_text, encoding="utf-8")
    committed = workflow_dir / "workflow.toml"
    _ = committed.write_text(_COMMITTED_WORKFLOW_TOML, encoding="utf-8")
    return committed


def _materialized(*, root: Path, graph_text: str, proof_only: bool) -> WorkflowPayload | str:
    return materialize_workflow_payload(
        committed=_committed(root=root, graph_text=graph_text),
        payload_dir=root / "payload",
        timeouts=default_node_timeouts(),
        adapters={},
        proof_only=proof_only,
    )


def test_proof_only_materialization_ships_the_three_proof_stages_and_nothing_else(
    tmp_path: Path,
) -> None:
    """Scenario 257: the shipped graph visits capture, verify and grade, then ends."""
    payload = _materialized(root=tmp_path, graph_text=_FULL_GRAPH, proof_only=True)
    assert isinstance(payload, WorkflowPayload)
    graph = parse_dot_graph(text=payload.graph.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    assert set(graph.nodes) == {"start", "exit", "proof_capture", "proof_verify", "proof_grade"}
    assert [
        (edge.source, edge.destination, edge.attributes.get("condition")) for edge in graph.edges
    ] == [
        ("start", "proof_capture", None),
        ("proof_capture", "exit", "outcome=failed"),
        ("proof_capture", "exit", "preferred_label=fix"),
        ("proof_capture", "proof_verify", None),
        ("proof_verify", "proof_grade", "preferred_label=approve"),
        ("proof_verify", "exit", None),
        ("proof_grade", "exit", None),
    ]


def test_an_ordinary_materialization_keeps_every_stage(tmp_path: Path) -> None:
    """The control: without the selector the whole workflow still ships."""
    payload = _materialized(root=tmp_path, graph_text=_FULL_GRAPH, proof_only=False)
    assert isinstance(payload, WorkflowPayload)
    graph = parse_dot_graph(text=payload.graph.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    assert {"implement", "review"} <= set(graph.nodes)


def test_proof_only_materialization_refuses_a_graph_without_the_proof_stages(
    tmp_path: Path,
) -> None:
    """A graph the arm cannot be derived from is refused before any run exists."""
    refusal = _materialized(root=tmp_path, graph_text=_NO_PROOF_STAGES_GRAPH, proof_only=True)
    assert isinstance(refusal, str)
    assert "proof-only" in refusal


def test_the_dispatch_materializer_reads_the_selector_off_the_invocation(
    tmp_path: Path,
) -> None:
    """The shipped workflow, materialized for a proof-only invocation, is the arm."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps({"git_author": _GIT_AUTHOR}), encoding="utf-8"
    )
    materialized = materialize_dispatch(
        args=argparse.Namespace(workflow=None, repo=str(repo), resume_proof_only=True),
        repo=repo,
        work_item_id="bd-ib-ixmxqy",
        journal=_NullJournal(),
    )
    assert not isinstance(materialized, MaterializationRefusal), materialized
    graph = parse_dot_graph(text=materialized.payload.graph.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    assert set(graph.nodes) == {"start", "exit", "proof_capture", "proof_verify", "proof_grade"}
