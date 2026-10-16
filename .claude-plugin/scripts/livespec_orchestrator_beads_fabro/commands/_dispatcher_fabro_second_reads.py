"""The SECOND reads that enrich a run observation the inspect payload cannot.

Both readings here answer a question `fabro inspect --json` structurally does
not carry, and both are therefore a second bounded round trip taken against an
observation already in hand rather than a different way of observing. That is
the cohesion: each takes an observed `FabroInspectResult`, spends at most one
extra read, and returns an enriched copy — never a fresh observation.

They are kept together, and apart from `_dispatcher_fabro_reattach`, because
that module owns OBSERVING a run (the inspect loop, its supervision budget and
its backoff) while these own what is attached once an observation is settled.
Each is gated on a DIFFERENT property of the observation and the two gates are
not interchangeable: the labels read fires only for a failure already
classified as a provider ceiling, because that is the only answer it can
change, while the event-stream read fires for any CONFIRMED FAILED run, because
a terminal's emitted output has to be recovered whatever the fault was.

Both are journaled under their own stage, for the one reason that governs every
read here: their SILENCE changes an answer. A refused labels read leaves the
conservative legacy attribution standing, and a refused event read leaves the
needs-human mapper with no preservation account — and at the outcome each is
indistinguishable from a run that never had one to read.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_journal import journal_stage
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
        JournalWriter,
    )
    from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan

__all__: list[str] = [
    "executed_candidate_attribution",
    "terminal_events_attachment",
]

# The labels read's own budget. It is one list of the factory's runs, taken at
# most once per observation and only for a failure already classified as a
# provider ceiling, so it is bounded well below the inspect budget.
_FABRO_PS_TIMEOUT_SECONDS = 60.0
# The stage event stream's own budget. One run's events, taken at most once per
# observation and only for a CONFIRMED failed run, so it too is bounded well
# below the inspect budget.
_FABRO_EVENTS_TIMEOUT_SECONDS = 60.0


def terminal_events_attachment(
    *,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    run_id: str,
    inspect: FabroInspectResult,
) -> FabroInspectResult:
    """Attach the run's stage event stream to a CONFIRMED failed observation.

    The confirmed-failed gate is what keeps this off every ordinary dispatch: a
    green run has no terminal output to recover, and an unanswered observation
    has not established that the run ended at all, so a read there would spend a
    round trip on a question the payload cannot answer.

    An UNREADABLE stream attaches `None` rather than an empty payload, because
    "read failure is not absence" is the governing rule for every consumer of
    these records: a probe that errored and a run that emitted nothing support
    opposite conclusions, and collapsing them would let a probe outage read as a
    terminal that preserved nothing.
    """
    if inspect.command.exit_code != 0 or inspect.status_kind != "failed":
        return inspect
    events = fabro_port_for_plan(plan=plan, runner=runner).events(
        run_id=run_id,
        timeout_seconds=_FABRO_EVENTS_TIMEOUT_SECONDS,
    )
    journal_stage(
        journal=journal,
        plan=plan,
        stage="fabro-terminal-events",
        result=cast("CommandResult", events.command),
    )
    return replace(
        inspect,
        events_payload=events.payload if events.command.exit_code == 0 else None,
    )


def executed_candidate_attribution(
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
