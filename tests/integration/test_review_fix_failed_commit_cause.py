"""Scenario 179 — review-fix settle exports a failed Green amend's own cause."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_commit_runner_program import (
    COMMIT_RUNNER_PROGRAM_FILENAME,
    commit_runner_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph

_ROOT = Path(__file__).resolve().parents[2]
_GRAPH = (
    _ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item" / "workflow.fabro"
)
_NODE = "review_fix_commit_settle"
_FAILED_TARGET = "check-green-amend"
_HOOK_ERROR = "GREEN-AMEND-HOOK-REFUSAL: test target failed"


def _environment() -> dict[str, str]:
    """Keep the fixture commit independent from the outer hook's Git state."""
    return {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("GIT_", "COV_CORE")) and key != "COVERAGE_PROCESS_START"
    }


def _git(*, repo: Path, argv: list[str]) -> subprocess.CompletedProcess[str]:
    """Run Git in the throwaway repository."""
    return subprocess.run(
        ["git", *argv],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        env={**_environment(), "GIT_EDITOR": "true", "GIT_CONFIG_GLOBAL": "/dev/null"},
    )


def _node_script() -> str:
    """Read the committed review-fix settle script that the factory executes."""
    graph = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    return graph.nodes[_NODE]["script"]


def test_review_fix_settle_exports_a_real_green_amend_hook_refusal(tmp_path: Path) -> None:
    """The settled node output names the real hook's target and diagnostic tail."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo=repo, argv=["init", "--quiet"])
    _git(repo=repo, argv=["config", "user.name", "Fixture"])
    _git(repo=repo, argv=["config", "user.email", "fixture@example.test"])
    _ = (repo / "module.py").write_text("value = 1\n", encoding="utf-8")
    _git(repo=repo, argv=["add", "module.py"])
    _git(repo=repo, argv=["commit", "--quiet", "-m", "test: red"])
    _ = (repo / "module.py").write_text("value = 2\n", encoding="utf-8")
    _git(repo=repo, argv=["add", "module.py"])
    hook = repo / ".git" / "hooks" / "pre-commit"
    _ = hook.write_text(
        "#!/bin/sh\n"
        "printf 'lefthook v1.13.6 hook: pre-commit\\n'\n"
        f"printf 'Failed targets (1):\\n  - {_FAILED_TARGET}\\n'\n"
        f"printf '{_HOOK_ERROR}\\n'\n"
        "exit 1\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    runner = plugins / COMMIT_RUNNER_PROGRAM_FILENAME
    _ = runner.write_text(commit_runner_program_source(), encoding="utf-8")

    started = subprocess.run(
        [sys.executable, str(runner), "start", "--", "git", "commit", "--amend", "--no-edit"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        env=_environment(),
    )
    run_id = started.stdout.strip()
    waited = subprocess.run(
        [sys.executable, str(runner), "wait", run_id, "--timeout-seconds", "60"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        env=_environment(),
    )
    assert json.loads(waited.stdout)["state"] == "failed"

    result = subprocess.run(
        ["sh", "-c", _node_script()],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        env={**_environment(), "LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT": str(plugins)},
    )

    assert result.returncode == 0, result.stderr
    assert run_id in result.stderr
    assert "exit status 1" in result.stderr
    assert f"failed targets: {_FAILED_TARGET}" in result.stderr
    assert "repository commit hook ran" in result.stderr
    assert _HOOK_ERROR in result.stderr
