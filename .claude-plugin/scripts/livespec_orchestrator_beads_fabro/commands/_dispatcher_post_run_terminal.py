"""The terminal path a dispatch takes once its `fabro run` has returned.

Everything the engine does between the launcher handing back a run and the
pull-request flow beginning belongs to one concern: observe the run after the
client returned, read the publication markers out of its output, derive the
terminal outcome the run's own record supports, and reconcile that outcome with
the pull request publication left behind. It lives apart from `run_dispatch` so
the engine sequences the lifecycle and this module owns what a finished run
means.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_journal import (
    journal_run_output_markers,
    run_wall_budget_outcome,
    stalled_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import (
    CommandRunner,
    DispatchOutcome,
    FabroRunResult,
    JournalWriter,
    SleepFn,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_reattach import (
    ReattachRun,
    inspect_after_run,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_terminal import (
    fabro_run_terminal_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_node_timeout_cut import (
    attach_node_timeout_cut,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_successful_terminal import (
    successful_store_loss_evidence,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_terminal_publication import (
    TerminalPublication,
    reconcile_terminal_publication,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_worker_exit_log_cause import (
    worker_exit_engine_failure_outcome,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroInspectResult

__all__: list[str] = [
    "PostRunTerminal",
    "post_run_terminal",
    "reattach_terminal",
]


@dataclass(frozen=True, kw_only=True)
class PostRunTerminal:
    """What the finished run left the engine to act on.

    `refusal` is the terminal outcome the publication reconciliation could not
    override, already carrying the hook-over-limit and node-timeout evidence;
    when it is set the engine returns it as the dispatch's ending. Otherwise the
    engine continues into the pull-request flow with `publication`, and reads
    `run_output` for the markers the merged reconcile is taken from.
    """

    run_id: str | None
    run_output: str
    publication: TerminalPublication
    refusal: DispatchOutcome | None


def post_run_terminal(
    *,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    launched: FabroRunResult,
    sleep: SleepFn,
) -> PostRunTerminal:
    """Derive how the returned run ended and what publication it left behind."""
    fabro = launched.command
    run_id = launched.run_id
    inspect = inspect_after_run(
        plan=plan,
        runner=runner,
        journal=journal,
        run_id=(
            None
            if run_id is None
            else ReattachRun(run_id=run_id, watch_state=launched.run_watch_state)
        ),
        follow_live=fabro.exit_code != 0,
        sleep=sleep,
    )
    inspect_stdout = "" if inspect is None else inspect.command.stdout
    inspect_stderr = "" if inspect is None else inspect.command.stderr
    # Both publication markers are read from ONE pass over this text, and the
    # hook-over-limit row is written there unconditionally of how the run ended
    # (see `journal_run_output_markers`). The event comes back so the terminal
    # outcome can carry it to the cause writer.
    run_output = f"{fabro.stdout}\n{fabro.stderr}\n{inspect_stdout}\n{inspect_stderr}"
    reattached = reattach_terminal(plan=plan, inspect=inspect)
    if reattached is not None:
        publication = reconcile_terminal_publication(
            plan=plan,
            runner=runner,
            journal=journal,
            terminal=reattached,
            evidence=None,
        )
        return PostRunTerminal(
            run_id=run_id,
            run_output=run_output,
            publication=publication,
            refusal=publication.refusal,
        )
    hook_over_limit = journal_run_output_markers(
        journal=journal, work_item_id=plan.work_item_id, text=run_output
    )
    terminal = fabro_run_terminal_outcome(
        outcome_type=DispatchOutcome,
        plan=plan,
        run_id=run_id,
        inspect=inspect,
        exit_code=fabro.exit_code,
        stderr=fabro.stderr,
    )
    # AND WHERE THE SAME CONCLUSION HID A FAILURE, THE ENGINE'S OWN VERDICT IS
    # RECOVERED FROM THE RUN'S EXPORTED LOG. The worker-exit sentence names no
    # fault, so a run that really did fail was reported as terminated with no
    # cause while its log still carried the deterministic failure cycle the
    # engine had decided. This passes every other ending straight through, and
    # spends its export only on that one conclusion.
    terminal = worker_exit_engine_failure_outcome(
        plan=plan,
        runner=runner,
        journal=journal,
        run_id=run_id,
        inspect=inspect,
        terminal=terminal,
    )
    # A STRUCTURED SUCCESSFUL CHECKPOINT OUTRANKS THE ENGINE'S OWN CONCLUSION,
    # and only for the one conclusion that admits it cannot answer: a worker
    # that exited zero before its terminal run event was persisted. The engine
    # then reports `failed` for a workflow that completed every node, so the
    # dispatch used to report a false implementation failure over an already
    # published pull request. The checkpoint is read for THIS run only, and it
    # decides nothing alone -- the reconciliation below still has to find the
    # matching publication -- so every other failure keeps its own terminal
    # outcome, untouched.
    evidence = successful_store_loss_evidence(plan=plan, run_id=run_id, inspect=inspect)
    publication = reconcile_terminal_publication(
        plan=plan,
        runner=runner,
        journal=journal,
        terminal=terminal,
        evidence=evidence,
    )
    refusal: DispatchOutcome | None = None
    if publication.refusal is not None:
        # Attached rather than threaded through `fabro_run_terminal_outcome`,
        # which classifies the ENGINE's own record and has no business reading a
        # sandbox sentinel. The event is evidence the cause writer renders only
        # where the ending is attributed to it.
        refusal = attach_node_timeout_cut(
            outcome=replace(publication.refusal, hook_over_limit=hook_over_limit),
            node_timeouts=plan.node_timeouts,
            text=run_output,
            events_payload=None if inspect is None else inspect.events_payload,
            journal=journal,
        )
    return PostRunTerminal(
        run_id=run_id, run_output=run_output, publication=publication, refusal=refusal
    )


def reattach_terminal(
    *, plan: DispatchPlan, inspect: FabroInspectResult | None
) -> DispatchOutcome | None:
    """Map a cancel performed during re-attach before publication reconciliation."""
    if inspect is None:
        return None
    if inspect.budget_exceeded_run_id is not None:
        return run_wall_budget_outcome(
            outcome_type=DispatchOutcome,
            plan=plan,
            run_id=inspect.budget_exceeded_run_id,
        )
    if inspect.stalled_run_id is not None:
        return stalled_outcome(
            outcome_type=DispatchOutcome,
            plan=plan,
            run_id=inspect.stalled_run_id,
        )
    return None
