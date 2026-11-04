"""Scenario 285 — the Red preview stages its new test before the handoff exists."""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

from tests.prepare_step_support import env_of, steps_in

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_gate_preview_program"
_FAILED_TARGET = "check-keyword-only-args"


def _run(
    *, repo: Path, env: dict[str, str], argv: list[str], check: bool = True
) -> subprocess.CompletedProcess[str]:
    """Run a sandbox-shaped repository command."""
    return subprocess.run(argv, cwd=repo, env=env, check=check, capture_output=True, text=True)


def _git(*, repo: Path, env: dict[str, str], argv: list[str]) -> str:
    """Run Git successfully and return standard output."""
    return _run(repo=repo, env=env, argv=["git", *argv]).stdout.strip()


def _environment(*, home: Path, plugins: Path) -> dict[str, str]:
    """Give the materialized program a stable, skip-bearing environment."""
    inherited = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("GIT_") and name != "COVERAGE_PROCESS_START"
    }
    return {
        **inherited,
        "HOME": str(home),
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "Scenario Author",
        "GIT_AUTHOR_EMAIL": "author@example.invalid",
        "GIT_COMMITTER_NAME": "Scenario Author",
        "GIT_COMMITTER_EMAIL": "author@example.invalid",
        "LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT": str(plugins),
        "LIVESPEC_CHECK_SKIP": _FAILED_TARGET,
    }


def _red_preview_repository(*, tmp_path: Path) -> tuple[Path, Path, dict[str, str]]:
    """Materialize a Red-node repository with a stale handoff and an extra changed path."""
    plugins = tmp_path / "plugins"
    repo = tmp_path / "repository"
    home = tmp_path / "home"
    repo.mkdir()
    home.mkdir()
    env = _environment(home=home, plugins=plugins)
    _ = _run(repo=repo, env=env, argv=["git", "init", "--quiet"])
    _ = (repo / "baseline.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(repo=repo, env=env, argv=["add", "baseline.py"])
    _git(repo=repo, env=env, argv=["commit", "--quiet", "-m", "chore: baseline"])
    test_file = repo / "tests" / "test_red.py"
    test_file.parent.mkdir()
    _ = test_file.write_text("def test_red() -> None:\n    assert False\n", encoding="utf-8")
    _ = (repo / "product.py").write_text("VALUE = 2\n", encoding="utf-8")
    _ = (repo / ".git" / "livespec-implement-handoff.md").write_text(
        "## red\n\nRed test file: `baseline.py`\n", encoding="utf-8"
    )
    hook = repo / ".git" / "hooks" / "pre-commit"
    _ = hook.write_text(
        "#!/bin/sh\n"
        'if test -n "${LIVESPEC_CHECK_SKIP+x}"; then\n'
        "  printf 'preview inherited LIVESPEC_CHECK_SKIP\\n' >&2\n"
        "  exit 9\n"
        "fi\n"
        'test "$(git diff --cached --name-only)" = "tests/test_red.py" || exit 8\n'
        f"printf 'Failed targets (1):\\n  - {_FAILED_TARGET}\\n'\n"
        "exit 1\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)
    preview = importlib.import_module(_MODULE)
    steps = [
        step for step in steps_in(block=preview.gate_preview_prepare_steps_block()) if step.env
    ]
    assert len(steps) == 1
    materialized = _run(
        repo=repo,
        env=env_of(step=steps[0], base=env),
        argv=["sh", "-c", steps[0].script],
        check=False,
    )
    assert materialized.returncode == 0, materialized.stderr
    runner = plugins / preview.GATE_PREVIEW_PROGRAM_FILENAME
    return repo, runner, env


def test_red_preview_stages_exactly_the_named_test_ignoring_handoff_and_other_changes(
    tmp_path: Path,
) -> None:
    """Red previews exactly the test path it is given, without changing its caller's index."""
    repo, runner, env = _red_preview_repository(tmp_path=tmp_path)
    before_head = _git(repo=repo, env=env, argv=["rev-parse", "HEAD"])
    before_index = _git(repo=repo, env=env, argv=["hash-object", "--no-filters", ".git/index"])
    before_history = _git(repo=repo, env=env, argv=["log", "--format=%H"])

    completed = _run(
        repo=repo,
        env=env,
        argv=[sys.executable, str(runner), "red", "tests/test_red.py"],
        check=False,
    )

    assert completed.returncode == 1, completed.stderr
    report = cast("dict[str, Any]", json.loads(completed.stdout.splitlines()[-1]))
    assert report == {
        "failed_targets": [_FAILED_TARGET],
        "status": 1,
        "unset_variables": ["LIVESPEC_CHECK_SKIP"],
    }
    assert _git(repo=repo, env=env, argv=["rev-parse", "HEAD"]) == before_head
    assert (
        _git(repo=repo, env=env, argv=["hash-object", "--no-filters", ".git/index"]) == before_index
    )
    assert _git(repo=repo, env=env, argv=["log", "--format=%H"]) == before_history
    assert _git(repo=repo, env=env, argv=["diff", "--cached", "--name-only"]) == ""
