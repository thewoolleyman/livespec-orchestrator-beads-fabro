"""Scenario 305: a commit-hook refusal while janitor refreshes enters repair.

The refresh must happen before janitor runs the aggregate.  This exercises the
real rebase and hook because a stubbed failure cannot show whether Git restored
the pre-refresh head or which part of its diagnostics the repair brief kept.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = (
    _REPO_ROOT
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "workflow.fabro"
)
_REFRESH_SCRIPT = _REPO_ROOT / "dev-tooling" / "refresh-before-janitor.sh"
_DEFAULT_BRANCH = "master"
_STATE_DIRECTORY = ".git/livespec-publication"


def _git(*argv: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *argv],
        check=True,
        capture_output=True,
        cwd=cwd,
        text=True,
    )


def _commit(*, cwd: Path, path: str, text: str, subject: str) -> str:
    target = cwd / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    _ = _git("add", path, cwd=cwd)
    _ = _git("commit", "-m", subject, cwd=cwd)
    return _git("rev-parse", "HEAD", cwd=cwd).stdout.strip()


def _janitor_script() -> str:
    graph = parse_dot_graph(text=_WORKFLOW.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    script: str = graph.nodes["janitor"]["script"]
    return (
        script.replace("{{ inputs.default_branch }}", _DEFAULT_BRANCH)
        .replace("{{ inputs.sandbox_check_suite }}", "true")
        .replace("{{ inputs.conformance_hook_install }}", "")
        .replace(r"\"", '"')
        .replace("dev-tooling/refresh-before-janitor.sh", str(_REFRESH_SCRIPT))
    )


def _world(*, root: Path) -> tuple[Path, str]:
    origin = root / "origin.git"
    _ = _git("init", "--bare", "--initial-branch=master", str(origin), cwd=root)
    seed = root / "seed"
    seed.mkdir()
    _ = _git("init", "--initial-branch=master", cwd=seed)
    _ = _git("config", "user.name", "Test", cwd=seed)
    _ = _git("config", "user.email", "test@example.invalid", cwd=seed)
    _ = _commit(cwd=seed, path="base.txt", text="base\n", subject="chore: seed")
    _ = _git("remote", "add", "origin", str(origin), cwd=seed)
    _ = _git("push", "-u", "origin", _DEFAULT_BRANCH, cwd=seed)

    run = root / "run"
    _ = _git("clone", str(origin), str(run), cwd=root)
    _ = _git("config", "user.name", "Test", cwd=run)
    _ = _git("config", "user.email", "test@example.invalid", cwd=run)
    _ = _git("switch", "-c", "fabro/run/test", cwd=run)
    before = _commit(cwd=run, path="run.txt", text="run\n", subject="feat: run work")

    default = root / "default"
    _ = _git("clone", str(origin), str(default), cwd=root)
    _ = _git("config", "user.name", "Test", cwd=default)
    _ = _git("config", "user.email", "test@example.invalid", cwd=default)
    _ = _commit(cwd=default, path="default.txt", text="default\n", subject="feat: default move")
    _ = _git("push", "origin", _DEFAULT_BRANCH, cwd=default)
    return run, before


def _plugins(*, root: Path) -> Path:
    plugins = root / "plugins"
    plugins.mkdir()
    gate = plugins / "livespec-run-plugin-gate.py"
    gate.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    gate.chmod(gate.stat().st_mode | stat.S_IXUSR)
    return plugins


def _refuse_refresh_commit(*, run: Path) -> None:
    hook = run / ".git" / "hooks" / "prepare-commit-msg"
    lines = [
        "#!/bin/sh",
    ]
    lines.extend(f"printf 'hook-line-{number}\\n' >&2" for number in range(1, 101))
    lines.extend(
        (
            "printf 'error: hook-own-error-line\\n' >&2",
            "printf 'Failed targets (2):\\n' >&2",
            "printf '  - check-format\\n' >&2",
            "printf '  - check-types\\n' >&2",
            "exit 1",
            "",
        )
    )
    hook.write_text("\n".join(lines), encoding="utf-8")
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR)


def test_a_hook_refused_pre_janitor_refresh_restores_and_writes_its_repair_brief(
    *, tmp_path: Path
) -> None:
    """Only the hook's final 80 lines, not Git's trailing diagnostics, are briefed."""
    run, before = _world(root=tmp_path)
    plugins = _plugins(root=tmp_path)
    _refuse_refresh_commit(run=run)

    result = subprocess.run(
        ["sh", "-c", _janitor_script()],
        check=False,
        capture_output=True,
        cwd=run,
        env={
            key: value
            for key, value in os.environ.items()
            if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE")
        }
        | {"LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT": str(plugins)},
        text=True,
    )

    assert result.returncode != 0, result.stdout
    assert _git("rev-parse", "HEAD", cwd=run).stdout.strip() == before
    git_dir = Path(_git("rev-parse", "--git-dir", cwd=run).stdout.strip())
    assert not (run / git_dir / "rebase-merge").exists()
    assert not (run / git_dir / "rebase-apply").exists()
    brief = (run / _STATE_DIRECTORY / "livespec-refresh-repair-brief").read_text(encoding="utf-8")
    assert f"pre-refresh-head: {before}" in brief
    assert "refresh-target: " in brief
    assert "failed-hook-targets: check-format check-types" in brief
    hook_tail = brief.split("hook-output-last-80-lines:\n", maxsplit=1)[1].splitlines()
    assert hook_tail[0] == "hook-line-25"
    assert hook_tail[-1] == "  - check-types"
    assert len(hook_tail) == 80
    assert "hook-line-100" in hook_tail
    assert "error: hook-own-error-line" in hook_tail
    assert "hook-line-24" not in hook_tail
    assert "hook-line-1" not in hook_tail
