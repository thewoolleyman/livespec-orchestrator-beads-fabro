"""Factory-branch guard for GitHub workflow file changes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner

__all__: list[str] = [
    "FACTORY_WORKFLOW_BOUNDARY_TEXT",
    "WorkflowGuardResult",
    "check_no_workflow_changes",
]

FACTORY_WORKFLOW_BOUNDARY_TEXT = (
    "Factory branches never create/update files under .github/workflows/. "
    "When an implementation legitimately needs a workflow change, restore "
    "that file to master's content, publish the rest, and report the "
    "dropped unified diff for maintainer-side landing."
)
_WORKFLOWS_PREFIX = ".github/workflows/"
_DIFF_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True, kw_only=True)
class WorkflowGuardResult:
    """Outcome of the workflow-file boundary inspection."""

    exit_code: int
    message: str


def check_no_workflow_changes(
    *,
    repo: Path,
    runner: CommandRunner,
) -> WorkflowGuardResult:
    """Fail when the branch diff vs origin/master touches workflow files."""
    diff = runner.run(
        argv=["git", "diff", "--name-only", "origin/master...HEAD"],
        cwd=repo,
        timeout_seconds=_DIFF_TIMEOUT_SECONDS,
    )
    if diff.exit_code != 0:
        detail = diff.stderr.strip() or diff.stdout.strip() or "git diff failed"
        return WorkflowGuardResult(
            exit_code=2,
            message=f"workflow guard could not inspect origin/master...HEAD: {detail}",
        )
    workflow_paths = _workflow_paths(diff_names=diff.stdout)
    if not workflow_paths:
        return WorkflowGuardResult(
            exit_code=0,
            message="No .github/workflows/ changes detected.",
        )
    return WorkflowGuardResult(
        exit_code=1,
        message=(
            "Factory branch diff touches .github/workflows/, which is out of bounds:\n"
            f"{_format_paths(paths=workflow_paths)}\n\n"
            f"{FACTORY_WORKFLOW_BOUNDARY_TEXT}"
        ),
    )


def _workflow_paths(*, diff_names: str) -> tuple[str, ...]:
    return tuple(
        path
        for path in (line.strip() for line in diff_names.splitlines())
        if path.startswith(_WORKFLOWS_PREFIX)
    )


def _format_paths(*, paths: tuple[str, ...]) -> str:
    return "\n".join(f"- {path}" for path in paths)
