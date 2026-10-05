"""Per-item dispatch: hold the lock, launch what was prepared, dispose of the outcome.

The PREPARATION — every pre-run refusal stage, from the ledger read through the
run-config overlay to the written goal — lives in `_dispatcher_loop_launch`,
which was split out of this module by cohesion. What is left here is the other
concern: the per-item dispatch lock that makes a claim visible to a concurrent
drain, the watchdogged run itself, and the post-run dispositions that decide what
the dispatch RESULT reports.
"""

from __future__ import annotations

import argparse
import time
from contextlib import ExitStack
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_id_journal import (
    DispatchJournalIdentity,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_lock import (
    dispatch_lock_path,
    live_dispatch_lock,
    release_dispatch_lock,
    write_dispatch_lock,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    DispatchOutcome,
    run_dispatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    GithubTokenEnvRunner,
    JournalFile,
    ShellCommandRunner,
    WatchedFabroLauncher,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_launch import prepare_launch
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_run import (
    DispatchRunContext,
    run_dispatch_with_watchdog,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_selection import (
    post_run_dispositions,
    run_id,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import (
    spans_path,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_pre_run_claim import (
    release_pre_run_claim_if_needed,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_review_gate import (
    ReviewGateEmission,
    emit_review_gate_from_fabro_events,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "dispatch_one",
]


def dispatch_one(
    *,
    args: argparse.Namespace,
    repo: Path,
    item: WorkItem,
    journal: JournalFile,
    janitor: tuple[str, ...] | None,
) -> DispatchOutcome:
    raw_factory_target = getattr(args, "fabro_factory_target", None)
    dispatch_factory = (
        raw_factory_target.name if isinstance(raw_factory_target, FactoryTarget) else None
    )
    if not isinstance(raw_factory_target, FactoryTarget):
        args.fabro_factory_target = FactoryTarget(name="default", server=None, dev_token=None)
    lock = live_dispatch_lock(repo=repo, work_item_id=item.id)
    if lock is None or lock.dispatch_id is None:
        dispatch_id = run_id()
        lock_path = write_dispatch_lock(repo=repo, work_item_id=item.id, dispatch_id=dispatch_id)
    else:
        dispatch_id = lock.dispatch_id
        lock_path = dispatch_lock_path(repo=repo, work_item_id=item.id)
    with ExitStack() as stack:
        _ = stack.callback(lambda: release_dispatch_lock(path=lock_path))
        outcome = _dispatch_one_locked(
            args=args,
            repo=repo,
            item=item,
            journal=journal,
            janitor=janitor,
            identity=DispatchJournalIdentity(
                dispatch_id=dispatch_id,
                dispatch_factory=dispatch_factory,
            ),
        )
        release_pre_run_claim_if_needed(repo=repo, item=item, outcome=outcome, journal=journal)
        return outcome


def _dispatch_one_locked(
    *,
    args: argparse.Namespace,
    repo: Path,
    item: WorkItem,
    journal: JournalFile,
    janitor: tuple[str, ...] | None,
    identity: DispatchJournalIdentity,
) -> DispatchOutcome:
    prepared = prepare_launch(
        args=args,
        repo=repo,
        item=item,
        journal=journal,
        janitor=janitor,
        identity=identity,
    )
    # A refusal arrives already journaled at its own stage and is terminal, so it
    # IS the dispatch result. The two-type rail is what keeps the six refusal
    # stages out of this function rather than six returns deep in it.
    if isinstance(prepared, DispatchOutcome):
        return prepared
    started_at, outcome = run_dispatch_with_watchdog(
        context=DispatchRunContext(
            args=args,
            repo=repo,
            plan=prepared.plan,
            journal=journal,
            overlay_file=prepared.overlay_file,
            payload_dir=prepared.payload_dir,
            token_supplier=prepared.token_supplier,
            dispatch_id=identity.dispatch_id,
        ),
        run_dispatch_func=run_dispatch,
        fabro_launcher_type=WatchedFabroLauncher,
    )
    # REBOUND, not merely called: the post-merge acceptance valve runs inside, and
    # the outcome it returns is the one the dispatch RESULT must report — a park
    # reported as the janitor's own `green at done` is finding F7(b).
    outcome = post_run_dispositions(
        args=args,
        repo=repo,
        item=item,
        outcome=outcome,
        journal=journal,
        wall_clock_seconds=time.monotonic() - started_at,
        dispatch_context_size=len(prepared.goal_text),
        token_supplier=prepared.token_supplier,
    )
    emit_review_gate_from_fabro_events(
        emission=ReviewGateEmission(
            plan=prepared.plan,
            runner=GithubTokenEnvRunner(inner=ShellCommandRunner(), token=prepared.token_supplier),
            journal=journal,
            spans_path=spans_path(args=args, repo=repo),
            work_item_id=item.id,
            dispatch_id=identity.dispatch_id,
            run_id=outcome.fabro_run_id,
            dispatch_factory=identity.dispatch_factory,
        )
    )
    return outcome
