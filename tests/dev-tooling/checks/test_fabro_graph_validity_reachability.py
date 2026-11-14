"""The factory-graph gate's reachability leg: every node is reachable from the start node.

The orchestrator's v0.329.0 release shipped an `implement-work-item` graph in
which `implement_hook_route` and `implement_commit_settle` had no incoming edge,
after the red/green split rewired their old entries and left both nodes in
place. `fabro run` refused every dispatch with `attractor.unreachable_node`,
and the release CI was green, because nothing in the check suite asked the
engine's reachability rule of the shipped graph.

The leg lives in the sibling private helper `_fabro_graph_reachability`, which
`fabro_graph_validity` calls from `report`. It needs no engine binary, so it
runs inside a Fabro sandbox too, where `fabro validate` is structurally absent.
The cases below drive it over seeded graphs, over the repository's own shipped
graphs, and through the gate's `report`.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECKS = _REPO_ROOT / "dev-tooling" / "checks"
_HELPER_PATH = _CHECKS / "_fabro_graph_reachability.py"
_GATE_PATH = _CHECKS / "fabro_graph_validity.py"
_WORKFLOWS = (".claude-plugin", ".fabro", "workflows")

_ORPHAN_GRAPH = """digraph Probe {
    start [shape=Mdiamond]
    exit  [shape=Msquare]
    work
    orphan
    start -> work
    work -> exit
    orphan -> work
}
"""

_CHAINED_ORPHANS_GRAPH = """digraph Probe {
    start [shape=Mdiamond]
    exit  [shape=Msquare]
    work
    first_orphan
    second_orphan
    start -> work -> exit
    first_orphan -> second_orphan -> work
}
"""

_REACHABLE_GRAPH = """digraph Probe {
    start [shape=Mdiamond]
    exit  [shape=Msquare]
    work
    retry
    start -> work
    work -> retry [condition="outcome=failed"]
    work -> exit
    retry -> work
}
"""

_NO_START_GRAPH = """digraph Probe {
    work
    work -> exit
}
"""


def _load_helper() -> ModuleType:
    assert _HELPER_PATH.is_file(), f"the reachability helper is missing at {_HELPER_PATH}"
    spec = importlib.util.spec_from_file_location("_fabro_graph_reachability", _HELPER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_gate() -> ModuleType:
    assert _HELPER_PATH.is_file(), f"the reachability helper is missing at {_HELPER_PATH}"
    spec = importlib.util.spec_from_file_location("fabro_graph_validity", _GATE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _seed(*, root: Path, directory: str, name: str, graph: str) -> Path:
    target = root.joinpath(*_WORKFLOWS, directory)
    target.mkdir(parents=True, exist_ok=True)
    path = target / name
    _ = path.write_text(graph, encoding="utf-8")
    return path


def test_an_orphan_node_is_a_finding_that_names_it(tmp_path: Path) -> None:
    helper = _load_helper()
    _ = _seed(root=tmp_path, directory="probe", name="workflow.fabro", graph=_ORPHAN_GRAPH)

    findings = helper.unreachable_node_findings(repo_root=tmp_path)

    assert len(findings) == 1
    assert "orphan" in findings[0]
    assert "probe/workflow.fabro" in findings[0]
    assert "start" in findings[0]


def test_every_unreachable_node_is_named_including_a_chain_of_them(tmp_path: Path) -> None:
    helper = _load_helper()
    _ = _seed(root=tmp_path, directory="probe", name="workflow.fabro", graph=_CHAINED_ORPHANS_GRAPH)

    findings = helper.unreachable_node_findings(repo_root=tmp_path)

    assert len(findings) == 2
    assert any("first_orphan" in finding for finding in findings)
    assert any("second_orphan" in finding for finding in findings)


def test_a_graph_whose_nodes_are_all_reachable_reports_nothing(tmp_path: Path) -> None:
    helper = _load_helper()
    _ = _seed(root=tmp_path, directory="probe", name="workflow.fabro", graph=_REACHABLE_GRAPH)

    assert helper.unreachable_node_findings(repo_root=tmp_path) == []


def test_every_shipped_graph_file_is_read_not_only_the_one_named_workflow_fabro(
    tmp_path: Path,
) -> None:
    helper = _load_helper()
    _ = _seed(root=tmp_path, directory="probe", name="workflow.fabro", graph=_REACHABLE_GRAPH)
    _ = _seed(root=tmp_path, directory="probe", name="workflow.variant.fabro", graph=_ORPHAN_GRAPH)
    _ = _seed(root=tmp_path, directory="other", name="workflow.fabro", graph=_ORPHAN_GRAPH)

    findings = helper.unreachable_node_findings(repo_root=tmp_path)

    assert len(findings) == 2
    assert any("probe/workflow.variant.fabro" in finding for finding in findings)
    assert any("other/workflow.fabro" in finding for finding in findings)


def test_a_graph_with_no_start_node_is_a_finding_not_a_silent_pass(tmp_path: Path) -> None:
    helper = _load_helper()
    _ = _seed(root=tmp_path, directory="probe", name="workflow.fabro", graph=_NO_START_GRAPH)

    findings = helper.unreachable_node_findings(repo_root=tmp_path)

    assert len(findings) == 1
    assert "no start node" in findings[0]


def test_a_graph_the_parser_refuses_is_a_finding_not_a_silent_pass(tmp_path: Path) -> None:
    helper = _load_helper()
    _ = _seed(root=tmp_path, directory="probe", name="workflow.fabro", graph="not a graph")

    findings = helper.unreachable_node_findings(repo_root=tmp_path)

    assert len(findings) == 1
    assert "probe/workflow.fabro" in findings[0]


def test_a_repository_that_ships_no_graph_reports_nothing(tmp_path: Path) -> None:
    helper = _load_helper()

    assert helper.unreachable_node_findings(repo_root=tmp_path) == []


def test_this_repositorys_shipped_graphs_have_no_unreachable_node() -> None:
    helper = _load_helper()

    assert helper.unreachable_node_findings(repo_root=_REPO_ROOT) == []


def test_the_gate_reports_an_orphan_node_as_a_graph_finding(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gate = _load_gate()
    root = tmp_path / "repo"
    directory = _seed(
        root=root, directory="implement-work-item", name="workflow.fabro", graph=_ORPHAN_GRAPH
    ).parent
    _ = (directory / "workflow.toml").write_text("[run]\n", encoding="utf-8")
    monkeypatch.setenv("LIVESPEC_FABRO_BIN", str(tmp_path / "absent" / "fabro"))
    monkeypatch.delenv("LIVESPEC_FABRO_GRAPH_VALIDATION", raising=False)

    found = gate.report(repo_root=root)

    assert len(found.findings) == 1
    assert "orphan" in found.findings[0]
