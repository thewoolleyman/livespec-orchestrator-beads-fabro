"""Tests for the Dispatcher's factory workflow-file boundary guard."""

from __future__ import annotations

import importlib
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_check_suite_view import (
    janitor_check_suite_from_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_argv import janitor_argv
from livespec_orchestrator_beads_fabro.commands._dispatcher_goal import render_goal
from livespec_orchestrator_beads_fabro.types import WorkItem

_GUARD_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_workflow_guard"
_ORIGIN_HEAD_ARGV = ["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"]
_REPO_VIEW_ARGV = [
    "gh",
    "repo",
    "view",
    "--json",
    "defaultBranchRef",
    "--jq",
    ".defaultBranchRef.name",
]
_SILENT = CommandResult(exit_code=1, stdout="", stderr="not a git repository")


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
    """A runner that answers each of the guard's three possible reads separately.

    The guard now asks a repository what its default branch is BEFORE it asks
    for a diff, so a stub that returned one canned result for every call would
    feed the diff's answer back as a branch name and prove nothing about which
    range was taken.
    """

    def __init__(
        self,
        *,
        result: CommandResult,
        origin_head: CommandResult | None = None,
        repo_view: CommandResult | None = None,
    ) -> None:
        self.result = result
        self.origin_head = origin_head or CommandResult(
            exit_code=0, stdout="origin/master\n", stderr=""
        )
        self.repo_view = repo_view or _SILENT
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
        if argv == _ORIGIN_HEAD_ARGV:
            return self.origin_head
        if argv == _REPO_VIEW_ARGV:
            return self.repo_view
        return self.result


def test_render_goal_declares_factory_workflow_boundary(tmp_path: Path) -> None:
    goal = render_goal(item=_item(), repo=tmp_path, branch="feat/bd-ib-test")

    assert (
        "Factory branches never create/update files under .github/workflows/. "
        "When an implementation needs a workflow change, leave every file "
        "under .github/workflows/ unchanged and report in your final message "
        "that the workflow change routes to the attended host session. A "
        "workflow change lands through the declared workflow-edit route, "
        "under which such an item is refused before dispatch and carried by "
        "the attended host session."
    ) in goal
    assert "maintainer-side landing" not in goal


def test_workflow_guard_module_exists_before_import() -> None:
    module_path = (
        Path(".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands")
        / "_dispatcher_workflow_guard.py"
    )
    assert module_path.is_file()


def test_workflow_guard_fails_with_carve_out_hint(tmp_path: Path) -> None:
    guard = importlib.import_module(_GUARD_MODULE)
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
    assert "leave every file under .github/workflows/ unchanged" in result.message
    assert "routes to the attended host session" in result.message
    assert "declared workflow-edit route" in result.message
    assert "dropped unified diff" not in result.message
    assert runner.calls == [
        (_ORIGIN_HEAD_ARGV, tmp_path),
        (["git", "diff", "--name-only", "origin/master...HEAD"], tmp_path),
    ]


def test_workflow_guard_diffs_against_a_resolved_non_master_default_branch(tmp_path: Path) -> None:
    """An adopter whose primary branch is `main` is judged on ITS range, not master's."""
    guard = importlib.import_module(_GUARD_MODULE)
    runner = RecordingRunner(
        result=CommandResult(exit_code=0, stdout=".github/workflows/ci.yml\n", stderr=""),
        origin_head=CommandResult(exit_code=0, stdout="origin/main\n", stderr=""),
    )

    result = guard.check_no_workflow_changes(repo=tmp_path, runner=runner)

    assert (["git", "diff", "--name-only", "origin/main...HEAD"], tmp_path) in runner.calls
    # The retired literal is gone, not merely shadowed: no read names it at all.
    assert all("origin/master...HEAD" not in " ".join(argv) for argv, _ in runner.calls)
    assert result.exit_code == 1
    assert result.outcome == "fail"


def test_workflow_guard_falls_back_to_the_forge_when_git_cannot_name_the_branch(
    tmp_path: Path,
) -> None:
    guard = importlib.import_module(_GUARD_MODULE)
    runner = RecordingRunner(
        result=CommandResult(exit_code=0, stdout="src/app.py\n", stderr=""),
        origin_head=_SILENT,
        repo_view=CommandResult(exit_code=0, stdout="trunk\n", stderr=""),
    )

    result = guard.check_no_workflow_changes(repo=tmp_path, runner=runner)

    assert (["git", "diff", "--name-only", "origin/trunk...HEAD"], tmp_path) in runner.calls
    assert result.exit_code == 0
    assert result.outcome == "vacuous-match"


def test_workflow_guard_refuses_when_no_route_can_name_the_default_branch(tmp_path: Path) -> None:
    guard = importlib.import_module(_GUARD_MODULE)
    runner = RecordingRunner(
        result=CommandResult(exit_code=0, stdout="src/app.py\n", stderr=""),
        origin_head=_SILENT,
        repo_view=_SILENT,
    )

    result = guard.check_no_workflow_changes(repo=tmp_path, runner=runner)

    # No range could be named, so no diff was taken: unobservable, never a pass
    # and never a vacuous match.
    assert result.exit_code == 2
    assert result.outcome is None
    assert "could not resolve the target's default branch" in result.message
    assert all(argv[:2] != ["git", "diff"] for argv, _ in runner.calls)


def test_workflow_guard_allows_non_workflow_paths(tmp_path: Path) -> None:
    guard = importlib.import_module(_GUARD_MODULE)
    runner = RecordingRunner(
        result=CommandResult(
            exit_code=0,
            stdout=".github/actions/build/action.yml\nsrc/app.py\n",
            stderr="",
        )
    )

    result = guard.check_no_workflow_changes(repo=tmp_path, runner=runner)

    # Not blocked (the boundary is intact), but not a pass either: the scope
    # matched zero of the two judged files, so the check observed nothing.
    assert result.exit_code == 0
    assert result.outcome == "vacuous-match"
    assert "matched zero of the 2 file(s)" in result.message


def test_workflow_guard_reports_git_diff_failure(tmp_path: Path) -> None:
    guard = importlib.import_module(_GUARD_MODULE)
    runner = RecordingRunner(
        result=CommandResult(exit_code=128, stdout="", stderr="fatal: no merge base")
    )

    result = guard.check_no_workflow_changes(repo=tmp_path, runner=runner)

    assert result.exit_code == 2
    # The refusal names the range it actually took, which is now a resolved one.
    assert "could not inspect origin/master...HEAD" in result.message
    assert "fatal: no merge base" in result.message


def test_default_janitor_runs_workflow_guard_before_full_check() -> None:
    assert janitor_argv(check_suite=janitor_check_suite_from_block(block={}, janitor=None)) == (
        "mise",
        "exec",
        "--",
        "just",
        "check-no-workflow-edits",
        "install-worktree-pack",
        "check",
    )
