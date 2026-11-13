"""The implement stage host-routes any working diff that edits a workflow."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

_WORKFLOW = Path(".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro")
_GUARD = "implement_workflow_guard"
_VERDICT = "LIVESPEC_IMPLEMENT_WORKFLOW_EDIT_HOST_ROUTE"
_UNPROVABLE = "LIVESPEC_IMPLEMENT_WORKFLOW_EDIT_UNPROVABLE"
_SCRIPT = re.compile(r'script="(?P<value>(?:[^"\\]|\\.)*)"')
_EDGE = re.compile(
    r"(?m)^[ \t]*(?P<src>[A-Za-z_]\w*)[ \t]*->[ \t]*(?P<dst>[A-Za-z_]\w*)(?P<attrs>.*)$"
)


def _guard_script() -> str:
    graph = _WORKFLOW.read_text(encoding="utf-8")
    block = re.search(
        rf"^\s*{_GUARD}\s*\[(?P<body>.*?)^\s*\]",
        graph,
        re.DOTALL | re.MULTILINE,
    )
    assert block is not None, f"the graph declares no {_GUARD} node"
    attribute = _SCRIPT.search(block.group("body"))
    assert attribute is not None, f"{_GUARD} carries no script attribute"
    return re.sub(r"\\(?P<escaped>.)", r"\g<escaped>", attribute.group("value")).replace(
        "{{ inputs.default_branch }}", "master"
    )


def _edges_from(*, source: str) -> dict[str, str]:
    return {
        edge.group("dst"): edge.group("attrs")
        for edge in _EDGE.finditer(_WORKFLOW.read_text(encoding="utf-8"))
        if edge.group("src") == source
    }


def _git(cwd: Path, *argv: str) -> str:
    return subprocess.run(
        ["git", *argv], cwd=cwd, check=True, text=True, capture_output=True
    ).stdout


def _sandbox(*, tmp_path: Path, with_origin: bool = True) -> Path:
    work = tmp_path / "work"
    work.mkdir()
    _git(work, "init", "-b", "master")
    _git(work, "config", "user.name", "workflow-guard-test")
    _git(work, "config", "user.email", "workflow-guard-test@example.invalid")
    (work / ".github" / "workflows").mkdir(parents=True)
    (work / ".github" / "actions").mkdir(parents=True)
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
        cwd=cwd,
        check=False,
        text=True,
        capture_output=True,
    )


def test_guard_sits_before_the_implementation_diff_breaker() -> None:
    completion = _edges_from(source="implement_completion")
    assert _GUARD in completion
    assert "implementation_diff" not in completion
    guard = _edges_from(source=_GUARD)
    assert set(guard) == {"needs_human", "implementation_diff"}
    assert 'condition="outcome=failed"' in guard["needs_human"]
    assert "condition" not in guard["implementation_diff"]


def test_guard_allows_a_diff_outside_workflows(tmp_path: Path) -> None:
    work = _sandbox(tmp_path=tmp_path)
    (work / ".github" / "actions" / "build.yml").write_text("name: build\n", encoding="utf-8")

    result = _run_guard(cwd=work)

    assert result.returncode == 0, result.stderr


def test_guard_names_every_workflow_file_in_the_working_diff(tmp_path: Path) -> None:
    work = _sandbox(tmp_path=tmp_path)
    (work / ".github" / "workflows" / "ci.yml").write_text("name: edited\n", encoding="utf-8")
    (work / ".github" / "workflows" / "added.yml").write_text("name: added\n", encoding="utf-8")
    (work / ".github" / "workflows" / "untracked.yml").write_text("name: new\n", encoding="utf-8")

    result = _run_guard(cwd=work)

    assert result.returncode == 1
    assert _VERDICT in result.stderr
    assert "host-route" in result.stderr
    for name in ("added.yml", "ci.yml", "untracked.yml"):
        assert f".github/workflows/{name}" in result.stderr


def test_guard_fails_closed_when_the_default_branch_base_is_unreadable(tmp_path: Path) -> None:
    work = _sandbox(tmp_path=tmp_path, with_origin=False)

    result = _run_guard(cwd=work)

    assert result.returncode == 1
    assert _UNPROVABLE in result.stderr
