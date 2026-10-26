"""The durable sandbox commit runner required by Scenario 179."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MODULE_PATH = (
    _REPO_ROOT
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_commit_runner.py"
)


def test_the_materialized_runner_keeps_the_original_commit_verdict(tmp_path: Path) -> None:
    """A wait sees the started commit's hook output, not a second hook run."""
    assert _MODULE_PATH.is_file()

    spec = importlib.util.spec_from_file_location("commit_runner", _MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    runner = tmp_path / module.COMMIT_RUNNER_PROGRAM_FILENAME
    _ = runner.write_text(module.commit_runner_program_source(), encoding="utf-8")
    repo = _repository_with_refusing_hook(tmp_path=tmp_path)

    started = _run(
        program=runner,
        repo=repo,
        args=("start", "--", "git", "commit", "--allow-empty", "-m", "test"),
    )
    assert started.returncode == 0, started.stderr
    run_id = json.loads(started.stdout)["run_id"]

    duplicate = _run(
        program=runner,
        repo=repo,
        args=("start", "--", "git", "commit", "--allow-empty", "-m", "duplicate"),
    )
    assert duplicate.returncode != 0
    assert run_id in duplicate.stderr

    waited = _run(
        program=runner, repo=repo, args=("wait", "--run", run_id, "--timeout-seconds", "3")
    )
    assert waited.returncode == 0, waited.stderr
    terminal = json.loads(waited.stdout)
    assert terminal["state"] == "failed"
    assert terminal["exit_code"] == 1
    assert "Failed targets (1):" in terminal["output_tail"]
    assert "check-types" in terminal["output_tail"]


def _repository_with_refusing_hook(*, tmp_path: Path) -> Path:
    """Create one real git repository whose commit hook takes a visible moment."""
    repo = tmp_path / "repository"
    repo.mkdir()
    _ = subprocess.run(["git", "init", "--quiet"], cwd=repo, check=True)
    _ = subprocess.run(["git", "config", "user.name", "Test Runner"], cwd=repo, check=True)
    _ = subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True
    )
    hook = repo / ".git" / "hooks" / "pre-commit"
    _ = hook.write_text(
        "#!/bin/sh\nsleep 1\nprintf 'Failed targets (1):\\n  - check-types\\n' >&2\nexit 1\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)
    return repo


def _run(*, program: Path, repo: Path, args: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    """Run the materialized program with a minimal, deterministic environment."""
    return subprocess.run(
        [sys.executable, str(program), *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )
