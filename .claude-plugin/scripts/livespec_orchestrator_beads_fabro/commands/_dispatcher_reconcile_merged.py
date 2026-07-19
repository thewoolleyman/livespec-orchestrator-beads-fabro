"""Operator valve for reconciling already-merged active items."""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    EXIT_FAILURE,
    EXIT_PRECONDITION_ERROR,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_completion import (
    complete_and_accept,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandRunner,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_janitor import post_merge
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_journal import run_stage
from livespec_orchestrator_beads_fabro.commands._dispatcher_heartbeat_probe import (
    HeartbeatLivenessProbe,
    LayeredLivenessProbe,
    heartbeat_lookup_keys,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_close import (
    emit_outcomes,
    load_items,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_selection import (
    janitor_core_ref,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_otel_wiring import parse_janitor
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import (
    heartbeat_path,
    journal_path,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
    PrView,
    build_plan,
    janitor_checkout_path,
    parse_pr_view,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_watchdog import (
    LivenessSample,
    resolve_stall_seconds,
)
from livespec_orchestrator_beads_fabro.commands._otel_receive import HeartbeatSink
from livespec_orchestrator_beads_fabro.effects import JsonParseFailure, parse_json
from livespec_orchestrator_beads_fabro.io import write_stderr
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "merged_pr_list_argv",
    "parse_merged_pr_list",
    "reconcile_plan",
    "run_reconcile_merged_command",
]

_GH_TIMEOUT_SECONDS = 120.0


def run_reconcile_merged_command(
    *, args: argparse.Namespace, runner: CommandRunner | None = None
) -> int:
    """Run the post-merge janitor + acceptance valve for a stranded active item."""
    repo = Path(args.repo)
    preflight = _reconcile_preflight(args=args, repo=repo)
    if isinstance(preflight, int):
        return preflight
    item = preflight.item
    janitor = preflight.janitor
    command_runner = ShellCommandRunner() if runner is None else runner
    journal = JournalFile(path=journal_path(args=args, repo=repo))
    plan = reconcile_plan(repo=repo, item=item, janitor=janitor)
    merged = _resolve_merged_pr(plan=plan, item=item, runner=command_runner, journal=journal)
    if merged is None:
        _ = write_stderr(text=f"ERROR: no merged PR found for active work-item {item.id}\n")
        return EXIT_PRECONDITION_ERROR
    outcome = post_merge(
        outcome_type=DispatchOutcome,
        plan=plan,
        runner=command_runner,
        journal=journal,
        merged=merged,
    )
    if outcome.status == "green" and outcome.stage == "done":
        complete_and_accept(repo=repo, item=item, outcome=outcome, journal=journal)
    journal.append(record={"stage": "outcome", "outcome": _outcome_payload(outcome=outcome)})
    emit_outcomes(outcomes=[outcome], as_json=args.as_json)
    return 0 if outcome.status == "green" and outcome.stage == "done" else EXIT_FAILURE


@dataclass(frozen=True, kw_only=True)
class _ReconcilePreflight:
    item: WorkItem
    janitor: tuple[str, ...] | None


def _reconcile_preflight(*, args: argparse.Namespace, repo: Path) -> _ReconcilePreflight | int:
    if not repo.exists():
        _ = write_stderr(text="ERROR: --repo does not exist\n")
        return EXIT_PRECONDITION_ERROR
    items = {item.id: item for item in load_items(repo=repo)}
    item = items.get(args.item)
    if item is None:
        _ = write_stderr(text=f"ERROR: work-item {args.item} not found\n")
        return EXIT_PRECONDITION_ERROR
    if item.status != "active":
        detail = f"ERROR: reconcile-merged expected active item {item.id}; found {item.status}\n"
        _ = write_stderr(text=detail)
        return EXIT_PRECONDITION_ERROR
    janitor, janitor_ok = parse_janitor(raw=args.janitor)
    if not janitor_ok:
        return 2
    if not args.force:
        live_detail = _live_dispatch_refusal(args=args, repo=repo, item=item)
        if live_detail is not None:
            _ = write_stderr(text=live_detail)
            return EXIT_PRECONDITION_ERROR
    return _ReconcilePreflight(item=item, janitor=janitor)


@dataclass(frozen=True, kw_only=True)
class _NoSignalLivenessProbe:
    def sample(self, *, observed_at: float) -> LivenessSample:
        return LivenessSample(last_event_epoch=None, observed_at=observed_at)


def _live_dispatch_refusal(*, args: argparse.Namespace, repo: Path, item: WorkItem) -> str | None:
    observed_at = time.time()
    heartbeat = HeartbeatLivenessProbe(
        sink=HeartbeatSink(path=heartbeat_path(args=args, repo=repo)),
        keys=heartbeat_lookup_keys(work_item_id=item.id, run_id=None),
    )
    probe = LayeredLivenessProbe(primary=heartbeat, fallback=_NoSignalLivenessProbe())
    sample = probe.sample(observed_at=observed_at)
    if sample.last_event_epoch is None:
        return None
    age_seconds = sample.observed_at - sample.last_event_epoch
    if age_seconds > resolve_stall_seconds():
        return None
    return (
        f"ERROR: reconcile-merged refused: live dispatch still appears active for "
        f"work-item {item.id} (recent heartbeat age {age_seconds:.1f}s). "
        f"Confirm with `fabro ps`, wait for the janitor window to close, or rerun "
        f"with --force only after confirming the original dispatcher process is dead.\n"
    )


def reconcile_plan(*, repo: Path, item: WorkItem, janitor: tuple[str, ...] | None) -> DispatchPlan:
    """Build the subset of a dispatch plan needed by the reconcile valve."""
    return build_plan(
        repo=repo,
        work_item_id=item.id,
        workflow_toml=repo / "tmp" / f"reconcile-{item.id}-workflow.toml",
        goal_file=repo / "tmp" / f"reconcile-{item.id}-goal.md",
        fabro_bin="fabro",
        janitor=janitor,
        janitor_checkout=janitor_checkout_path(repo=repo, work_item_id=item.id),
        janitor_core_ref=janitor_core_ref(repo=repo),
    )


def merged_pr_list_argv(*, item: WorkItem) -> list[str]:
    """Build the GitHub search argv used when branch lookup is unavailable."""
    return [
        "gh",
        "pr",
        "list",
        "--state",
        "merged",
        "--search",
        item.id,
        "--json",
        "number,title,headRefName,state,mergeCommit",
        "--limit",
        "20",
    ]


def parse_merged_pr_list(*, stdout: str, item: WorkItem, branch: str) -> tuple[PrView, ...]:
    """Parse merged PR search results, accepting either branch or title/id matches."""
    parsed_raw = parse_json(text=stdout)
    if isinstance(parsed_raw, JsonParseFailure) or not isinstance(parsed_raw, list):
        return ()
    matches: list[PrView] = []
    for entry_raw in cast("list[object]", parsed_raw):
        view = _pr_view_from_list_entry(entry_raw=entry_raw, item=item, branch=branch)
        if view is not None:
            matches.append(view)
    return tuple(matches)


def _resolve_merged_pr(
    *, plan: DispatchPlan, item: WorkItem, runner: CommandRunner, journal: JournalFile
) -> PrView | None:
    viewed = run_stage(
        runner=runner,
        journal=journal,
        plan=plan,
        stage="reconcile-pr-view-branch",
        command=(_pr_view_branch_argv(plan=plan), plan.repo, _GH_TIMEOUT_SECONDS, None),
    )
    if viewed.exit_code == 0:
        return _merged_pr_view(stdout=viewed.stdout)
    searched = run_stage(
        runner=runner,
        journal=journal,
        plan=plan,
        stage="reconcile-pr-list-merged",
        command=(merged_pr_list_argv(item=item), plan.repo, _GH_TIMEOUT_SECONDS, None),
    )
    for candidate in parse_merged_pr_list(stdout=searched.stdout, item=item, branch=plan.branch):
        return candidate
    return None


def _pr_view_branch_argv(*, plan: DispatchPlan) -> list[str]:
    return [
        "gh",
        "pr",
        "view",
        plan.branch,
        "--json",
        "number,state,autoMergeRequest,mergeStateStatus,mergeCommit,statusCheckRollup",
    ]


def _merged_pr_view(*, stdout: str) -> PrView | None:
    view = parse_pr_view(stdout=stdout)
    if view is None or view.state != "MERGED" or view.merge_sha is None:
        return None  # pragma: no cover - defensive malformed gh JSON
    return view


def _pr_view_from_list_entry(*, entry_raw: object, item: WorkItem, branch: str) -> PrView | None:
    if not isinstance(entry_raw, dict):
        return None
    entry = cast("dict[str, Any]", entry_raw)
    number_raw: object = entry.get("number")
    state_raw: object = entry.get("state")
    if not isinstance(number_raw, int) or state_raw != "MERGED":
        return None
    title_raw: object = entry.get("title")
    head_raw: object = entry.get("headRefName")
    if head_raw != branch and not (isinstance(title_raw, str) and item.id in title_raw):
        return None
    merge_sha = _list_entry_merge_sha(entry=entry)
    if merge_sha is None:
        return None
    return PrView(
        number=number_raw,
        state="MERGED",
        auto_merge_armed=False,
        merge_state_status="UNKNOWN",
        merge_sha=merge_sha,
        terminal_required_check_failures=(),
    )


def _list_entry_merge_sha(*, entry: dict[str, Any]) -> str | None:
    commit_raw: object = entry.get("mergeCommit")
    if not isinstance(commit_raw, dict):
        return None  # pragma: no cover - defensive malformed gh JSON
    oid_raw: object = cast("dict[str, Any]", commit_raw).get("oid")
    return oid_raw if isinstance(oid_raw, str) and oid_raw else None


def _outcome_payload(*, outcome: DispatchOutcome) -> dict[str, object]:
    return {
        "work_item_id": outcome.work_item_id,
        "status": outcome.status,
        "stage": outcome.stage,
        "pr_number": outcome.pr_number,
        "merge_sha": outcome.merge_sha,
        "detail": outcome.detail,
        "fabro_run_id": outcome.fabro_run_id,
    }
