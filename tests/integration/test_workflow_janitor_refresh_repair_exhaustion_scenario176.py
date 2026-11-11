"""Scenario 176: the janitor's pre-aggregate refresh repair has a round bound.

The janitor node used to count each refresh-repair round and never test the
count, so a run whose refresh could not converge spent janitor and fix visits to
the visit cap and ended ``workflow_error`` (measured on bd-ib-so6fef run
01M6WEK4Q0EC9Y9V0J9ZJ5ZQWV: six janitor visits, no ``needs_human``).  The
shared ``livespec_refresh_repair`` helper already bounds ``publish_draft`` and
``pr_refresh`` at two rounds; these cases bind the same bound on the janitor arm.

Every behavioural case EXECUTES the shipped node bytes, taken through
``parse_dot_graph``, in a real throwaway clone, because both the bound and the
route are shell and a substring assertion cannot tell an arm that runs from one
sitting behind an earlier ``exit``.  The routing claim is read off the graph.
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
_DEFAULT_BRANCH = "master"
_STATE_DIRECTORY = ".git/livespec-publication"
_ROUTE = "janitor_refresh_route"
_EXHAUSTED_MARKER = "livespec-refresh-repair-exhausted"
_COUNT_FILE = "livespec-refresh-repair-count"
_BRIEF_FILE = "livespec-refresh-repair-brief"
_REASON_FILE = "livespec-needs-human-reason"


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


def _script(*, node: str) -> str:
    graph = parse_dot_graph(text=_WORKFLOW.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    script: str = graph.nodes[node]["script"]
    return (
        script.replace("{{ inputs.default_branch }}", _DEFAULT_BRANCH)
        .replace("{{ inputs.sandbox_check_suite }}", "true")
        .replace(r"\"", '"')
    )


def _world(*, root: Path, conflicting: bool) -> tuple[Path, str]:
    origin = root / "origin.git"
    _ = _git("init", "--bare", "--initial-branch=master", str(origin), cwd=root)
    seed = root / "seed"
    seed.mkdir()
    _ = _git("init", "--initial-branch=master", cwd=seed)
    _ = _git("config", "user.name", "Test", cwd=seed)
    _ = _git("config", "user.email", "test@example.invalid", cwd=seed)
    _ = _commit(cwd=seed, path="shared.txt", text="base\n", subject="chore: seed")
    _ = _git("remote", "add", "origin", str(origin), cwd=seed)
    _ = _git("push", "-u", "origin", _DEFAULT_BRANCH, cwd=seed)

    run = root / "run"
    _ = _git("clone", str(origin), str(run), cwd=root)
    _ = _git("config", "user.name", "Test", cwd=run)
    _ = _git("config", "user.email", "test@example.invalid", cwd=run)
    _ = _git("switch", "-c", "fabro/run/test", cwd=run)
    run_path = "shared.txt" if conflicting else "owned.txt"
    before = _commit(cwd=run, path=run_path, text="run\n", subject="feat: run work")

    default = root / "default"
    _ = _git("clone", str(origin), str(default), cwd=root)
    _ = _git("config", "user.name", "Test", cwd=default)
    _ = _git("config", "user.email", "test@example.invalid", cwd=default)
    _ = _commit(cwd=default, path="shared.txt", text="default\n", subject="feat: default move")
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
        "printf 'Failed targets (1):\\n' >&2",
        "printf '  - check-types\\n' >&2",
        "exit 1",
        "",
    ]
    hook.write_text("\n".join(lines), encoding="utf-8")
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR)


def _record_rounds(*, run: Path, rounds: int) -> None:
    state = run / _STATE_DIRECTORY
    state.mkdir(parents=True, exist_ok=True)
    _ = (state / _COUNT_FILE).write_text(f"{rounds}\n", encoding="utf-8")


def _run(*, node: str, run: Path, plugins: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sh", "-c", _script(node=node)],
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


def _routes_to(*, run: Path, plugins: Path) -> str:
    done = _run(node=_ROUTE, run=run, plugins=plugins)
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


def _assert_exhausted(*, run: Path, plugins: Path, before: str) -> None:
    janitor = _run(node="janitor", run=run, plugins=plugins)

    assert janitor.returncode != 0, janitor.stdout
    assert "LIVESPEC_REFRESH_REPAIR_EXHAUSTED" in janitor.stderr
    assert _git("rev-parse", "HEAD", cwd=run).stdout.strip() == before
    state = run / _STATE_DIRECTORY
    assert (state / _EXHAUSTED_MARKER).is_file()
    assert not (state / _BRIEF_FILE).exists()
    reason = (run / ".git" / _REASON_FILE).read_text(encoding="utf-8")
    assert reason.startswith("refresh-repair-exhausted:")
    assert before in reason
    assert _routes_to(run=run, plugins=plugins) == '{"preferred_next_label":"needs_human"}'


def test_a_conflicting_janitor_refresh_after_two_rounds_is_exhausted(*, tmp_path: Path) -> None:
    run, before = _world(root=tmp_path, conflicting=True)
    plugins = _plugins(root=tmp_path)
    _record_rounds(run=run, rounds=2)

    _assert_exhausted(run=run, plugins=plugins, before=before)


def test_a_hook_refused_janitor_refresh_after_two_rounds_is_exhausted(*, tmp_path: Path) -> None:
    run, before = _world(root=tmp_path, conflicting=False)
    plugins = _plugins(root=tmp_path)
    _refuse_refresh_commit(run=run)
    _record_rounds(run=run, rounds=2)

    _assert_exhausted(run=run, plugins=plugins, before=before)


def test_the_graph_routes_an_exhausted_janitor_visit_to_needs_human() -> None:
    graph = parse_dot_graph(text=_WORKFLOW.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    arms = {
        edge.destination: edge.attributes.get("condition", "")
        for edge in graph.edges
        if edge.source == _ROUTE
    }

    assert arms["needs_human"] == "preferred_label=needs_human"
    assert arms["refresh_repair"] == "preferred_label=refresh_repair"
    assert arms["needs_human"] != arms["refresh_repair"]


def test_a_conflicting_janitor_refresh_with_budget_remaining_still_enters_repair(
    *, tmp_path: Path
) -> None:
    run, before = _world(root=tmp_path, conflicting=True)
    plugins = _plugins(root=tmp_path)
    _record_rounds(run=run, rounds=1)

    janitor = _run(node="janitor", run=run, plugins=plugins)

    assert janitor.returncode != 0
    assert "LIVESPEC_REFRESH_REPAIR_EXHAUSTED" not in janitor.stderr
    assert _git("rev-parse", "HEAD", cwd=run).stdout.strip() == before
    state = run / _STATE_DIRECTORY
    brief = (state / _BRIEF_FILE).read_text(encoding="utf-8")
    assert f"pre-refresh-head: {before}" in brief
    assert "conflicted-paths: shared.txt" in brief
    assert not (state / _EXHAUSTED_MARKER).exists()
    assert (state / _COUNT_FILE).read_text(encoding="utf-8").strip() == "2"
    assert _routes_to(run=run, plugins=plugins) == '{"preferred_next_label":"refresh_repair"}'
