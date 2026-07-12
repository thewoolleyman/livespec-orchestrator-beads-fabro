"""Dispatch-loop candidate selection and per-item launch primitives."""

from __future__ import annotations

import argparse
import tempfile
import time
from dataclasses import asdict
from pathlib import Path
from time import sleep as _real_sleep

from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_self_update as selfup,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_completion import (
    warn_item_sizing,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credentials import (
    materialize_overlay,
    read_dispatch_comments,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    DispatchOutcome,
    PollPolicy,
    run_dispatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    GithubTokenEnvRunner,
    JournalFile,
    ShellCommandRunner,
    WatchedFabroLauncher,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_lessons import (
    read_ratified_lessons,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_selection import (
    candidates,
    is_dispatch_candidate,
    janitor_core_ref,
    post_run_dispositions,
    prepare,
    ready_items,
    run_id,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import (
    heartbeat_path,
    workflow_toml,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    build_plan,
    janitor_checkout_path,
    render_goal,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "candidates",
    "dispatch_one",
    "is_dispatch_candidate",
    "janitor_core_ref",
    "post_run_dispositions",
    "prepare",
    "ready_items",
    "run_id",
]


def dispatch_one(
    *,
    args: argparse.Namespace,
    repo: Path,
    item: WorkItem,
    journal: JournalFile,
    janitor: tuple[str, ...] | None,
) -> DispatchOutcome:
    goal_file = Path(tempfile.gettempdir()) / f"fabro-goal-{item.id}.md"
    overlay_file = Path(tempfile.gettempdir()) / f"fabro-run-config-{item.id}.toml"
    janitor_checkout = janitor_checkout_path(repo=repo, work_item_id=item.id)
    plan = build_plan(
        repo=repo,
        work_item_id=item.id,
        workflow_toml=overlay_file,
        goal_file=goal_file,
        fabro_bin=args.fabro_bin,
        janitor=janitor,
        janitor_checkout=janitor_checkout,
        janitor_core_ref=janitor_core_ref(repo=repo),
    )
    warn_item_sizing(item=item, journal=journal)
    comments = read_dispatch_comments(repo=repo, item=item)
    if isinstance(comments, str):
        outcome = DispatchOutcome(
            work_item_id=item.id,
            status="failed",
            stage="ledger-comments",
            pr_number=None,
            merge_sha=None,
            detail=comments,
        )
        journal.append(record={"stage": "outcome", "outcome": asdict(outcome)})
        return outcome
    dispatch_id = run_id()
    journal.append(
        record={"stage": "dispatch-id", "work_item_id": item.id, "dispatch_id": dispatch_id}
    )
    token_supplier = selfup.github_token_supplier()
    if isinstance(token_supplier, str):
        outcome = DispatchOutcome(
            work_item_id=item.id,
            status="failed",
            stage="github-app-auth",
            pr_number=None,
            merge_sha=None,
            detail=token_supplier,
        )
        journal.append(record={"stage": "outcome", "outcome": asdict(outcome)})
        return outcome
    overlay_error = materialize_overlay(
        committed=workflow_toml(args=args),
        overlay=overlay_file,
        repo=repo,
        work_item_id=item.id,
        dispatch_id=dispatch_id,
        token=token_supplier,
    )
    if overlay_error is not None:
        outcome = DispatchOutcome(
            work_item_id=item.id,
            status="failed",
            stage="run-config-overlay",
            pr_number=None,
            merge_sha=None,
            detail=overlay_error,
        )
        journal.append(record={"stage": "outcome", "outcome": asdict(outcome)})
        return outcome
    # Lessons are read host-side from `repo` (the dispatcher's operative
    # checkout, where the reflector maintains loop-reflection-gate/lessons.md),
    # exactly like `comments` above; only committed content is read, so an
    # unmerged reflector proposal never influences a brief.
    lessons = read_ratified_lessons(lessons_root=repo)
    goal_text = render_goal(
        item=item, repo=repo, branch=plan.branch, comments=comments, lessons=lessons
    )
    _ = goal_file.write_text(goal_text, encoding="utf-8")
    started_at = time.monotonic()
    try:
        outcome = run_dispatch(
            plan=plan,
            # Pillar 1 (first-class remint): the decorator re-resolves
            # GH_TOKEN from the caching provider before EVERY engine
            # subprocess, so the ~76-min merge-poll and the post-merge
            # git/janitor legs never ride an expired once-at-start token.
            runner=GithubTokenEnvRunner(inner=ShellCommandRunner(), token=token_supplier),
            journal=journal,
            sleep=_real_sleep,
            poll=PollPolicy(
                attempts=args.poll_attempts,
                interval_seconds=args.poll_interval_seconds,
            ),
            # The progress watchdog (work-item livespec-impl-beads-oyg):
            # runs `fabro run` while watching liveness and `fabro rm -f`-es
            # a sustained-no-progress stall (the 7us.6 silent-deadlock
            # backstop) — a distinct `stalled-no-progress` outcome that
            # h1p's `notify_terminal` alarms on. 29f.6 layers the
            # metrics-HEARTBEAT (the journal-sibling file the live receiver
            # writes) as the deferred-PRIMARY liveness signal over the
            # coarse wall-clock backstop; an absent/stale/malformed
            # heartbeat degrades to the wall-clock layer, never to NO
            # detection.
            fabro_launcher=WatchedFabroLauncher(
                heartbeat_path=heartbeat_path(args=args, repo=repo),
            ),
        )
    finally:
        overlay_file.unlink(missing_ok=True)
    post_run_dispositions(
        args=args,
        repo=repo,
        item=item,
        outcome=outcome,
        journal=journal,
        wall_clock_seconds=time.monotonic() - started_at,
        dispatch_context_size=len(goal_text),
        token_supplier=token_supplier,
    )
    return outcome
