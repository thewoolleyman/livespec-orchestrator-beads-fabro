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
  primary -> post-merge janitor hard gate in a FRESH detached worktree
  of the merged ref -> report.

The post-merge janitor venue is deliberate (work-item
livespec-impl-beads-cgd): the host primary's working tree can carry
environment rot — stale `.venv` shebangs after a repo rename, a stale
`.coverage`, untracked ghost `__pycache__` dirs — that false-reds a
merge whose own sandbox checks and CI were green, recording a failed
dispatch for a green work-item. A fresh checkout of merged master
cannot carry that rot, so a red there is a real signal.

Three terminal states (livespec-impl-beads-4zl): `green` (merged,
post-merge janitor green), `failed` (an expected failure at a named
stage), and `blocked` — the run parked at the phase graph's in-loop
human gate (Fabro's native blocked status; the foreground `fabro run`
returns and the slot frees while a server-side engine holds the run).
Blocked is NOT a failure: the item stays open, nothing is closed, and
the human answers via `fabro attach <run-id>` (`fabro resume` only
when the engine died) — the Dispatcher never auto-resumes.

One refinement on `green` (livespec-impl-beads-cgd): when the merge
is confirmed but the janitor CHECKOUT cannot be provisioned (worktree
add or mise trust failed), the outcome is still `green` — gate
accounting must not count a host-environment problem as a work-item
failure — but the stage is `janitor-env-degraded` and the detail
carries an actionable remediation message. A red janitor INSIDE the
fresh checkout stays `failed` at `janitor-post-merge`, and the
checkout is kept on disk for diagnosis (it is removed after a green
run).

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
    janitor_trust_argv,
    janitor_worktree_add_argv,
    janitor_worktree_remove_argv,
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
    "FabroLauncher",
    "FabroRunResult",
    "JournalWriter",
    "PollPolicy",
    "SleepFn",
    "SynchronousFabroLauncher",
    "run_dispatch",
]

_GIT_TIMEOUT_SECONDS = 600.0
# Worst-case phase-graph wall clock the foreground `fabro run` subprocess
# must outlive (workflow.fabro budgets): implement 2 attempts x 14400s
# (one transient auto-retry) + janitor 3 visits x 3600s + fix 2 visits x
# 3600s + pr 2 attempts x 1800s = 50400s, plus sandbox-provisioning
# slack. A subprocess budget below the graph's own ceiling kills the CLI
# mid-run while the server-side engine keeps executing the graph.
_FABRO_TIMEOUT_SECONDS = 54000.0
_FABRO_INSPECT_TIMEOUT_SECONDS = 300.0
_GH_TIMEOUT_SECONDS = 300.0
_JANITOR_TIMEOUT_SECONDS = 3600.0

# The env-var an operator tunes the watchdog stall window with (named in
# the stalled-no-progress detail so the message is self-documenting).
_STALL_ENV_HINT = "LIVESPEC_DISPATCH_STALL_SECONDS"

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
class FabroRunResult:
    """Outcome of the watched `fabro run` foreground stage.

    `command` is the `CommandResult` of the `fabro run` process (its exit
    code routes the blocked / failed / green flow exactly as before).
    `stalled_run_id` is set ONLY when the coarse wall-clock watchdog
    confirmed a sustained-no-progress stall and `fabro rm -f`-ed the run
    (the 7us.6 hang class) — the engine then short-circuits to a distinct
    `stalled-no-progress` outcome. None means the watchdog never tripped
    (the normal path, including a clean probe-failure-but-healthy run:
    fail-safe, a flaky probe is NOT a stall).
    """

    command: CommandResult
    stalled_run_id: str | None = None


class FabroLauncher(Protocol):
    """Seam that runs `fabro run` to completion with a progress watchdog.

    Production is `_dispatcher_io.WatchedFabroLauncher`: it runs `fabro
    run` while the coarse wall-clock watchdog samples the event stream and
    `fabro rm -f`-es a confirmed stall. `SynchronousFabroLauncher` is the
    no-watchdog default (a plain `runner.run`, used where the watchdog is
    not wired and by the legacy hermetic engine tests). The DEFERRED 29f
    metrics-heartbeat primary becomes a third launcher feeding the same
    `decide_stall` — see `_dispatcher_watchdog`.
    """

    def launch(
        self,
        *,
        plan: DispatchPlan,
        runner: CommandRunner,
        journal: JournalWriter,
    ) -> FabroRunResult:
        """Run `fabro run` for `plan`, watching liveness; return the result."""
        ...


@dataclass(frozen=True, kw_only=True)
class SynchronousFabroLauncher:
    """No-watchdog launcher: a plain blocking `fabro run` (the legacy path).

    Preserves the exact pre-watchdog behavior — one `runner.run` of
    `fabro run` with the 15h `_FABRO_TIMEOUT_SECONDS` subprocess ceiling
    (bn4's coarse timeout, which COEXISTS with the watchdog as defense in
    depth). It never reports a stall, so `run_dispatch` routes purely on
    the exit code. `run_dispatch` defaults to this launcher so callers
    that do not wire the watchdog (and the existing engine tests) are
    unaffected.
    """

    def launch(
        self,
        *,
        plan: DispatchPlan,
        runner: CommandRunner,
        journal: JournalWriter,
    ) -> FabroRunResult:
        _ = journal
        command = runner.run(
            argv=fabro_run_argv(plan=plan),
            cwd=plan.repo,
            timeout_seconds=_FABRO_TIMEOUT_SECONDS,
        )
        return FabroRunResult(command=command)


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
    fabro_launcher: FabroLauncher | None = None,
) -> DispatchOutcome:
    """Drive one work-item end-to-end; never raises for expected failures.

    `fabro_launcher` runs the `fabro run` stage with the coarse
    wall-clock progress watchdog (work-item livespec-impl-beads-oyg). It
    defaults to the no-watchdog `SynchronousFabroLauncher` so callers that
    do not wire the watchdog keep the prior blocking behavior. When the
    launcher reports a confirmed stall, the engine short-circuits to a
    distinct `stalled-no-progress` outcome (fail-CLOSED) BEFORE any PR
    flow — the run was already `fabro rm -f`-ed by the launcher.
    """
    launcher = fabro_launcher if fabro_launcher is not None else SynchronousFabroLauncher()
    launched = launcher.launch(plan=plan, runner=runner, journal=journal)
    fabro = launched.command
    _journal_stage(journal=journal, plan=plan, stage="fabro-run", result=fabro)
    if launched.stalled_run_id is not None:
        return _stalled(plan=plan, run_id=launched.stalled_run_id)
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
    """Refresh the primary, then gate on the janitor in a fresh checkout.

    The janitor runs in a freshly provisioned detached worktree of the
    merged ref — NEVER the host primary's working tree, whose
    environment rot once false-redded a confirmed-green merge
    (livespec-impl-beads-cgd). Provisioning failures degrade (green
    outcome at `janitor-env-degraded` with actionable detail) instead
    of failing; a red janitor inside the fresh checkout is the real
    signal and stays a failure, with the checkout kept for diagnosis.
    """
    pull = runner.run(
        argv=pull_primary_argv(plan=plan),
        cwd=plan.repo,
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
    )
    _journal_stage(journal=journal, plan=plan, stage="pull-primary", result=pull)
    if pull.exit_code != 0:
        return _merged_failure(plan=plan, stage="pull-primary", merged=merged, result=pull)
    degraded = _provision_janitor_checkout(plan=plan, runner=runner, journal=journal, merged=merged)
    if degraded is not None:
        return degraded
    janitor = runner.run(
        argv=list(plan.janitor),
        cwd=plan.janitor_checkout,
        timeout_seconds=_JANITOR_TIMEOUT_SECONDS,
    )
    _journal_stage(journal=journal, plan=plan, stage="janitor-post-merge", result=janitor)
    if janitor.exit_code != 0:
        return DispatchOutcome(
            work_item_id=plan.work_item_id,
            status="failed",
            stage="janitor-post-merge",
            pr_number=merged.number,
            merge_sha=merged.merge_sha,
            detail=(
                f"post-merge janitor red in fresh checkout {plan.janitor_checkout} "
                f"(kept for diagnosis): {_tail(text=janitor.stderr)}"
            ),
        )
    cleanup = runner.run(
        argv=janitor_worktree_remove_argv(plan=plan),
        cwd=plan.repo,
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
    )
    _journal_stage(journal=journal, plan=plan, stage="janitor-checkout-remove", result=cleanup)
    return DispatchOutcome(
        work_item_id=plan.work_item_id,
        status="green",
        stage="done",
        pr_number=merged.number,
        merge_sha=merged.merge_sha,
        detail="merged, post-merge janitor green",
    )


def _provision_janitor_checkout(
    *,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    merged: PrView,
) -> DispatchOutcome | None:
    """Provision the fresh detached worktree the post-merge janitor runs in.

    Returns None when the checkout is ready, or the janitor-env-degraded
    outcome when a provisioning step fails (environment-shaped; the
    merge is already confirmed, so gate accounting must not record a
    work-item failure). Steps: a pre-clean `git worktree remove --force`
    whose result is deliberately ignored (it clears a stale registration
    left by a crashed earlier dispatch; on a clean host it just fails),
    the detached `git worktree add` at the merged ref (the merge sha
    when the PR view carried one, `origin/master` otherwise — the
    just-pulled primary has both), and `mise trust` inside the checkout
    (trust is per-path, so the fresh path is never pre-trusted and the
    default janitor's `mise exec` would refuse to run there).
    """
    preclean = runner.run(
        argv=janitor_worktree_remove_argv(plan=plan),
        cwd=plan.repo,
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
    )
    _journal_stage(journal=journal, plan=plan, stage="janitor-checkout-preclean", result=preclean)
    ref = merged.merge_sha if merged.merge_sha is not None else "origin/master"
    add = runner.run(
        argv=janitor_worktree_add_argv(plan=plan, ref=ref),
        cwd=plan.repo,
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
    )
    _journal_stage(journal=journal, plan=plan, stage="janitor-checkout-add", result=add)
    if add.exit_code != 0:
        return _merged_degraded(
            plan=plan,
            merged=merged,
            step=(
                f"provisioning the fresh janitor checkout at "
                f"{plan.janitor_checkout} (ref {ref})"
            ),
            result=add,
        )
    trust = runner.run(
        argv=janitor_trust_argv(),
        cwd=plan.janitor_checkout,
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
    )
    _journal_stage(journal=journal, plan=plan, stage="janitor-checkout-trust", result=trust)
    if trust.exit_code != 0:
        return _merged_degraded(
            plan=plan,
            merged=merged,
            step=f"`mise trust` inside the janitor checkout {plan.janitor_checkout}",
            result=trust,
        )
    return None


def _merged_degraded(
    *,
    plan: DispatchPlan,
    merged: PrView,
    step: str,
    result: CommandResult,
) -> DispatchOutcome:
    """Janitor-env-degraded: merged green, but the gate could not run.

    NOT a work-item failure (livespec-impl-beads-cgd): the merge is
    confirmed on the remote and the work-item's own sandbox checks and
    CI were green, so a host-side provisioning failure must not reset
    the gate streak. The outcome stays `green` for accounting, with the
    degradation loud in the stage and an actionable remediation detail.
    """
    return DispatchOutcome(
        work_item_id=plan.work_item_id,
        status="green",
        stage="janitor-env-degraded",
        pr_number=merged.number,
        merge_sha=merged.merge_sha,
        detail=(
            f"merged, but the post-merge janitor DID NOT RUN: {step} failed "
            f"({_tail(text=result.stderr, limit=500)}). This is a host-environment "
            f"problem, not a work-item failure — the merge is confirmed on the "
            f"remote. Remediate the host, then run `{' '.join(plan.janitor)}` in "
            f"a clean checkout of merged master to close the gate by hand."
        ),
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


def _stalled(*, plan: DispatchPlan, run_id: str) -> DispatchOutcome:
    """The distinct `stalled-no-progress` terminal (the 7us.6 hang class).

    The coarse wall-clock watchdog confirmed sustained no progress (no new
    fabro event for the full stall window) and `fabro rm -f`-ed the run.
    This is a FAIL-CLOSED terminal — never silently treated as success: a
    distinct `status` so the loop verdict exits non-zero and h1p's
    `notify_terminal` alarms the operator with the `stalled-no-progress`
    outcome class.
    """
    return DispatchOutcome(
        work_item_id=plan.work_item_id,
        status="stalled-no-progress",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail=(
            f"run {run_id} made no progress for the full stall window "
            f"(no new fabro event); the coarse wall-clock watchdog "
            f"`fabro rm -f`-ed it (the 7us.6 silent-deadlock class). "
            f"Set {_STALL_ENV_HINT} to tune the window; the DEFERRED 29f "
            f"OTEL metrics-heartbeat primary will refine this coarse signal."
        ),
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
