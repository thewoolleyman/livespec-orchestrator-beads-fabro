"""Tests for the Dispatcher's factory workflow-file boundary guard."""

from __future__ import annotations

import importlib
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_argv import (
    janitor_argv_with_default,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_goal import render_goal
from livespec_orchestrator_beads_fabro.types import WorkItem


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-test",
        type="task",
        status="ready",
        title="A ready task",
        description="Do the thing.",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-07-23T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


class RecordingRunner:
    def __init__(self, *, result: CommandResult) -> None:
        self.result = result
        self.calls: list[tuple[list[str], Path]] = []

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (timeout_seconds, env, stdin)
        self.calls.append((argv, cwd))
        return self.result


def test_render_goal_declares_factory_workflow_boundary(tmp_path: Path) -> None:
    goal = render_goal(item=_item(), repo=tmp_path, branch="feat/bd-ib-test")

    assert (
        "Factory branches never create/update files under .github/workflows/. "
        "When an implementation legitimately needs a workflow change, restore "
        "that file to master's content, publish the rest, and report the "
        "dropped unified diff for maintainer-side landing."
    ) in goal


def test_workflow_guard_module_exists_before_import() -> None:
    module_path = (
        Path(".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands")
        / "_dispatcher_workflow_guard.py"
    )
    assert module_path.is_file()


def test_workflow_guard_fails_with_carve_out_hint(tmp_path: Path) -> None:
    guard = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_workflow_guard"
    )
    runner = RecordingRunner(
        result=CommandResult(
            exit_code=0,
            stdout=".github/workflows/ci.yml\nsrc/app.py\n",
            stderr="",
        )
    )

    result = guard.check_no_workflow_changes(repo=tmp_path, runner=runner)

    assert result.exit_code == 1
    assert ".github/workflows/ci.yml" in result.message
    assert "restore that file to master's content" in result.message
    assert "publish the rest" in result.message
    assert "dropped unified diff" in result.message
    assert runner.calls == [(["git", "diff", "--name-only", "origin/master...HEAD"], tmp_path)]


def test_workflow_guard_allows_non_workflow_paths(tmp_path: Path) -> None:
    guard = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_workflow_guard"
    )
    runner = RecordingRunner(
        result=CommandResult(
            exit_code=0,
            stdout=".github/actions/build/action.yml\nsrc/app.py\n",
            stderr="",
        )
    )

    result = guard.check_no_workflow_changes(repo=tmp_path, runner=runner)

    assert result.exit_code == 0
    assert result.message == "No .github/workflows/ changes detected."


def test_workflow_guard_reports_git_diff_failure(tmp_path: Path) -> None:
    guard = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_workflow_guard"
    )
    runner = RecordingRunner(
        result=CommandResult(exit_code=128, stdout="", stderr="fatal: no merge base")
    )

    result = guard.check_no_workflow_changes(repo=tmp_path, runner=runner)

    assert result.exit_code == 2
    assert "could not inspect" in result.message
    assert "fatal: no merge base" in result.message


def test_default_janitor_runs_workflow_guard_before_full_check() -> None:
    assert janitor_argv_with_default(janitor=None) == (
        "mise",
        "exec",
        "--",
        "just",
        "check-no-workflow-edits",
        "check",
    )
