"""Scenario 285 — an implement turn previews its prospective commit gate safely."""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

from tests.prepare_step_support import env_of, steps_in

_ROOT = Path(__file__).parents[2]
_MODULE_PATH = (
    _ROOT
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_gate_preview_program.py"
)
_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_gate_preview_program"
_FAILED_TARGET = "check-keyword-only-args"


def _run(
    *, repo: Path, env: dict[str, str], argv: list[str], check: bool = True
) -> subprocess.CompletedProcess[str]:
    """Run one real repository command for the preview journey."""
    return subprocess.run(argv, cwd=repo, env=env, check=check, capture_output=True, text=True)


def _git(*, repo: Path, env: dict[str, str], argv: list[str]) -> str:
    """Run git successfully and return its standard output."""
    return _run(repo=repo, env=env, argv=["git", *argv]).stdout.strip()


def _environment(*, home: Path, plugins: Path) -> dict[str, str]:
    """Give the materialized program a clean, stable Git environment."""
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


def _preview_repository(*, tmp_path: Path, preview: Any) -> tuple[Path, Path, dict[str, str]]:
    """Build the real sandbox-shaped repository and materialize its preview program."""
    plugins = tmp_path / "plugins"
    repo = tmp_path / "repository"
    home = tmp_path / "home"
    repo.mkdir()
    home.mkdir()
    env = _environment(home=home, plugins=plugins)
    _ = _run(repo=repo, env=env, argv=["git", "init", "--quiet"])
    _ = (repo / "tracked.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(repo=repo, env=env, argv=["add", "tracked.py"])
    _git(repo=repo, env=env, argv=["commit", "--quiet", "-m", "chore: baseline"])
    _ = (repo / "tracked.py").write_text("VALUE = 2\n", encoding="utf-8")
    _ = (repo / "created.py").write_text("VALUE = 3\n", encoding="utf-8")
    hook = repo / ".git" / "hooks" / "pre-commit"
    _ = hook.write_text(
        "#!/bin/sh\n"
        'if test -n "${LIVESPEC_CHECK_SKIP+x}"; then\n'
        "  printf 'preview inherited LIVESPEC_CHECK_SKIP\\n' >&2\n"
        "  exit 9\n"
        "fi\n"
        "for path in tracked.py created.py; do\n"
        '  git diff --cached --name-only | grep -qx "$path" || exit 8\n'
        "done\n"
        f"printf 'Failed targets (1):\\n  - {_FAILED_TARGET}\\n'\n"
        "exit 1\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)
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


def test_gate_preview_runs_the_hook_against_a_disposable_staged_tree_and_unsets_skips(
    tmp_path: Path,
) -> None:
    """The inherited skip cannot hide a refusing target or mutate the real commit state."""
    assert _MODULE_PATH.is_file(), f"missing Dispatcher gate-preview program at {_MODULE_PATH}"
    preview = importlib.import_module(_MODULE)
    repo, runner, env = _preview_repository(tmp_path=tmp_path, preview=preview)
    before_head = _git(repo=repo, env=env, argv=["rev-parse", "HEAD"])
    before_index = _git(repo=repo, env=env, argv=["hash-object", "--no-filters", ".git/index"])
    before_history = _git(repo=repo, env=env, argv=["log", "--format=%H"])

    completed = _run(
        repo=repo,
        env=env,
        argv=[sys.executable, str(runner), "green"],
        check=False,
    )

    report = cast("dict[str, Any]", json.loads(completed.stdout.splitlines()[-1]))
    assert completed.returncode == 1
    assert report == {
        "failed_targets": [_FAILED_TARGET],
        "status": 1,
        "unset_variables": ["LIVESPEC_CHECK_SKIP"],
    }
    assert env["LIVESPEC_CHECK_SKIP"] == _FAILED_TARGET
    assert _git(repo=repo, env=env, argv=["rev-parse", "HEAD"]) == before_head
    assert (
        _git(repo=repo, env=env, argv=["hash-object", "--no-filters", ".git/index"]) == before_index
    )
    assert _git(repo=repo, env=env, argv=["log", "--format=%H"]) == before_history
    assert _git(repo=repo, env=env, argv=["diff", "--cached", "--name-only"]) == ""
