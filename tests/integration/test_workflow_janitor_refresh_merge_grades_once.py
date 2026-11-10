"""Scenario 305: a janitor refresh merge pays the full aggregate once, not twice.

The janitor must create the refresh merge without committing it and commit it
through the repository's hooks, so the pre-commit hook's passing full aggregate
on the merged tree can stand in for the janitor's own.  Real throwaway
repositories with real hooks are used because a stubbed merge cannot show
whether the hook fired, which tree it judged, or what the janitor then skipped.
"""

from __future__ import annotations

import json
import os
import shlex
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
_SCOPE_ADAPTER = _REPO_ROOT / "dev-tooling" / "green-token-scope.sh"
_DEFAULT_BRANCH = "master"
_PUBLISH_BRANCH = "feat/bd-ib-yqjaut"
_STATE_DIRECTORY = ".git/livespec-publication"
_TOKEN = ".git/livespec-green-token.json"
_PICKER = "check-codex-skill-picker"


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
    _ = target.write_text(text, encoding="utf-8")
    _ = _git("add", path, cwd=cwd)
    _ = _git("commit", "-m", subject, cwd=cwd)
    return _git("rev-parse", "HEAD", cwd=cwd).stdout.strip()


def _janitor_script(*, check_suite: str) -> str:
    graph = parse_dot_graph(text=_WORKFLOW.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    script: str = graph.nodes["janitor"]["script"]
    return (
        script.replace("{{ inputs.default_branch }}", _DEFAULT_BRANCH)
        .replace("{{ inputs.sandbox_check_suite }}", check_suite)
        .replace("{{ inputs.conformance_hook_install }}", "")
        .replace(r"\"", '"')
    )


def _world(*, root: Path) -> Path:
    """A run whose publish branch already exists, so the refresh must be a merge."""
    origin = root / "origin.git"
    _ = _git("init", "--bare", "--initial-branch=master", str(origin), cwd=root)
    seed = root / "seed"
    seed.mkdir()
    _ = _git("init", "--initial-branch=master", cwd=seed)
    _ = _git("config", "user.name", "Test", cwd=seed)
    _ = _git("config", "user.email", "test@example.invalid", cwd=seed)
    _ = _commit(
        cwd=seed,
        path="dev-tooling/green-token-scope.sh",
        text=_SCOPE_ADAPTER.read_text(encoding="utf-8"),
        subject="chore: seed the scope adapter",
    )
    _ = _git("remote", "add", "origin", str(origin), cwd=seed)
    _ = _git("push", "-u", "origin", _DEFAULT_BRANCH, cwd=seed)

    run = root / "run"
    _ = _git("clone", str(origin), str(run), cwd=root)
    _ = _git("config", "user.name", "Test", cwd=run)
    _ = _git("config", "user.email", "test@example.invalid", cwd=run)
    _ = _git("switch", "-c", "fabro/run/test", cwd=run)
    _ = _commit(cwd=run, path="owned.txt", text="run\n", subject="feat: run work")
    _ = _git("push", "origin", f"HEAD:refs/heads/{_PUBLISH_BRANCH}", cwd=run)

    default = root / "default"
    _ = _git("clone", str(origin), str(default), cwd=root)
    _ = _git("config", "user.name", "Test", cwd=default)
    _ = _git("config", "user.email", "test@example.invalid", cwd=default)
    _ = _commit(cwd=default, path="moved.txt", text="default\n", subject="feat: default move")
    _ = _git("push", "origin", _DEFAULT_BRANCH, cwd=default)
    return run


def _hook(*, run: Path, name: str, body: str) -> None:
    hook = run / ".git" / "hooks" / name
    _ = hook.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    _ = hook.chmod(hook.stat().st_mode | stat.S_IXUSR)


def _evidence_hook_body(*, judged_tree: str) -> str:
    """A pre-commit hook that records a passed aggregate for ``judged_tree``."""
    return (
        "tree=$(git write-tree)\n"
        f"judged={judged_tree}\n"
        "token=$(git rev-parse --git-path livespec-green-token.json)\n"
        'printf \'{"mode": "normal", "scope": "full-suite", "tree_hash": "%s", '
        '"pre_commit_aggregate": {"tree_hash": "%s", "run_id": "pre-commit-aggregate:t:%s", '
        '"output_checksum": "sha256:0", "captured_at": "2026-11-09T00:00:00Z"}}\' '
        '"$judged" "$judged" "$tree" > "$token"'
    )


def _plugins(*, root: Path) -> Path:
    plugins = root / "plugins"
    plugins.mkdir()
    gate = plugins / "livespec-run-plugin-gate.py"
    _ = gate.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    _ = gate.chmod(gate.stat().st_mode | stat.S_IXUSR)
    return plugins


def _suite(*, root: Path, run: Path) -> tuple[Path, Path]:
    """A stand-in aggregate that records the head it was asked to grade."""
    log = root / "aggregate-calls"
    path = root / "suite"
    _ = path.write_text(
        f"#!/bin/sh\ngit -C {shlex.quote(str(run))} rev-parse HEAD >> {shlex.quote(str(log))}\n",
        encoding="utf-8",
    )
    _ = path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path, log


def _run_janitor(*, run: Path, plugins: Path, check_suite: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sh", "-c", _janitor_script(check_suite=check_suite)],
        check=False,
        capture_output=True,
        cwd=run,
        env={
            key: value
            for key, value in os.environ.items()
            if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE")
        }
        | {
            "LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT": str(plugins),
            "LIVESPEC_PUBLISH_BRANCH": _PUBLISH_BRANCH,
        },
        text=True,
    )


def _calls(*, log: Path) -> list[str]:
    return log.read_text(encoding="utf-8").split() if log.exists() else []


def _parents(*, run: Path) -> list[str]:
    return _git("rev-list", "--parents", "-n", "1", "HEAD", cwd=run).stdout.split()[1:]


def test_a_refresh_merge_whose_hook_passed_the_aggregate_is_graded_once(*, tmp_path: Path) -> None:
    run = _world(root=tmp_path)
    plugins = _plugins(root=tmp_path)
    suite, log = _suite(root=tmp_path, run=run)
    # The hook judges whatever tree the merge staged, as the real aggregate does.
    _hook(run=run, name="pre-commit", body=_evidence_hook_body(judged_tree="$tree"))

    janitor = _run_janitor(run=run, plugins=plugins, check_suite=str(suite))

    assert janitor.returncode == 0, janitor.stderr
    assert len(_parents(run=run)) == 2
    assert _calls(log=log) == []
    head = _git("rev-parse", "HEAD", cwd=run).stdout.strip()
    passed = (run / _STATE_DIRECTORY / "livespec-janitor-passed-head").read_text(encoding="utf-8")
    assert passed.strip() == head
    recorded = json.loads((run / _TOKEN).read_text(encoding="utf-8"))
    assert recorded["tree_hash"] == _git("rev-parse", "HEAD^{tree}", cwd=run).stdout.strip()
    assert recorded["skipped_targets"] == [_PICKER]
    honoured = subprocess.run(
        ["bash", "dev-tooling/green-token-scope.sh", "check", _PICKER],
        check=False,
        cwd=run,
    )
    assert honoured.returncode == 0


def test_a_refresh_merge_whose_hook_recorded_no_aggregate_runs_the_janitors_own(
    *, tmp_path: Path
) -> None:
    run = _world(root=tmp_path)
    plugins = _plugins(root=tmp_path)
    suite, log = _suite(root=tmp_path, run=run)
    _hook(run=run, name="pre-commit", body="exit 0")

    janitor = _run_janitor(run=run, plugins=plugins, check_suite=str(suite))

    assert janitor.returncode == 0, janitor.stderr
    head = _git("rev-parse", "HEAD", cwd=run).stdout.strip()
    assert _calls(log=log) == [head]


def test_a_refresh_merge_whose_hook_judged_another_tree_runs_the_janitors_own(
    *, tmp_path: Path
) -> None:
    run = _world(root=tmp_path)
    plugins = _plugins(root=tmp_path)
    suite, log = _suite(root=tmp_path, run=run)
    stale = _git("rev-parse", "HEAD^{tree}", cwd=run).stdout.strip()
    _hook(run=run, name="pre-commit", body=_evidence_hook_body(judged_tree=stale))

    janitor = _run_janitor(run=run, plugins=plugins, check_suite=str(suite))

    assert janitor.returncode == 0, janitor.stderr
    head = _git("rev-parse", "HEAD", cwd=run).stdout.strip()
    assert _calls(log=log) == [head]


def test_a_refresh_merge_the_hook_refuses_is_not_committed_and_names_its_failed_targets(
    *, tmp_path: Path
) -> None:
    run = _world(root=tmp_path)
    plugins = _plugins(root=tmp_path)
    suite, log = _suite(root=tmp_path, run=run)
    before = _git("rev-parse", "HEAD", cwd=run).stdout.strip()
    _hook(
        run=run,
        name="pre-commit",
        body=("printf 'Failed targets (1):\\n' >&2\n" "printf '  - check-types\\n' >&2\n" "exit 1"),
    )

    janitor = _run_janitor(run=run, plugins=plugins, check_suite=str(suite))

    assert janitor.returncode != 0
    assert _git("rev-parse", "HEAD", cwd=run).stdout.strip() == before
    assert _calls(log=log) == []
    brief = (run / _STATE_DIRECTORY / "livespec-refresh-repair-brief").read_text(encoding="utf-8")
    assert f"pre-refresh-head: {before}" in brief
    assert "failed-hook-targets: check-types" in brief
