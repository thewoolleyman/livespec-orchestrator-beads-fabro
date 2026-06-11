"""Dispatch engine: sequence one work-item through the Fabro Loop.

The engine owns the per-item lifecycle the family discipline prescribes
(livespec non-functional-requirements.md §"Orchestrator-internal
Dispatcher guidance", Architecture C shape per
livespec/tmp/fabro-architecture-c-design.md):

  Fabro run from the target repo's PRIMARY checkout (Fabro clones fresh
  inside its docker sandbox and the phase graph does
  implement/janitor/PR — the host owns no git working state, so there
  is no worktree prep and no reaping) -> blocked-state check (`fabro
  inspect`) -> confirm auto-merge armed (arming as fallback when the
  graph could not) -> poll until the PR is MERGED -> refresh the
  primary -> post-merge janitor hard gate -> report.

Three terminal states (livespec-impl-beads-4zl): `green` (merged,
post-merge janitor green), `failed` (an expected failure at a named
stage), and `blocked` — the run parked at the phase graph's in-loop
human gate (Fabro's native blocked status; the foreground `fabro run`
returns and the slot frees while a server-side engine holds the run).
Blocked is NOT a failure: the item stays open, nothing is closed, and
the human answers via `fabro attach <run-id>` (`fabro resume` only
when the engine died) — the Dispatcher never auto-resumes.

All side effects flow through the injected `CommandRunner` /
`JournalWriter` / `SleepFn` seams so the hermetic test tier drives every
branch without real subprocesses. Expected failures are DATA (a
`DispatchOutcome` with `status="failed"` naming the stage), never raised:
the loop layer must survive one item's failure and keep its budget
accounting.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from livespec_impl_beads.commands._dispatcher_plan import (
    DispatchPlan,
    PrView,
    fabro_inspect_argv,
    fabro_run_argv,
    parse_pr_view,
    parse_run_id,
    parse_run_status,
    pr_arm_argv,
    pr_update_branch_argv,
    pr_view_argv,
    pull_primary_argv,
)

__all__: list[str] = [
    "CommandResult",
    "CommandRunner",
    "DispatchOutcome",
    "JournalWriter",
    "PollPolicy",
    "SleepFn",
    "run_dispatch",
]

_GIT_TIMEOUT_SECONDS = 600.0
_FABRO_TIMEOUT_SECONDS = 14400.0
_FABRO_INSPECT_TIMEOUT_SECONDS = 300.0
_GH_TIMEOUT_SECONDS = 300.0
_JANITOR_TIMEOUT_SECONDS = 3600.0

SleepFn = Callable[[float], None]


class JournalWriter(Protocol):
    """Append-one-record seam for the structured iteration journal."""

    def append(self, *, record: dict[str, object]) -> None:
        """Persist one journal record."""
        ...


@dataclass(frozen=True, kw_only=True)
class CommandResult:
    """Outcome of one subprocess invocation across the runner seam."""

    exit_code: int
    stdout: str
    stderr: str


class CommandRunner(Protocol):
    """The single subprocess seam the engine executes argvs through."""

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
    ) -> CommandResult:
        """Run argv in cwd, returning the completed result (never raising
        for non-zero exits; timeouts surface as non-zero results)."""
        ...


@dataclass(frozen=True, kw_only=True)
class PollPolicy:
    """Bounded merge-confirmation polling (an unbounded loop is a defect)."""

    attempts: int
    interval_seconds: float


@dataclass(frozen=True, kw_only=True)
class DispatchOutcome:
    """Terminal report for one dispatched work-item.

    `status` is one of `green` / `failed` / `blocked` (blocked = the run
    parked at the in-loop human gate; surfaced to the operator, never
    treated as a failure, never auto-resumed).
    """

    work_item_id: str
    status: str
    stage: str
    pr_number: int | None
    merge_sha: str | None
    detail: str


def run_dispatch(
    *,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    sleep: SleepFn,
    poll: PollPolicy,
) -> DispatchOutcome:
    """Drive one work-item end-to-end; never raises for expected failures."""
    fabro = runner.run(
        argv=fabro_run_argv(plan=plan),
        cwd=plan.repo,
        timeout_seconds=_FABRO_TIMEOUT_SECONDS,
    )
    _journal_stage(journal=journal, plan=plan, stage="fabro-run", result=fabro)
    blocked = _blocked_outcome(plan=plan, runner=runner, journal=journal, fabro=fabro)
    if blocked is not None:
        return blocked
    if fabro.exit_code != 0:
        return _failed(plan=plan, stage="fabro-run", detail=_tail(text=fabro.stderr))
    view = _confirm_pr(plan=plan, runner=runner, journal=journal)
    if view is None:
        return _failed(plan=plan, stage="pr-view", detail="no PR found for branch")
    merged = _await_merge(plan=plan, runner=runner, journal=journal, sleep=sleep, poll=poll)
    if merged is None:
        return DispatchOutcome(
            work_item_id=plan.work_item_id,
            status="failed",
            stage="merge-poll",
            pr_number=view.number,
            merge_sha=None,
            detail="PR did not reach MERGED within the poll budget",
        )
    return _post_merge(plan=plan, runner=runner, journal=journal, merged=merged)


def _blocked_outcome(
    *,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    fabro: CommandResult,
) -> DispatchOutcome | None:
    """Detect a run parked at the in-loop human gate (third terminal state).

    A foreground `fabro run` exits non-zero when it returns at a human
    gate, so the exit code alone cannot distinguish blocked from failed:
    the engine parses the run id from the CLI output and reads the
    authoritative status via `fabro inspect --json`. Anything other
    than a confirmed blocked status falls back to exit-code routing.
    """
    run_id = parse_run_id(output=fabro.stdout + "\n" + fabro.stderr)
    if run_id is None:
        return None
    inspect = runner.run(
        argv=fabro_inspect_argv(plan=plan, run_id=run_id),
        cwd=plan.repo,
        timeout_seconds=_FABRO_INSPECT_TIMEOUT_SECONDS,
    )
    _journal_stage(journal=journal, plan=plan, stage="fabro-inspect", result=inspect)
    if inspect.exit_code != 0:
        return None
    if parse_run_status(stdout=inspect.stdout) != "blocked":
        return None
    return DispatchOutcome(
        work_item_id=plan.work_item_id,
        status="blocked",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail=(
            f"run {run_id} parked at the in-loop human gate (needs-human); "
            f"answer with `fabro attach {run_id}` while the engine lives, "
            f"`fabro resume {run_id}` only if the engine died; "
            "not auto-resumed, item left open"
        ),
    )


def _confirm_pr(
    *,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
) -> PrView | None:
    view = _view_pr(plan=plan, runner=runner, journal=journal)
    if view is None:
        return None
    if view.auto_merge_armed or view.state == "MERGED":
        return view
    arm = runner.run(
        argv=pr_arm_argv(plan=plan, number=view.number),
        cwd=plan.repo,
        timeout_seconds=_GH_TIMEOUT_SECONDS,
    )
    _journal_stage(journal=journal, plan=plan, stage="pr-arm-fallback", result=arm)
    return _view_pr(plan=plan, runner=runner, journal=journal)


def _await_merge(
    *,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    sleep: SleepFn,
    poll: PollPolicy,
) -> PrView | None:
    for attempt in range(poll.attempts):
        view = _view_pr(plan=plan, runner=runner, journal=journal)
        if view is not None and view.state == "MERGED":
            return view
        if view is not None and view.merge_state_status == "BEHIND":
            update = runner.run(
                argv=pr_update_branch_argv(plan=plan, number=view.number),
                cwd=plan.repo,
                timeout_seconds=_GH_TIMEOUT_SECONDS,
            )
            _journal_stage(journal=journal, plan=plan, stage="pr-update-branch", result=update)
        if attempt + 1 < poll.attempts:
            sleep(poll.interval_seconds)
    return None


def _post_merge(
    *,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    merged: PrView,
) -> DispatchOutcome:
    pull = runner.run(
        argv=pull_primary_argv(plan=plan),
        cwd=plan.repo,
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
    )
    _journal_stage(journal=journal, plan=plan, stage="pull-primary", result=pull)
    if pull.exit_code != 0:
        return _merged_failure(plan=plan, stage="pull-primary", merged=merged, result=pull)
    janitor = runner.run(
        argv=list(plan.janitor),
        cwd=plan.repo,
        timeout_seconds=_JANITOR_TIMEOUT_SECONDS,
    )
    _journal_stage(journal=journal, plan=plan, stage="janitor-post-merge", result=janitor)
    if janitor.exit_code != 0:
        return _merged_failure(plan=plan, stage="janitor-post-merge", merged=merged, result=janitor)
    return DispatchOutcome(
        work_item_id=plan.work_item_id,
        status="green",
        stage="done",
        pr_number=merged.number,
        merge_sha=merged.merge_sha,
        detail="merged, post-merge janitor green",
    )


def _view_pr(
    *,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
) -> PrView | None:
    result = runner.run(
        argv=pr_view_argv(plan=plan),
        cwd=plan.repo,
        timeout_seconds=_GH_TIMEOUT_SECONDS,
    )
    _journal_stage(journal=journal, plan=plan, stage="pr-view", result=result)
    if result.exit_code != 0:
        return None
    return parse_pr_view(stdout=result.stdout)


def _journal_stage(
    *,
    journal: JournalWriter,
    plan: DispatchPlan,
    stage: str,
    result: CommandResult,
) -> None:
    journal.append(
        record={
            "work_item_id": plan.work_item_id,
            "stage": stage,
            "exit_code": result.exit_code,
            "detail": _tail(text=result.stderr if result.exit_code != 0 else result.stdout),
        }
    )


def _failed(*, plan: DispatchPlan, stage: str, detail: str) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=plan.work_item_id,
        status="failed",
        stage=stage,
        pr_number=None,
        merge_sha=None,
        detail=detail,
    )


def _merged_failure(
    *,
    plan: DispatchPlan,
    stage: str,
    merged: PrView,
    result: CommandResult,
) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=plan.work_item_id,
        status="failed",
        stage=stage,
        pr_number=merged.number,
        merge_sha=merged.merge_sha,
        detail=_tail(text=result.stderr),
    )


def _tail(*, text: str, limit: int = 2000) -> str:
    stripped = text.strip()
    if len(stripped) <= limit:
        return stripped
    return stripped[-limit:]
