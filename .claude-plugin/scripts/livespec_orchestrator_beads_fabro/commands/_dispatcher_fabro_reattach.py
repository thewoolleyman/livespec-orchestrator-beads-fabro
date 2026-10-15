"""Observe the bound server run after the foreground client disconnects."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_dead_implementer import (
    DEAD_IMPLEMENTER_SENTINEL,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_journal import journal_stage
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    NEEDS_HUMAN_MARKER,
    NON_CONVERGED_MARKER,
    DispatchPlan,
)
from livespec_orchestrator_beads_fabro.commands._fabro_executed_candidate import (
    attributed_provider_limit_failure,
    executed_candidate_identity,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import (
    FabroInspectResult,
    fabro_port_for_plan,
)
from livespec_orchestrator_beads_fabro.commands._fabro_terminal_evidence import terminal_evidence

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
        CommandResult,
        CommandRunner,
        DispatchOutcome,
        JournalWriter,
    )

__all__: list[str] = [
    "TERMINAL_STATUS_KINDS",
    "ReattachTiming",
    "inspect_after_run",
    "inspect_run",
    "unobservable_run_outcome",
]

_FABRO_INSPECT_TIMEOUT_SECONDS = 300.0
# A broken route must outlive the measured 2m25s tailnet outage without
# trapping a dispatcher indefinitely. The attempt cap also bounds immediate
# refusals; a healthy live observation resets both limits.
_REATTACH_WINDOW_SECONDS = 600.0
_MAX_UNANSWERED_INSPECTS = 12
TERMINAL_STATUS_KINDS = frozenset(
    {"succeeded", "failed", "cancelled", "canceled", "blocked", "human_input_required"}
)
_LIVE_STATUS_KINDS = frozenset({"running", "runnable", "pending", "queued", "starting", "paused"})
# The labels read's own budget. It is one list of the factory's runs, taken at
# most once per observation and only for a failure already classified as a
# provider ceiling, so it is bounded well below the inspect budget above.
_FABRO_PS_TIMEOUT_SECONDS = 60.0
# Each sentinel a TERMINAL node prints on the client's own channel before the
# client exits non-green. `DEAD_IMPLEMENTER_SENTINEL` covers its check-failed
# variant too, which carries it as a prefix.
_CLIENT_TERMINAL_SENTINELS = (NEEDS_HUMAN_MARKER, NON_CONVERGED_MARKER, DEAD_IMPLEMENTER_SENTINEL)


@dataclass(frozen=True, kw_only=True)
class ReattachTiming:
    """The clock and waiting seam of one supervision loop."""

    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic


_DEFAULT_TIMING = ReattachTiming()


def inspect_run(
    *,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    run_id: str | None,
    follow_live: bool = False,
    timing: ReattachTiming = _DEFAULT_TIMING,
) -> FabroInspectResult | None:
    """Read a run, and attribute a provider ceiling to the candidate that ran.

    The observation itself is `_observed_run` below. What this adds is the one
    thing the observed payload cannot answer: WHICH candidate entitlement the
    failing attempt spent. MEASURED on both engines, an `inspect --json` record
    carries no `labels` key — the pinned build answers `run_id`, `status` and
    `checkpoint`, and the candidate build answers nine keys, none of them
    labels — while the `ps --json` run row carries them on every row. So the
    attribution costs a SECOND read, and it is taken HERE, at the one function
    every dispatch and every reconciliation reads a run through, rather than at
    each of the terminal mappers that consume the failure.
    """
    if run_id is None:
        return None
    return _executed_candidate_attribution(
        plan=plan,
        runner=runner,
        journal=journal,
        run_id=run_id,
        inspect=_observed_run(
            plan=plan,
            runner=runner,
            journal=journal,
            run_id=run_id,
            follow_live=follow_live,
            timing=timing,
        ),
    )


def _executed_candidate_attribution(
    *,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    run_id: str,
    inspect: FabroInspectResult,
) -> FabroInspectResult:
    """Re-attribute a classified provider ceiling from the run's own labels.

    The typed flag is the gate, so an ordinary failure spends no second read:
    `ps -a --json` lists every run the factory holds (1626 rows measured on
    `hp`), and a failure reporting no ceiling has no provider to attribute.

    The failing node comes from `terminal_evidence`, which is the reading that
    already knows how to find it on BOTH engines and which excludes the
    needs-human terminal — the one node that cannot be the cause, and the one
    that records a failed outcome on every run reaching it. An observation
    carrying no terminal evidence names no node, so no identity is established
    and the v107 cause-text attribution stands.
    """
    failure = inspect.failure
    if failure is None or not failure.provider_usage_limit:
        return inspect
    evidence = terminal_evidence(payload=inspect.payload)
    executed = executed_candidate_identity(
        labels=_run_labels(plan=plan, runner=runner, journal=journal, run_id=run_id),
        node=None if evidence is None else evidence.current_predecessor,
    )
    return replace(
        inspect,
        failure=attributed_provider_limit_failure(failure=failure, executed=executed),
    )


def _run_labels(
    *,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    run_id: str,
) -> Mapping[str, str]:
    """The labels the factory's own row records for THIS run, or none.

    The row is selected by run id rather than taken from the head of the list:
    a factory serves every repository on its host, so another repository's row
    carries a well-formed entitlement that belongs to somebody else's dispatch.

    The read is journaled under its own stage because its SILENCE changes an
    answer — a refused or unparseable listing leaves the conservative legacy
    attribution standing, which at the outcome is indistinguishable from a
    dispatch that never recorded an identity to read.
    """
    ps = fabro_port_for_plan(plan=plan, runner=runner).ps(timeout_seconds=_FABRO_PS_TIMEOUT_SECONDS)
    journal_stage(
        journal=journal,
        plan=plan,
        stage="fabro-run-labels",
        result=cast("CommandResult", ps.command),
    )
    for summary in ps.runs:
        if summary.run_id == run_id:
            return summary.labels
    return {}


def _observed_run(
    *,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    run_id: str,
    follow_live: bool,
    timing: ReattachTiming,
) -> FabroInspectResult:
    """Read a run, optionally supervising it after a lost client stream.

    Only confirmed terminal evidence ends supervision immediately. Failed or
    unrecognized reads use exponential backoff, capped at a minute, for at most
    ten minutes or twelve consecutive unanswered inspections. Inspect timeouts
    consume that same budget. Confirmed live reads reset it and keep polling.
    """
    unanswered = 0
    attempt = 0
    deadline = timing.clock() + _REATTACH_WINDOW_SECONDS
    while True:
        timeout = (
            min(_FABRO_INSPECT_TIMEOUT_SECONDS, max(0.001, deadline - timing.clock()))
            if follow_live
            else _FABRO_INSPECT_TIMEOUT_SECONDS
        )
        inspect = fabro_port_for_plan(plan=plan, runner=runner).inspect(
            run_id=run_id,
            timeout_seconds=timeout,
        )
        journal_stage(
            journal=journal,
            plan=plan,
            stage="fabro-inspect",
            result=cast("CommandResult", inspect.command),
        )
        if follow_live:
            attempt += 1
            journal.append(
                record={
                    "stage": "fabro-reattach",
                    "work_item_id": plan.work_item_id,
                    "run_id": run_id,
                    "attempt": attempt,
                    "exit_code": inspect.command.exit_code,
                    "status": inspect.status_kind,
                    "server_url": plan.fabro_factory_server,
                }
            )
        if not follow_live or (
            inspect.command.exit_code == 0 and inspect.status_kind in TERMINAL_STATUS_KINDS
        ):
            return inspect
        if inspect.command.exit_code == 0 and inspect.status_kind in _LIVE_STATUS_KINDS:
            unanswered = 0
            timing.sleep(30.0)
            deadline = timing.clock() + _REATTACH_WINDOW_SECONDS
            continue
        unanswered += 1
        remaining = deadline - timing.clock()
        if unanswered >= _MAX_UNANSWERED_INSPECTS or remaining <= 0:
            return inspect
        timing.sleep(min(5.0 * 2 ** (unanswered - 1), 60.0, remaining))
        if timing.clock() >= deadline:
            return inspect


def inspect_after_run(
    *,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    run_id: str | None,
    follow_live: bool,
    sleep: Callable[[float], None],
) -> FabroInspectResult | None:
    """Observe completion and refresh a failed run's not-yet-persisted detail."""
    inspect = inspect_run(
        plan=plan,
        runner=runner,
        journal=journal,
        run_id=run_id,
        follow_live=follow_live,
        timing=ReattachTiming(sleep=sleep),
    )
    if (
        follow_live
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
    return inspect


def unobservable_run_outcome(
    *,
    outcome_type: type[DispatchOutcome],
    plan: DispatchPlan,
    run_id: str | None,
    inspect: FabroInspectResult | None,
    client_text: str,
) -> DispatchOutcome | None:
    """Retain ownership when a failed client leaves its bound run unobservable.

    The caller has already handled a clean client exit. An unanswered or
    unrecognized observation cannot establish failure, release a claim or
    authorize another launch of this item. The run id and factory remain
    visible for continued observation after this supervision budget expires.

    A CLIENT THAT PRINTED A TERMINAL SENTINEL IS NOT UNOBSERVABLE, however its
    inspections went — which is why `client_text` is a required argument rather
    than something a caller may leave off. Such a sentinel is positive proof the
    run reached a terminal node, and on the pinned engine the client's own
    output is the ONLY channel carrying it: an unanswered inspect leaves
    `inspect.failure` empty, so reporting the run unobservable here would
    discard the one verdict in hand. The cost is not a relabel. Every
    disposition downstream — the needs-human ledger valve, the durable
    `livespec-needs-human-cause` comment that outlives the run, the preserved
    reference record, and the non-convergence cap that reads
    `NON_CONVERGED_MARKER` out of the detail — gates on a `blocked` or `failed`
    status, so a shadowed sentinel rests the item at `active` with none of them
    written, after a supervision budget spent on a run that had already ended.
    """
    # No inspection result means re-attachment was never attempted, as in
    # legacy callers reporting explicit terminal sentinels from the client.
    if (
        run_id is None
        or inspect is None
        or (inspect.command.exit_code == 0 and inspect.status_kind in TERMINAL_STATUS_KINDS)
        or any(sentinel in client_text for sentinel in _CLIENT_TERMINAL_SENTINELS)
    ):
        return None
    return outcome_type(
        work_item_id=plan.work_item_id,
        status="run-unobservable",
        stage="fabro-reattach",
        pr_number=None,
        merge_sha=None,
        fabro_run_id=run_id,
        detail=(
            f"run {run_id} on {plan.fabro_factory_server or 'the local factory'} "
            "is possibly still alive; re-attach observation budget exhausted; "
            "work-item claim retained"
        ),
    )
