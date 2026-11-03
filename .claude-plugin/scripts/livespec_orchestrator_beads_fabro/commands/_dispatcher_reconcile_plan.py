"""Plan construction for the reconcile-merged valve."""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._config import resolve_fabro_bin
from livespec_orchestrator_beads_fabro.commands._dispatcher_default_branch import (
    resolve_default_branch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_selection import (
    livespec_config_text,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
    build_plan,
    janitor_reconcile_checkout_path,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = ["reconcile_plan"]


def reconcile_plan(
    *, repo: Path, item: WorkItem, janitor: tuple[str, ...] | None, runner: CommandRunner
) -> DispatchPlan:
    """Build the subset of a dispatch plan needed by the reconcile valve.

    It resolves the SAME contract a live dispatch would, from the same two
    sources, because it runs the same post-merge janitor at the same venue: a
    reconcile that resolved its own core pin or its own default branch could
    clean up somewhere the original dispatch never named.
    """
    return build_plan(
        repo=repo,
        work_item_id=item.id,
        workflow_toml=repo / "tmp" / f"reconcile-{item.id}-workflow.toml",
        goal_file=repo / "tmp" / f"reconcile-{item.id}-goal.md",
        fabro_bin=resolve_fabro_bin(cwd=repo),
        janitor=janitor,
        janitor_checkout=janitor_reconcile_checkout_path(repo=repo, work_item_id=item.id),
        config_text=livespec_config_text(repo=repo),
        default_branch=resolve_default_branch(repo=repo, runner=runner),
    )
