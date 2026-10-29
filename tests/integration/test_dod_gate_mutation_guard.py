"""A `dod_gate` turn that mutates the sandbox ends the run at needs-human.

Work-item `bd-ib-al54tl`. Run 01M5SWSTWJZBAG194Q8NHS2RGB (work-item
`bd-ib-nz4av6`, petri, 2026-10-25) spent two 30-minute `dod_gate` turns
IMPLEMENTING the item it was meant to grade: it edited files, ran the check suite
and started a commit, and the run reached needs-human only after both turns hit
their ceiling. Seven other `dod_gate` turns in the same window took 0.7 to 1.6
minutes each.

The node's agent is not mechanically prevented from doing implement work, so the
run enforces the role afterwards: a scripted `dod_gate_mutation_guard` node sits
on `dod_gate`'s fallthrough and compares the sandbox with the state the node
started on. The starting state is read off the run's own checkpoint chain -- the
engine commits one `fabro(<run>): <node> (<status>)` checkpoint per stage, so the
newest checkpoint that is not a `dod_gate` one is the commit the node started on.

THE PROMPT HALF is bound here too, because a refusal the grader was never told to
expect reads as a broken sandbox rather than as the rule it is.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

_PAYLOAD = Path(".claude-plugin/.fabro/workflows/implement-work-item")
_WORKFLOW = _PAYLOAD / "workflow.fabro"
_PROMPT = _PAYLOAD / "prompts" / "dod-gate.md"
_GUARD = "dod_gate_mutation_guard"
_MUTATION_MARKER = "LIVESPEC_DOD_GATE_MUTATION"
_UNPROVABLE_MARKER = "LIVESPEC_DOD_GATE_MUTATION_UNPROVABLE"
_SCRIPT = re.compile(r'script="(?P<value>(?:[^"\\]|\\.)*)"')
_EDGE = re.compile(
    r"(?m)^[ \t]*(?P<src>[A-Za-z_]\w*)[ \t]*->[ \t]*(?P<dst>[A-Za-z_]\w*)(?P<attrs>.*)$"
)


def _graph() -> str:
    return _WORKFLOW.read_text(encoding="utf-8")


def _edges_from(*, source: str) -> dict[str, str]:
    return {
        edge.group("dst"): edge.group("attrs")
        for edge in _EDGE.finditer(_graph())
        if edge.group("src") == source
    }


def _guard_script() -> str:
    block = re.search(
        rf"^\s*{_GUARD}\s*\[(?P<body>.*?)^\s*\]",
        _graph(),
        re.DOTALL | re.MULTILINE,
    )
    assert block is not None, f"the graph declares no {_GUARD} node"
    attribute = _SCRIPT.search(block.group("body"))
    assert attribute is not None, f"{_GUARD} carries no script attribute"
    return re.sub(r"\\(?P<escaped>.)", r"\g<escaped>", attribute.group("value")).replace(
        "{{ inputs.default_branch }}", "master"
    )


def _git(cwd: Path, *argv: str) -> str:
    return subprocess.run(
        ["git", *argv], cwd=str(cwd), check=True, text=True, capture_output=True
    ).stdout


def _checkpoint(*, cwd: Path, node: str) -> None:
    _git(cwd, "add", "-A")
    _git(cwd, "commit", "--allow-empty", "-m", f"fabro(01RUN): {node} (success)")


def _sandbox(*, tmp_path: Path, prepared: bool = True) -> Path:
    work = tmp_path / "work"
    work.mkdir()
    _git(work, "init", "-b", "master")
    _git(work, "config", "user.name", "dod-gate-guard-test")
    _git(work, "config", "user.email", "dod-gate-guard-test@example.invalid")
    (work / "base.txt").write_text("base\n", encoding="utf-8")
    _git(work, "add", "base.txt")
    _git(work, "commit", "-m", "base")
    _git(work, "update-ref", "refs/remotes/origin/master", "HEAD")
    _git(work, "switch", "-c", "fabro/run/01RUN")
    if prepared:
        _checkpoint(cwd=work, node="run_prepare_1")
        _checkpoint(cwd=work, node="run_prepare_2")
    return work


def _run_guard(*, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/sh", "-c", _guard_script()],
        cwd=str(cwd),
        check=False,
        text=True,
        capture_output=True,
    )


def _reason(*, cwd: Path) -> str:
    path = Path(_git(cwd, "rev-parse", "--git-path", "livespec-needs-human-reason").strip())
    return (cwd / path).read_text(encoding="utf-8")


def test_a_grading_turn_that_changes_nothing_passes_the_guard(tmp_path: Path) -> None:
    work = _sandbox(tmp_path=tmp_path)
    _checkpoint(cwd=work, node="dod_gate")
    result = _run_guard(cwd=work)
    assert result.returncode == 0, result.stderr


def test_an_edited_file_fails_the_guard_and_the_reason_names_it(tmp_path: Path) -> None:
    work = _sandbox(tmp_path=tmp_path)
    (work / "base.txt").write_text("edited by the grader\n", encoding="utf-8")
    _checkpoint(cwd=work, node="dod_gate")
    result = _run_guard(cwd=work)
    assert result.returncode == 1
    assert _MUTATION_MARKER in result.stderr
    assert "base.txt" in result.stderr
    assert "base.txt" in _reason(cwd=work)
    assert "dod_gate" in _reason(cwd=work)


def test_a_new_file_in_the_working_tree_fails_the_guard(tmp_path: Path) -> None:
    work = _sandbox(tmp_path=tmp_path)
    _checkpoint(cwd=work, node="dod_gate")
    (work / "scratch.txt").write_text("left behind\n", encoding="utf-8")
    result = _run_guard(cwd=work)
    assert result.returncode == 1
    assert _MUTATION_MARKER in result.stderr
    assert "scratch.txt" in result.stderr


def test_a_commit_made_during_the_turn_fails_the_guard_even_when_it_is_empty(
    tmp_path: Path,
) -> None:
    work = _sandbox(tmp_path=tmp_path)
    _git(work, "commit", "--allow-empty", "-m", "feat: the grader implemented the item")
    _checkpoint(cwd=work, node="dod_gate")
    result = _run_guard(cwd=work)
    assert result.returncode == 1
    assert _MUTATION_MARKER in result.stderr
    assert "the grader implemented the item" in result.stderr
    assert "commit" in _reason(cwd=work)


def test_a_run_with_no_checkpoint_before_the_node_fails_closed_naming_why(
    tmp_path: Path,
) -> None:
    work = _sandbox(tmp_path=tmp_path, prepared=False)
    _checkpoint(cwd=work, node="dod_gate")
    result = _run_guard(cwd=work)
    assert result.returncode == 1
    assert _UNPROVABLE_MARKER in result.stderr


def test_the_graph_routes_dod_gate_through_the_guard_before_implement() -> None:
    edges = _edges_from(source="dod_gate")
    assert set(edges) == {"needs_human", _GUARD}, edges
    assert "condition" not in edges[_GUARD]
    assert 'condition="outcome=failed"' in edges["needs_human"]
    guard_edges = _edges_from(source=_GUARD)
    assert set(guard_edges) == {"needs_human", "implement"}, guard_edges
    assert 'condition="outcome=failed"' in guard_edges["needs_human"]
    assert "condition" not in guard_edges["implement"]


def _prompt() -> str:
    return " ".join(_PROMPT.read_text(encoding="utf-8").split())


@pytest.mark.parametrize(
    "needle",
    [
        "grade the Definition of Done only",
        "must not edit files",
        "run the check suite",
        "must not commit",
        "working tree and HEAD",
        "dod_gate_mutation_guard",
    ],
)
def test_the_prompt_tells_the_agent_it_grades_only_and_may_not_mutate(needle: str) -> None:
    assert needle in _prompt(), needle
