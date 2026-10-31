"""Finish a launched dispatch with dispositions and review-gate evidence."""

from __future__ import annotations

import argparse
import time
from collections.abc import Callable
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_id_journal import (
    DispatchJournalIdentity,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    GithubTokenEnvRunner,
    JournalFile,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._dispatcher_review_gate import (
    ReviewGateEmission,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = ["finish_dispatch"]


def finish_dispatch(  # noqa: PLR0913 -- each post-launch value is independently produced before disposition.
    *,
    args: argparse.Namespace,
    repo: Path,
    item: WorkItem,
    journal: JournalFile,
    plan: DispatchPlan,
    outcome: DispatchOutcome,
    started_at: float,
    goal_text: str,
    token_supplier: Callable[[], str],
    identity: DispatchJournalIdentity,
    spans: Path,
    dispose: Callable[..., DispatchOutcome],
    emit_review: Callable[..., None],
) -> DispatchOutcome:
    """Apply the terminal disposition and emit its review-gate observation."""
    outcome = dispose(
        args=args,
        repo=repo,
        item=item,
        outcome=outcome,
        journal=journal,
        wall_clock_seconds=time.monotonic() - started_at,
        dispatch_context_size=len(goal_text),
        token_supplier=token_supplier,
    )
    emit_review(
        emission=ReviewGateEmission(
            plan=plan,
            runner=GithubTokenEnvRunner(inner=ShellCommandRunner(), token=token_supplier),
            journal=journal,
            spans_path=spans,
            work_item_id=item.id,
            dispatch_id=identity.dispatch_id,
            run_id=outcome.fabro_run_id,
            dispatch_factory=identity.dispatch_factory,
        )
    )
    return outcome
