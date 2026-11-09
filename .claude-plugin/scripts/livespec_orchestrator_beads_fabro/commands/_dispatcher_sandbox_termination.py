"""Attach the sandbox provider's termination report to a confirmed-failed run.

`SPECIFICATION/contracts.md` section "Provider-limit permanence and root-cause
surfacing" -> "A sandbox killed for memory is named." (`bd-ib-jnstxo`,
Scenario 335). The report is read HERE, at the one seam every dispatch and every
reconciliation observes a run through, because the sandbox must still exist:
once the collection duty of section "Sandbox retention and collection" deletes
it, the provider has nothing left to report and the only honest answer is
"unobservable".

The confirmed-failed gate is what keeps this off every ordinary dispatch: a green
run has no failure to classify, and an unanswered observation has not
established that the run ended at all. Every reading is journaled under its own
stage, because its SILENCE changes an answer -- an unreadable report leaves the
failure under the category it arrived with, which at the outcome is otherwise
indistinguishable from a run whose container ended cleanly.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._fabro_resource_exhaustion import (
    sandbox_termination_statement,
)
from livespec_orchestrator_beads_fabro.commands._fabro_sandbox_termination import (
    PERMANENT_CATEGORY,
    oom_reclassified_failure,
    permanent_failure_signature,
    read_sandbox_termination,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
        CommandRunner,
        DispatchOutcome,
        JournalWriter,
    )
    from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
    from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroInspectResult

__all__: list[str] = [
    "JOURNAL_STAGE_SANDBOX_TERMINATION",
    "outcome_naming_sandbox_termination",
    "sandbox_termination_attachment",
]

JOURNAL_STAGE_SANDBOX_TERMINATION = "fabro-sandbox-termination"


def sandbox_termination_attachment(
    *,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    run_id: str,
    inspect: FabroInspectResult,
) -> FabroInspectResult:
    """Read the run's sandbox termination and reclassify an OOM-killed run."""
    if inspect.command.exit_code != 0 or inspect.status_kind != "failed":
        return inspect
    termination = read_sandbox_termination(runner=runner, cwd=plan.repo, run_id=run_id)
    journal.append(
        record={
            "stage": JOURNAL_STAGE_SANDBOX_TERMINATION,
            "work_item_id": plan.work_item_id,
            "run_id": run_id,
            "observed": termination.observed,
            "oom_killed": termination.oom_killed,
            "memory_limit_bytes": termination.memory_limit_bytes,
            "detail": termination.detail,
        }
    )
    return replace(
        inspect,
        failure=oom_reclassified_failure(failure=inspect.failure, termination=termination),
        sandbox_termination=termination,
    )


def outcome_naming_sandbox_termination(
    *,
    outcome: DispatchOutcome,
    inspect: FabroInspectResult | None,
) -> DispatchOutcome:
    """The outcome, naming what the sandbox provider reported about the container.

    Applied to EVERY non-green mapping rather than inside one of them, because an
    OOM-killed run can end at several terminals -- the generic failure, the
    needs-human terminal, a sandbox-acquire failure -- and each re-reads its own
    failure from the engine's records, where the sandbox report is not. The
    reclassification is therefore stated here as well as on the failure detail,
    and from the same reading, so the two cannot disagree. A reading with
    nothing to say (a container that was not OOM-killed) changes nothing.
    """
    termination = None if inspect is None else inspect.sandbox_termination
    statement = (
        None if termination is None else sandbox_termination_statement(termination=termination)
    )
    if termination is None or statement is None:
        return outcome
    named = replace(
        outcome,
        detail=f"{outcome.detail}; {statement}" if outcome.detail else statement,
        sandbox_termination=termination,
    )
    if not termination.oom_killed:
        return named
    return replace(
        named,
        fabro_failure_category=PERMANENT_CATEGORY,
        fabro_failure_signature=permanent_failure_signature(
            signature=outcome.fabro_failure_signature
        ),
    )
