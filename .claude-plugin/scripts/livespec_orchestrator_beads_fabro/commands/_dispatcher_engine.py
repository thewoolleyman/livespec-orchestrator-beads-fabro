"""Dispatch engine: sequence one work-item through the Fabro Loop.

The engine owns the per-item lifecycle the family discipline prescribes
(livespec non-functional-requirements.md, Architecture C shape per
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

from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_current_merge_hold import (
    CurrentMergeHold,
    read_current_merge_hold,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_journal import (
    failed_outcome,
    journal_stage,
    stalled_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_merge import (
    await_merge,
    confirm_pr,
    outcome_after_await,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_terminal import (
    fabro_run_terminal_outcome,
    inspect_run,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
    PrView,
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

# The stage a merge-held run terminates GREEN at. It is a named constant rather
# than a literal at its two sites because the second site — the post-merge
# dispositions — reads it as the ONE green outcome that has not merged, and a
# spelling that drifted between the two would silently re-arm the acceptance
# valve on unmerged work.
MERGE_HELD_STAGE = "pr"

# The worst-case phase-graph wall clock the foreground `fabro run`
# subprocess must outlive is no longer a constant here: it is DERIVED per
# dispatch from the resolved node timeouts and stall timeout and carried on
# `plan.fabro_timeout_seconds` (`_node_timeouts.derive_fabro_timeout_seconds`).
# A subprocess budget below the graph's own ceiling kills the CLI mid-run
# while the server-side engine keeps executing the graph; a budget fixed
# above it masks a shortened node. Following the graph is what keeps both
# from happening silently.
_FABRO_AUTH_TIMEOUT_SECONDS = 300.0
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
        env: dict[str, str] | None = None,
        stdin: int | None = None,
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
    `abandoned_run_id` is set when the launcher reaped a queued/running run
    whose work-item is already no longer dispatchable.
    """

    command: CommandResult
    run_id: str | None = None
    stalled_run_id: str | None = None
    abandoned_run_id: str | None = None
    abandoned_item_status: str | None = None


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
    """

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
        )
        return FabroRunResult(command=cast("CommandResult", result.command), run_id=result.run_id)


@dataclass(frozen=True, kw_only=True)
class DispatchOutcome:
    """Terminal report for one dispatched work-item.

    `status` is one of `green` / `failed` / `blocked` (blocked = the run's
    `needs_human` terminal fired and the item rests at blocked / needs-human
    in the ledger; surfaced to a human, never treated as a failure, never
    auto-resolved).

    `step` / `missing_integration_point` / `remedy` are the STRUCTURED half
    of a degraded post-merge outcome: the stable step identifier from the
    closed vocabulary, the required integration point the governed
    repository did not provide, and how to provide it. They are fields
    rather than prose inside `detail` because the NEXT dispatch's
    pre-dispatch gate has to match on them -- free prose describing the
    same failure cannot be matched against a waiver entry, nor against the
    re-verification that clears the refusal. They are None on every outcome
    that is not a degraded step outcome.

    `dead_implementer_condition` is the governing condition of a
    dead-implementer truncation, carried as a typed field rather than left for
    each consumer to re-match against `detail` prose — the same seam rationale
    as `provider_usage_limit`. It is None on every run whose implementer
    changed the worktree, which is every ordinary run.

    `provider_usage_limit_provider` names the vendor that refused, read off this
    run's own failure. It is what an exhaustion record is labelled with, and it
    is carried rather than assumed because the detection behind
    `provider_usage_limit` fires for either vendor.

    `verdict` is the POST-MERGE ACCEPTANCE verdict, and it is None on every
    outcome that never reached the acceptance valve. The parking-verdict clause of
    `SPECIFICATION/contracts.md` requires the dispatch result to report it beside
    `stage` and `status`, which is why it rides here rather than being left for a
    consumer to recover from the journal: the journal lives in the `tmp/` tree of
    whichever host ran the dispatch, and the result is what an operator and an
    exit code see.
    """

    work_item_id: str
    status: str
    stage: str
    verdict: str | None = None
    pr_number: int | None
    merge_sha: str | None
    detail: str
    step: str | None = None
    missing_integration_point: str | None = None
    remedy: str | None = None
    fabro_run_id: str | None = None
    fabro_failure_cause: str | None = None
    fabro_failure_category: str | None = None
    fabro_failure_signature: str | None = None
    provider_usage_limit: bool = False
    provider_usage_limit_provider: str | None = None
    dead_implementer_condition: str | None = None


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
    inspect = inspect_run(plan=plan, runner=runner, journal=journal, run_id=run_id)
    if (
        fabro.exit_code != 0
        and run_id is not None
        and (
            inspect is not None
            and inspect.command.exit_code == 0
            and inspect.status_kind == "failed"
            and inspect.failure is None
        )
    ):
        refreshed = inspect_run(plan=plan, runner=runner, journal=journal, run_id=run_id)
        if refreshed is not None and refreshed.failure is not None:
            inspect = refreshed
    terminal = fabro_run_terminal_outcome(
        outcome_type=DispatchOutcome,
        plan=plan,
        run_id=run_id,
        inspect=inspect,
        exit_code=fabro.exit_code,
        stderr=fabro.stderr,
    )
    if terminal is not None:
        return terminal
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
    current_hold = _current_hold_terminal(plan=plan, view=view, hold=hold, run_id=run_id)
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


def _current_hold_terminal(
    *,
    plan: DispatchPlan,
    view: PrView,
    hold: CurrentMergeHold,
    run_id: str | None,
) -> DispatchOutcome | None:
    """The terminal the CURRENT merge hold puts on this run, or None to keep going.

    Keyed on the reading `confirm_pr` already acted on rather than on
    `plan.merge_hold`, so the arming decision and the terminal classification cannot
    disagree about one run. The launch snapshot cannot answer this: a hold applied
    after dispatch is absent from it, and the measured defect was both halves
    reading it (`_dispatcher_current_merge_hold`).

    A MERGED pull request is past the hold entirely and returns None, so the run
    proceeds to its ordinary post-merge path. Terminating green-with-no-merge there
    would skip the post-merge janitor and the acceptance valve on work that HAS
    merged, which is a worse outcome than the one the hold is protecting against.
    """
    if view.state == "MERGED":
        return None
    if hold != "held":
        return None
    # THE HOLD'S TERMINAL. Nothing may merge this pull request, so polling for its
    # merge could only spend the whole budget and then report a FAILURE for work that
    # succeeded. The run ends here instead, green, exactly as `contracts.md` -> "The
    # per-item merge hold" requires: green is also what reclaims the claim under the
    # ordinary green-terminal rule, so a held item holds no capacity slot while it
    # waits for a person. `merge_sha` is None because nothing merged — this is the one
    # green outcome that carries no merge, and the post-merge dispositions read that
    # from the stage rather than re-deriving the hold.
    return DispatchOutcome(
        work_item_id=plan.work_item_id,
        status="green",
        stage=MERGE_HELD_STAGE,
        pr_number=view.number,
        merge_sha=None,
        detail=(
            f"merge hold stands: PR #{view.number} is open with no auto-merge armed, "
            "and the run terminated rather than waiting for a merge no automated path "
            f"may perform. Release with `set-merge-hold:{plan.work_item_id}:off`."
        ),
        fabro_run_id=run_id,
    )


def dispatch_fabro_run_inputs(*, plan: DispatchPlan) -> tuple[str, ...]:
    """Render the `--input` pairs for one dispatch's `fabro run`.

    Every ACP node's adapter comes from `plan.acp_nodes`, already resolved
    through the workflow / repository / per-dispatch layers and already
    journaled — this function only renders what resolved, so the record and
    the run cannot disagree. NO adapter string, model or provider appears
    here as a literal: which provider a node runs is configuration, per
    `SPECIFICATION/contracts.md`.

    A plan carrying NO resolution passes no adapter input at all, leaving
    the workflow's own declared defaults standing — layer 1 applied by
    fabro rather than by us, not a fallback provider choice.

    `plan.integration_inputs` carries the same discipline for the repository
    integration contract: the sandbox-facing fields are PROJECTIONS of the one
    contract the plan resolved and the dispatch record journaled, already
    intersected with the input names the dispatched workflow declares. They are
    rendered here rather than resolved here for exactly the reason the adapters
    are — the record and the run must not be able to disagree.

    The three PER-ITEM POLICY inputs at the end are rendered on EVERY dispatch
    rather than intersected with what the payload declares, because they are
    projections of the item's own effective policy rather than of the
    repository's contract: an item is dispatched with a review-fix cap, a
    merge-on-review-cap outcome and a merge hold whatever else is true of it.
    `merge_hold` spells its boolean the way the run config declares it, so the
    value the workflow's own default carries and the value a dispatch renders
    are the same word.
    """
    adapters = () if plan.acp_nodes is None else plan.acp_nodes.run_inputs
    return (
        *adapters,
        *plan.integration_inputs,
        f"review_fix_visit_cap={plan.review_fix_visit_cap}",
        f"merge_on_review_cap_outcome={plan.merge_on_review_cap_outcome}",
        f"merge_hold={'true' if plan.merge_hold else 'false'}",
    )
