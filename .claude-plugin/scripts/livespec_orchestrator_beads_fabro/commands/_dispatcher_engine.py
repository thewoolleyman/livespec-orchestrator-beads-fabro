"""Dispatch engine: sequence one work-item through the Fabro Loop.

The engine owns the per-item lifecycle the family discipline prescribes
(livespec non-functional-requirements.md, Architecture C shape per
livespec/tmp/fabro-architecture-c-design.md):

  Production Fabro run through an origin-proven SOURCE worktree (the
  source runner owns its worktree/ref cleanup; Fabro clones fresh inside
  its docker sandbox and the phase graph does implement/janitor/PR)
  -> blocked-state check (`fabro inspect`) -> confirm auto-merge armed
  (arming as fallback when the
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
stage), and `blocked` — the phase graph's `needs_human` terminal fired
(the run preserved its tree on a run-scoped ref, emitted the
LIVESPEC_NEEDS_HUMAN sentinel and ended; plan ledger-is-the-only-gate,
contracts.md "A factory run never awaits a human", v093). Blocked is NOT
a failure: the item rests at `blocked / needs-human`, nothing is closed,
and the human decides through the ledger's valves — no run waits and the
Dispatcher never auto-resolves the decision.

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

from dataclasses import dataclass, replace
from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_correlation import (
    dispatch_correlation,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_current_merge_hold import (
    MERGE_HELD_STAGE,
    merge_hold_terminal,
    read_current_merge_hold,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_journal import (
    failed_outcome,
    journal_run_output_markers,
    journal_stage,
    stalled_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_merge import (
    await_merge,
    confirm_pr,
    outcome_after_await,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import (
    CommandResult,
    CommandRunner,
    DispatchOutcome,
    FabroLauncher,
    FabroRunResult,
    JournalWriter,
    PollPolicy,
    SleepFn,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_inputs import (
    dispatch_fabro_run_inputs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_reattach import inspect_after_run
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_terminal import (
    fabro_run_terminal_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_pr_open_diff import (
    pr_open_diff_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_labels import (
    dispatch_run_label_pairs,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import fabro_port_for_plan

__all__: list[str] = [
    "MERGE_HELD_STAGE",
    "CommandResult",
    "CommandRunner",
    "DispatchOutcome",
    "FabroLauncher",
    "FabroRunResult",
    "JournalWriter",
    "PollPolicy",
    "SleepFn",
    "SynchronousFabroLauncher",
    "dispatch_fabro_run_inputs",
    "run_dispatch",
    "run_fabro_factory_auth_login",
]

# The worst-case phase-graph wall clock the foreground `fabro run`
# subprocess must outlive is no longer a constant here: it is DERIVED per
# dispatch from the resolved node timeouts and stall timeout and carried on
# `plan.fabro_timeout_seconds` (`_node_timeouts.derive_fabro_timeout_seconds`).
# A subprocess budget below the graph's own ceiling kills the CLI mid-run
# while the server-side engine keeps executing the graph; a budget fixed
# above it masks a shortened node. Following the graph is what keeps both
# from happening silently.
_FABRO_AUTH_TIMEOUT_SECONDS = 300.0


def run_fabro_factory_auth_login(*, plan: DispatchPlan, runner: CommandRunner) -> None:
    _ = fabro_port_for_plan(plan=plan, runner=runner).auth_login(
        timeout_seconds=_FABRO_AUTH_TIMEOUT_SECONDS
    )


@dataclass(frozen=True, kw_only=True)
class SynchronousFabroLauncher:
    """No-watchdog launcher: a plain blocking `fabro run` (the legacy path).

    Preserves the exact pre-watchdog behavior — one `runner.run` of
    `fabro run` with the plan's derived subprocess ceiling (bn4's coarse
    timeout, which COEXISTS with the watchdog as defense in
    depth). It never reports a stall, so `run_dispatch` routes purely on
    the exit code. `run_dispatch` defaults to this launcher so callers
    that do not wire the watchdog (and the existing engine tests) are
    unaffected.

    `dispatch_id` rides here for the same reason it rides the watched
    launcher: both paths label their run with the dispatch's correlation,
    and the two launchers deliberately read the SAME inputs so a
    repository cannot have one path correlated and the other anonymous.
    None is an invocation that minted no id — the legacy default and the
    engine tests — which carries no labels rather than partial ones.
    """

    dispatch_id: str | None = None

    def launch(
        self,
        *,
        plan: DispatchPlan,
        runner: CommandRunner,
        journal: JournalWriter,
    ) -> FabroRunResult:
        _ = journal
        run_fabro_factory_auth_login(plan=plan, runner=runner)
        result = fabro_port_for_plan(plan=plan, runner=runner).run(
            workflow_toml=plan.workflow_toml,
            goal_file=plan.goal_file,
            inputs=dispatch_fabro_run_inputs(plan=plan),
            timeout_seconds=plan.fabro_timeout_seconds,
            # The repository and per-node entitlement labels, read off the
            # SAME plan fields the watched launcher reads them from: both
            # paths label a run identically, so a repository cannot have one
            # path's evidence discoverable host-wide and the other's not.
            labels=dispatch_run_label_pairs(repo=plan.repo, acp_nodes=plan.acp_nodes),
            correlation=dispatch_correlation(
                work_item_id=plan.work_item_id,
                dispatch_id=self.dispatch_id,
                factory=plan.fabro_factory_name,
            ),
        )
        return FabroRunResult(command=cast("CommandResult", result.command), run_id=result.run_id)


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
    journal_stage(journal=journal, plan=plan, stage="fabro-run", result=fabro)
    if launched.abandoned_run_id is not None:
        return DispatchOutcome(
            work_item_id=plan.work_item_id,
            status="failed",
            stage="stale-run-reap",
            pr_number=None,
            merge_sha=None,
            detail=(
                f"run {launched.abandoned_run_id} abandoned because work-item "
                f"{plan.work_item_id} status is {launched.abandoned_item_status}; "
                "item is no longer dispatchable"
            ),
            fabro_run_id=launched.abandoned_run_id,
        )
    if launched.stalled_run_id is not None:
        return stalled_outcome(
            outcome_type=DispatchOutcome, plan=plan, run_id=launched.stalled_run_id
        )
    run_id = launched.run_id
    inspect = inspect_after_run(
        plan=plan,
        runner=runner,
        journal=journal,
        run_id=run_id,
        follow_live=fabro.exit_code != 0,
        sleep=sleep,
    )
    inspect_stdout = "" if inspect is None else inspect.command.stdout
    inspect_stderr = "" if inspect is None else inspect.command.stderr
    # Both publication markers are read from ONE pass over this text, and the
    # hook-over-limit row is written there unconditionally of how the run ended
    # (see `journal_run_output_markers`). The event comes back so the terminal
    # outcome can carry it to the cause writer.
    hook_over_limit = journal_run_output_markers(
        journal=journal,
        work_item_id=plan.work_item_id,
        text=f"{fabro.stdout}\n{fabro.stderr}\n{inspect_stdout}\n{inspect_stderr}",
    )
    terminal = fabro_run_terminal_outcome(
        outcome_type=DispatchOutcome,
        plan=plan,
        run_id=run_id,
        inspect=inspect,
        exit_code=fabro.exit_code,
        stderr=fabro.stderr,
    )
    if terminal is not None:
        # Attached rather than threaded through `fabro_run_terminal_outcome`,
        # which classifies the ENGINE's own record and has no business reading a
        # sandbox sentinel. The event is evidence the cause writer renders only
        # where the ending is attributed to it.
        return replace(terminal, hook_over_limit=hook_over_limit)
    # THE CURRENT HOLD, read ONCE for the whole merge-confirmation boundary. The
    # plan's `merge_hold` is the launch snapshot the sandbox and the dispatch record
    # share and must keep; this is what the ledger says now, hours later, and a hold
    # set during the run is visible in exactly one of the two
    # (`_dispatcher_current_merge_hold`).
    hold = read_current_merge_hold(repo=plan.repo, work_item_id=plan.work_item_id)
    view = confirm_pr(plan=plan, runner=runner, journal=journal, hold=hold)
    if view is None:
        return failed_outcome(
            outcome_type=DispatchOutcome,
            plan=plan,
            stage="pr-view",
            detail="no PR found for branch",
            fabro_run_id=run_id,
        )
    # The branch-versus-base size, recorded HERE and not at the terminal (plan
    # slice S4, `bd-ib-tbgxm4`): this is the moment the pull request is confirmed
    # and nothing about merging has been decided yet, so the measurement rides
    # the journal whatever terminal follows — the merge hold's green, a merge-poll
    # timeout, a terminal required-check failure, or a post-merge janitor failure.
    # The merged-PR size beside it is read only for a green outcome, which is why
    # it was absent on every non-converged run the calibration pass had.
    journal.append(
        record=pr_open_diff_record(
            work_item_id=plan.work_item_id,
            pr_number=view.number,
            diff_size=view.diff_size,
        )
    )
    current_hold = merge_hold_terminal(
        outcome_type=DispatchOutcome, plan=plan, view=view, hold=hold, run_id=run_id
    )
    if current_hold is not None:
        return current_hold
    outcome = outcome_after_await(
        outcome_type=DispatchOutcome,
        plan=plan,
        runner=runner,
        journal=journal,
        merged=await_merge(
            outcome_type=DispatchOutcome,
            plan=plan,
            runner=runner,
            journal=journal,
            sleep=sleep,
            poll=poll,
        ),
        pr_number=view.number,
        run_id=run_id,
    )
    if run_id is not None and outcome.fabro_run_id is None:
        outcome = replace(outcome, fabro_run_id=run_id)
    return outcome
