"""A run whose working diff reaches the workflows directory ends at its implement stage.

Work-item `bd-ib-tgygh6`. The pre-dispatch screen cannot see every item that
edits a workflow, so the implement stage backstops it: a scripted
`implement_workflow_guard` node sits on `implement_completion`'s complete edge,
reads the run's working diff against the default branch, and ends the run at
needs-human with a host-route verdict that names EVERY file under
`.github/workflows/` instead of letting the run continue to publication.

The node's own script is extracted from the committed graph, unescaped and run
by `sh` in a throwaway repository, so the arms that matter (committed file,
uncommitted edit, untracked file, deletion, unresolvable base) execute rather
than being matched as text.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

_PAYLOAD = Path(".claude-plugin/.fabro/workflows/implement-work-item")
_WORKFLOW = _PAYLOAD / "workflow.fabro"
_GUARD = "implement_workflow_guard"
_VERDICT_MARKER = "LIVESPEC_IMPLEMENT_WORKFLOW_EDIT_HOST_ROUTE"
_UNPROVABLE_MARKER = "LIVESPEC_IMPLEMENT_WORKFLOW_EDIT_UNPROVABLE"
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


def _sandbox(*, tmp_path: Path, with_origin: bool = True) -> Path:
    work = tmp_path / "work"
    work.mkdir()
    _git(work, "init", "-b", "master")
    _git(work, "config", "user.name", "workflow-guard-test")
    _git(work, "config", "user.email", "workflow-guard-test@example.invalid")
    (work / ".github" / "workflows").mkdir(parents=True)
    (work / ".github" / "actions").mkdir(parents=True)
    (work / "base.txt").write_text("base\n", encoding="utf-8")
    (work / ".github" / "workflows" / "ci.yml").write_text("name: ci\n", encoding="utf-8")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "base")
    if with_origin:
        _git(work, "update-ref", "refs/remotes/origin/master", "HEAD")
    _git(work, "switch", "-c", "fabro/run/01RUN")
    return work


def _run_guard(*, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/sh", "-c", _guard_script()],
        cwd=str(cwd),
        check=False,
        text=True,
        capture_output=True,
    )


def _git_file(*, cwd: Path, name: str) -> str:
    path = Path(_git(cwd, "rev-parse", "--git-path", name).strip())
    return (cwd / path).read_text(encoding="utf-8")


def _commit_all(*, cwd: Path, message: str) -> None:
    _git(cwd, "add", "-A")
    _git(cwd, "commit", "-m", message)


def test_the_guard_sits_between_the_completion_gate_and_the_diff_breaker() -> None:
    completion = _edges_from(source="implement_completion")
    assert _GUARD in completion
    assert 'condition="preferred_label=complete"' in completion[_GUARD]
    assert "implementation_diff" not in completion

    guard = _edges_from(source=_GUARD)
    assert set(guard) == {"needs_human", "implementation_diff"}
    assert 'condition="outcome=failed"' in guard["needs_human"]
    # Exactly one unconditional out-edge: a node whose every edge carries a
    # condition is rejected by the engine as `all_conditional_edges`.
    assert "condition" not in guard["implementation_diff"]


def test_a_diff_with_no_workflow_file_passes_the_guard(tmp_path: Path) -> None:
    work = _sandbox(tmp_path=tmp_path)
    (work / "feature.py").write_text("x = 1\n", encoding="utf-8")
    (work / ".github" / "actions" / "build.yml").write_text("name: build\n", encoding="utf-8")
    _commit_all(cwd=work, message="feature")

    result = _run_guard(cwd=work)

    assert result.returncode == 0, result.stderr


def test_a_committed_workflow_edit_ends_the_stage_naming_the_file(tmp_path: Path) -> None:
    work = _sandbox(tmp_path=tmp_path)
    (work / ".github" / "workflows" / "ci.yml").write_text("name: ci\non: push\n", encoding="utf-8")
    _commit_all(cwd=work, message="edit ci")

    result = _run_guard(cwd=work)

    assert result.returncode == 1
    assert _VERDICT_MARKER in result.stderr
    assert ".github/workflows/ci.yml" in result.stderr
    assert "host" in result.stderr
    cause = _git_file(cwd=work, name="livespec-stage-cause")
    assert cause.startswith("stage: implement\n")
    assert ".github/workflows/ci.yml" in cause
    assert ".github/workflows/ci.yml" in _git_file(cwd=work, name="livespec-needs-human-reason")


def test_the_verdict_names_every_workflow_file_whatever_its_state(tmp_path: Path) -> None:
    work = _sandbox(tmp_path=tmp_path)
    (work / ".github" / "workflows" / "added.yml").write_text("name: added\n", encoding="utf-8")
    _commit_all(cwd=work, message="add a workflow")
    (work / ".github" / "workflows" / "ci.yml").write_text("name: edited\n", encoding="utf-8")
    (work / ".github" / "workflows" / "untracked.yml").write_text("name: new\n", encoding="utf-8")
    (work / "feature.py").write_text("x = 1\n", encoding="utf-8")

    result = _run_guard(cwd=work)

    assert result.returncode == 1
    for name in ("added.yml", "ci.yml", "untracked.yml"):
        assert f".github/workflows/{name}" in result.stderr
    assert "feature.py" not in result.stderr


def test_a_deleted_workflow_file_is_a_workflow_edit(tmp_path: Path) -> None:
    work = _sandbox(tmp_path=tmp_path)
    _git(work, "rm", "-q", ".github/workflows/ci.yml")
    _commit_all(cwd=work, message="remove ci")

    result = _run_guard(cwd=work)

    assert result.returncode == 1
    assert ".github/workflows/ci.yml" in result.stderr


def test_an_unresolvable_base_fails_closed(tmp_path: Path) -> None:
    work = _sandbox(tmp_path=tmp_path, with_origin=False)

    result = _run_guard(cwd=work)

    assert result.returncode == 1
    assert _UNPROVABLE_MARKER in result.stderr
    assert _VERDICT_MARKER not in result.stderr
