"""Flake work-item rendering and filing for a failed-jobs re-run."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_pr_view import GH_TIMEOUT_SECONDS

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
    from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan

__all__: list[str] = ["file_flake_item"]

_FLAKE_MARKER = "livespec-merge-poll-failed-jobs-rerun"


def file_flake_item(
    *,
    run_id: str,
    jobs: Iterable[tuple[str, str, tuple[str, ...]]],
    plan: DispatchPlan,
    runner: CommandRunner,
) -> str | None:
    """File the root-fix obligation; filing failure must not undo the rerun."""
    if not (plan.repo / ".beads").is_dir():
        return "beads pointer unavailable"
    result = runner.run(
        argv=[
            "bd",
            "create",
            "--type",
            "bug",
            "--title",
            f"Flake: failed jobs re-run {run_id}",
            "--description",
            _description(run_id=run_id, jobs=jobs),
        ],
        cwd=plan.repo,
        timeout_seconds=GH_TIMEOUT_SECONDS,
    )
    return None if result.exit_code == 0 else result.stderr


def _description(*, run_id: str, jobs: Iterable[tuple[str, str, tuple[str, ...]]]) -> str:
    lines = [_FLAKE_MARKER, f"workflow-run: {run_id}"]
    for name, kind, evidence in jobs:
        lines.extend(
            (f"job: {name}", f"class: {kind}", *(f"evidence: {item}" for item in evidence))
        )
    return "\n".join(lines)
