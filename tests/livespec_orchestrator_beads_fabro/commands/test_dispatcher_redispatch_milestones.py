"""Milestones come from the committed graph's dependency order, never from stage names."""

from __future__ import annotations

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_redispatch_milestones as milestones,
)

_GRAPH = """digraph G {
  start [shape=Mdiamond]
  implement [shape=parallelogram]
  zeta [shape=parallelogram]
  alpha [shape=parallelogram]
  start -> implement
  implement -> zeta
  zeta -> alpha
  alpha -> implement
}
"""


def _workflow(*, tmp_path: Path, manifest: str | None, graph: str | None) -> None:
    directory = tmp_path / ".fabro" / "workflows" / "implement-work-item"
    directory.mkdir(parents=True)
    if manifest is not None:
        (directory / "workflow.toml").write_text(manifest, encoding="utf-8")
    if graph is not None:
        (directory / "workflow.fabro").write_text(graph, encoding="utf-8")


def _payload(*nodes: str) -> object:
    return [{"checkpoint": {"node_outcomes": {node: {"status": "succeeded"} for node in nodes}}}]


def test_rank_is_dependency_distance_not_name_order(tmp_path: Path) -> None:
    _workflow(tmp_path=tmp_path, manifest='[workflow]\ngraph = "workflow.fabro"\n', graph=_GRAPH)

    ranks = milestones.committed_node_ranks(repo=tmp_path)

    assert ranks == {"start": 0, "implement": 1, "zeta": 2, "alpha": 3}


@pytest.mark.parametrize(
    ("manifest", "graph"),
    [
        pytest.param(None, None, id="manifest-missing"),
        pytest.param('[workflow]\nname = "x"\n', None, id="no-graph-declared"),
        pytest.param('[workflow]\ngraph = "workflow.fabro"\n', None, id="graph-missing"),
        pytest.param('[workflow]\ngraph = "workflow.fabro"\n', "digraph G {}\n", id="no-entry"),
    ],
)
def test_unreadable_workflow_has_no_ranks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, manifest: str | None, graph: str | None
) -> None:
    _workflow(tmp_path=tmp_path, manifest=manifest, graph=graph)
    reserved = tmp_path / ".fabro" / "workflows" / "implement-work-item" / "workflow.toml"

    def _reserved(*, args: object) -> Path:
        _ = args
        return reserved

    monkeypatch.setattr(milestones, "workflow_toml", _reserved)

    assert milestones.committed_node_ranks(repo=tmp_path) is None


def test_furthest_succeeded_node_by_rank_is_the_milestone() -> None:
    ranks = {"start": 0, "implement": 1, "zeta": 2, "alpha": 3}

    reached = milestones.run_milestone(
        payload=_payload("setup", "start", "implement", "zeta"), ranks=ranks
    )

    assert reached == milestones.RunMilestone(
        name="zeta", order=2, workflow_identity="committed-graph"
    )


def test_undeclared_succeeded_nodes_change_the_workflow_identity() -> None:
    reached = milestones.run_milestone(
        payload=_payload("mystery", "implement"), ranks={"implement": 1}
    )

    assert reached is not None
    assert reached.workflow_identity == "undeclared:mystery"


def test_a_run_with_no_declared_success_has_the_no_milestone_rank() -> None:
    reached = milestones.run_milestone(payload=_payload("setup"), ranks={"implement": 1})

    assert reached == milestones.RunMilestone(
        name=milestones.NO_MILESTONE, order=-1, workflow_identity="committed-graph"
    )


def test_a_failed_node_is_not_a_milestone() -> None:
    payload = [{"checkpoint": {"node_outcomes": {"implement": {"status": "failed"}}}}]

    reached = milestones.run_milestone(payload=payload, ranks={"implement": 1})

    assert reached is not None
    assert reached.order == -1


def test_a_record_that_grades_nothing_has_no_milestone() -> None:
    assert milestones.run_milestone(payload=None, ranks={"implement": 1}) is None
    assert milestones.run_milestone(payload=[{"status": {"kind": "failed"}}], ranks={}) is None
