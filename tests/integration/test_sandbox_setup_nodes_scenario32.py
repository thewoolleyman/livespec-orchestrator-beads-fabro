"""The committed workflows run their sandbox setup as numbered command nodes (bd-ib-dpsiwz).

Binds the setup-node scenarios of `SPECIFICATION/scenarios.md` Scenario 32 and the
sandbox-setup bullet of `SPECIFICATION/constraints.md` section "Fabro runtime
constraints" (proposed in `SPECIFICATION/proposed_changes/
sandbox-setup-runs-as-explicit-command-nodes.md`). Upstream Fabro refuses
`run.prepare` from `v0.396.0-nightly.0`, so neither committed run configuration may
declare it, and the steps it carried are `run_prepare_<N>` command nodes between
`start` and the first stage.

The graph is read through the shared parser, never grepped, and the terminal node's
OWN script is executed by `sh` in a throwaway repository whose run branch carries
engine-shaped `fabro(<run>): <node> (<status>)` checkpoint commits, because the
step it names is read off that chain and a substring assertion cannot tell a script
that names the failed step from one that merely mentions it.

THE FAILURE ROUTE IS THE LOAD-BEARING HALF. A command node that exits non-zero
follows its unconditional edge and the run goes on to succeed (measured on candidate
run 01M6VWWEK8QP at bbe6938), so a chain with no failure route reads healthy while a
step failed. Each node is asserted to carry BOTH a conditional failed edge to the
terminal node and exactly ONE unconditional edge, because the engine rejects a node
whose every outgoing edge is conditional. The walk case then follows only the
failed outcome from every node and requires it to end at the terminal node without
ever entering the first stage.
"""

from __future__ import annotations

import re
import subprocess
from itertools import pairwise
from pathlib import Path

import pytest
import tomli
from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import (
    DotGraph,
    parse_dot_graph,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_setup_nodes import (
    SETUP_FAILURE_NODE,
    SETUP_FAILURE_SCRIPT,
    setup_node_names,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_IMPLEMENT = _REPO_ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item"
_GROOM = _REPO_ROOT / ".fabro" / "workflows" / "groom-work-item"
# Each committed workflow and the first stage its setup chain enters.
_WORKFLOWS = ((_IMPLEMENT, "dod_gate"), (_GROOM, "implement"))
_IDS = ("implement-work-item", "groom-work-item")
_DIRECTORIES = (_IMPLEMENT, _GROOM)
# The premise each implement-work-item setup node runs, in the order the steps ran
# as prepare steps. A reordered or dropped step moves a needle off its position.
_IMPLEMENT_ORDER = (
    "is-shallow-repository",
    "inputs.prepare_toolchain_mise",
    "inputs.prepare_toolchain_python_sync",
    "inputs.prepare_toolchain_lefthook",
    "livespec-implement-check-suite",
    "inputs.conformance_hook_install",
    "inputs.sandbox_exempt_marker",
    "inputs.conformance_verify_commit_refuse_hook",
    "inputs.conformance_verify_plugin_resolution",
)
_GROOM_ORDER = (
    "git fetch --unshallow",
    "inputs.prepare_toolchain_mise",
    "inputs.prepare_toolchain_python_sync",
    "inputs.prepare_toolchain_lefthook",
    "inputs.conformance_hook_install",
    "inputs.sandbox_exempt_marker",
    "inputs.conformance_verify_commit_refuse_hook",
    "inputs.conformance_verify_plugin_resolution",
)


def _graph(*, workflow: Path) -> DotGraph:
    parsed = parse_dot_graph(text=(workflow / "workflow.fabro").read_text(encoding="utf-8"))
    assert not isinstance(parsed, str), parsed
    return parsed


def _unconditional(*, graph: DotGraph, source: str) -> list[str]:
    return [
        edge.destination
        for edge in graph.edges
        if edge.source == source and "condition" not in edge.attributes
    ]


@pytest.mark.parametrize("workflow", _DIRECTORIES, ids=_IDS)
def test_no_committed_run_config_declares_a_prepare_table(workflow: Path) -> None:
    text = (workflow / "workflow.toml").read_text(encoding="utf-8")
    document = tomli.loads(text)
    assert "prepare" not in document.get("run", {})
    assert "[[run.prepare.steps]]" not in text
    assert "[[run.prepare.steps]]" not in (workflow / "workflow.fabro").read_text(encoding="utf-8")


@pytest.mark.parametrize(("workflow", "first"), _WORKFLOWS, ids=_IDS)
def test_the_setup_is_a_numbered_chain_between_start_and_the_first_stage(
    workflow: Path, first: str
) -> None:
    graph = _graph(workflow=workflow)
    chain = setup_node_names(graph=graph)
    assert chain == tuple(f"run_prepare_{index}" for index in range(1, len(chain) + 1))
    assert len(chain) >= 7
    assert _unconditional(graph=graph, source="start") == [chain[0]]
    for before, after in pairwise(chain):
        assert _unconditional(graph=graph, source=before) == [after]
    assert _unconditional(graph=graph, source=chain[-1]) == [first]
    assert [edge.source for edge in graph.edges if edge.destination == first][:1] == [chain[-1]]


@pytest.mark.parametrize("workflow", _DIRECTORIES, ids=_IDS)
def test_every_setup_node_is_a_command_node_with_a_script_and_a_timeout(workflow: Path) -> None:
    graph = _graph(workflow=workflow)
    for name in setup_node_names(graph=graph):
        attributes = graph.nodes[name]
        assert attributes["shape"] == "parallelogram"
        assert re.fullmatch(r"[0-9]+s", attributes["timeout"]), (name, attributes["timeout"])
        assert attributes["script"].strip()


def test_the_implement_setup_runs_the_steps_in_the_order_they_ran_as_prepare_steps() -> None:
    graph = _graph(workflow=_IMPLEMENT)
    scripts = [graph.nodes[name]["script"] for name in setup_node_names(graph=graph)]
    assert len(scripts) == len(_IMPLEMENT_ORDER)
    for script, needle in zip(scripts, _IMPLEMENT_ORDER, strict=True):
        assert needle in script, (needle, script)


def test_the_groom_setup_runs_the_steps_in_the_order_they_ran_as_prepare_steps() -> None:
    graph = _graph(workflow=_GROOM)
    scripts = [graph.nodes[name]["script"] for name in setup_node_names(graph=graph)]
    assert len(scripts) == len(_GROOM_ORDER)
    for script, needle in zip(scripts, _GROOM_ORDER, strict=True):
        assert needle in script, (needle, script)


@pytest.mark.parametrize("workflow", _DIRECTORIES, ids=_IDS)
def test_every_setup_node_routes_a_failure_to_the_terminal_node_beside_one_fallthrough(
    workflow: Path,
) -> None:
    graph = _graph(workflow=workflow)
    for name in setup_node_names(graph=graph):
        failed = [
            edge.destination
            for edge in graph.edges
            if edge.source == name and edge.attributes.get("condition") == "outcome=failed"
        ]
        assert failed == [SETUP_FAILURE_NODE], name
        assert len(_unconditional(graph=graph, source=name)) == 1, name
    assert not [edge for edge in graph.edges if edge.source == SETUP_FAILURE_NODE]
    assert graph.nodes[SETUP_FAILURE_NODE]["script"] == SETUP_FAILURE_SCRIPT


@pytest.mark.parametrize(("workflow", "first"), _WORKFLOWS, ids=_IDS)
def test_a_failed_outcome_at_any_setup_node_ends_the_run_before_the_first_stage(
    workflow: Path, first: str
) -> None:
    graph = _graph(workflow=workflow)
    chain = setup_node_names(graph=graph)

    def _next(*, node: str, outcome: str) -> str:
        conditional = [
            edge.destination
            for edge in graph.edges
            if edge.source == node and edge.attributes.get("condition") == f"outcome={outcome}"
        ]
        return conditional[0] if conditional else _unconditional(graph=graph, source=node)[0]

    for failing in chain:
        position, visited = failing, []
        while position != SETUP_FAILURE_NODE:
            visited.append(position)
            position = _next(node=position, outcome="failed")
        assert visited == [failing]
        assert first not in visited
    # The control: with every step succeeding the same selection walks the whole chain
    # and enters the first stage, so the failure arm is not simply the only way out.
    walked, position = [], "start"
    while position != first:
        walked.append(position)
        position = _next(node=position, outcome="succeeded")
    assert walked == ["start", *chain]


def _git(cwd: Path, *argv: str) -> None:
    _ = subprocess.run(["git", *argv], cwd=str(cwd), check=True, text=True, capture_output=True)


def _repository(*, tmp_path: Path, checkpoints: tuple[str, ...]) -> Path:
    work = tmp_path / "work"
    work.mkdir()
    _git(work, "init", "-b", "master")
    _git(work, "config", "user.name", "setup-nodes-test")
    _git(work, "config", "user.email", "setup-nodes-test@example.invalid")
    (work / "base.txt").write_text("base\n", encoding="utf-8")
    _git(work, "add", "base.txt")
    _git(work, "commit", "-m", "base")
    for subject in checkpoints:
        _git(work, "commit", "--allow-empty", "-m", subject)
    return work


def _run_terminal(*, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/sh", "-c", SETUP_FAILURE_SCRIPT],
        cwd=str(cwd),
        check=False,
        text=True,
        capture_output=True,
    )


def test_the_terminal_node_names_the_step_the_newest_checkpoint_recorded(tmp_path: Path) -> None:
    work = _repository(
        tmp_path=tmp_path,
        checkpoints=(
            "fabro(01RUN): run_prepare_6 (success)",
            "fabro(01RUN): run_prepare_7 (failure)",
        ),
    )
    result = _run_terminal(cwd=work)
    assert result.returncode == 1
    assert "LIVESPEC_SETUP_STEP_FAILED: run_prepare_7 failed" in result.stderr
    assert "run_prepare_6" not in result.stderr


def test_the_terminal_node_still_ends_the_run_when_no_checkpoint_names_a_step(
    tmp_path: Path,
) -> None:
    work = _repository(tmp_path=tmp_path, checkpoints=())
    result = _run_terminal(cwd=work)
    assert result.returncode == 1
    assert (
        "LIVESPEC_SETUP_STEP_FAILED: an unidentified run_prepare_<N> step failed" in result.stderr
    )


def test_the_terminal_node_ends_the_run_outside_a_repository(tmp_path: Path) -> None:
    result = _run_terminal(cwd=tmp_path)
    assert result.returncode == 1
    assert "an unidentified run_prepare_<N> step" in result.stderr
