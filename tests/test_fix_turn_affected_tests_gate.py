"""Fix-turn commits take the affected-tests path before the janitor aggregate."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_commit_runner_program import (
    commit_runner_program_source,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PRE_COMMIT = _REPO_ROOT / "dev-tooling" / "just-check-pre-commit.sh"
_CHECK_CHANGED = _REPO_ROOT / "dev-tooling" / "just-check-changed.sh"
_WORKFLOW = ".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro"


def _run(*, argv: list[str], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, check=False)


def _write_tool(*, directory: Path, name: str, body: str) -> None:
    path = directory / name
    _ = path.write_text(body, encoding="utf-8")
    _ = path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _repository(*, tmp_path: Path) -> tuple[Path, dict[str, str], Path]:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    for arguments in (
        ["git", "init", "--quiet"],
        ["git", "config", "user.name", "Test User"],
        ["git", "config", "user.email", "test@example.invalid"],
    ):
        result = _run(argv=arguments, cwd=repo, env=os.environ.copy())
        assert result.returncode == 0, result.stderr
    source = repo / ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/widget.py"
    source.parent.mkdir(parents=True)
    _ = source.write_text("VALUE = 0\n", encoding="utf-8")
    _ = _run(argv=["git", "add", "."], cwd=repo, env=os.environ.copy())
    baseline = _run(argv=["git", "commit", "-m", "baseline"], cwd=repo, env=os.environ.copy())
    assert baseline.returncode == 0, baseline.stderr

    tools = tmp_path / "bin"
    tools.mkdir()
    log = tmp_path / "just.log"
    _write_tool(
        directory=tools,
        name="uv",
        body=(
            "#!/usr/bin/env bash\n"
            "case \"$*\" in *'pre_commit_delegate run'*) exit 75 ;; *) exit 0 ;; esac\n"
        ),
    )
    _write_tool(
        directory=tools,
        name="just",
        body=(
            "#!/usr/bin/env bash\n"
            'printf \'%s\\n\' "$*" >> "$FAKE_LOG"\n'
            'if [[ "$*" == check-changed && "${FAKE_CHANGED_UNSCOPABLE:-}" == true ]]; then exit 75; fi\n'
        ),
    )
    return (
        repo,
        {**os.environ, "PATH": f"{tools}{os.pathsep}{os.environ['PATH']}", "FAKE_LOG": str(log)},
        log,
    )


def _stage(*, repo: Path, path: str, text: str) -> None:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    _ = target.write_text(text, encoding="utf-8")
    staged = _run(argv=["git", "add", path], cwd=repo, env=os.environ.copy())
    assert staged.returncode == 0, staged.stderr


def test_fix_stage_scopes_then_falls_back_to_the_aggregate(*, tmp_path: Path) -> None:
    """A scopeable fix avoids the aggregate, while an unknown scope cannot."""
    scoped_repo, scoped_env, scoped_log = _repository(tmp_path=tmp_path / "scoped")
    _stage(
        repo=scoped_repo,
        path=".claude-plugin/scripts/livespec_orchestrator_beads_fabro/widget.py",
        text="VALUE = 1\n",
    )

    scoped = _run(
        argv=["bash", str(_PRE_COMMIT)],
        cwd=scoped_repo,
        env={**scoped_env, "LIVESPEC_AGENT_STAGE": "fix"},
    )

    assert scoped.returncode == 0, scoped.stderr
    assert scoped_log.read_text(encoding="utf-8").splitlines() == ["check-changed"]

    unknown_repo, unknown_env, unknown_log = _repository(tmp_path=tmp_path / "unknown")
    _stage(repo=unknown_repo, path="README.md", text="unscoped\n")
    unknown = _run(
        argv=["bash", str(_PRE_COMMIT)],
        cwd=unknown_repo,
        env={
            **unknown_env,
            "LIVESPEC_AGENT_STAGE": "fix",
            "FAKE_CHANGED_UNSCOPABLE": "true",
        },
    )

    assert unknown.returncode == 0, unknown.stderr
    assert unknown_log.read_text(encoding="utf-8").splitlines() == [
        "check-changed",
        "check-skipping check-codex-skill-picker",
    ]


def test_workflow_change_selects_graph_reading_tests(*, tmp_path: Path) -> None:
    """A graph edit is scoped to the tests that read the workflow payload."""
    tools = tmp_path / "bin"
    tools.mkdir()
    log = tmp_path / "just.log"
    _write_tool(
        directory=tools,
        name="just",
        body=(
            "#!/usr/bin/env bash\n"
            'printf \'%s\\n\' "$*" >> "$FAKE_LOG"\n'
            'if [[ "$*" == changed-files ]]; then exit 0; fi\n'
        ),
    )
    _write_tool(
        directory=tools,
        name="git",
        body=(
            "#!/usr/bin/env bash\n"
            "if [[ \"$*\" == *'diff --name-only'* ]]; then printf '%s\\n' '" + _WORKFLOW + "'; fi\n"
        ),
    )
    _write_tool(
        directory=tools,
        name="rg",
        body="#!/usr/bin/env bash\nprintf '%s\\n' tests/test_graph_reader.py\n",
    )

    result = _run(
        argv=["bash", str(_CHECK_CHANGED)],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{tools}{os.pathsep}{os.environ['PATH']}",
            "FAKE_LOG": str(log),
        },
    )

    assert result.returncode == 0, result.stderr
    assert log.read_text(encoding="utf-8").splitlines() == [
        "changed-files",
        "check-staged-tests tests/test_graph_reader.py",
    ]


def test_commit_runner_keeps_the_fix_stage_for_the_hook() -> None:
    """The materialized commit process preserves its stage for pre-commit selection."""
    source = commit_runner_program_source()

    assert "env=os.environ.copy()" in source
    assert 'if k != "LIVESPEC_AGENT_STAGE"' not in source
