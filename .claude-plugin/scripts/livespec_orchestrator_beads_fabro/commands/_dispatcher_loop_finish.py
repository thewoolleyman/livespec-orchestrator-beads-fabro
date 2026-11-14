"""Finish a launched dispatch with dispositions and review-gate evidence."""

from __future__ import annotations

import argparse
import contextlib
import time
from collections.abc import Callable
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_correlation import dispatch_correlation
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_terminal_span import (
    TerminalAttempt,
    emit_terminal_span,
    terminal_attempts,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = ["finish_dispatch"]


def _observed_attempts(
    *,
    plan: DispatchPlan,
    outcome: DispatchOutcome,
    token_supplier: Callable[[], str],
    terminal_at_ns: int,
) -> tuple[TerminalAttempt, ...] | None:
    """Return the run's attempts, ``()`` when no run was made, ``None`` when unreadable."""
    if outcome.fabro_run_id is None:
        return ()
    from livespec_orchestrator_beads_fabro.commands._fabro_port import fabro_port_for_plan

    try:
        events = fabro_port_for_plan(
            plan=plan,
            runner=GithubTokenEnvRunner(inner=ShellCommandRunner(), token=token_supplier),
        ).events(run_id=outcome.fabro_run_id, timeout_seconds=30.0)
        if events.command.exit_code != 0:
            return None
        return terminal_attempts(events_payload=events.payload, terminal_at_ns=terminal_at_ns)
    except (OSError, RuntimeError, TypeError, ValueError):
        return None


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
    terminal_at_ns = time.time_ns()
    # The terminal record is already durable before this best-effort telemetry
    # read.  A factory event-read or local append failure must never rewrite the
    # result a caller receives.
    with contextlib.suppress(OSError, RuntimeError, TypeError, ValueError):
        emit_terminal_span(
            correlation=dispatch_correlation(
                work_item_id=item.id,
                dispatch_id=identity.dispatch_id,
                factory=plan.fabro_factory_name,
            ),
            outcome=outcome,
            attempts=_observed_attempts(
                plan=plan,
                outcome=outcome,
                token_supplier=token_supplier,
                terminal_at_ns=terminal_at_ns,
            ),
            spans_path=spans,
            started_at_ns=terminal_at_ns,
            ended_at_ns=time.time_ns(),
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
