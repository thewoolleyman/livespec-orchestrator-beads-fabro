"""The engine verdict an exported run log still carries after a run-store loss.

A worker that loses its canonical run store cannot persist the terminal run
event, so the engine finalises the run from the only thing it has left: the
worker's own exit status. The conclusion it writes is `terminated` with
`Worker exited before emitting a terminal run event: exit status: 0` as its
whole account of the fault -- a sentence that names no node, no category and
no fault, because at the moment it is written there is nothing left to read it
off. Nobody killed the run; the Dispatcher then reports a dispatch terminated
with no cause while the engine had already decided something far more useful.

WHAT THE ENGINE HAD DECIDED IS STILL ON DISK. The verdict is logged BEFORE the
store loss, into the run's own log, and `fabro dump` still exports it. Measured
on hp run `01M592T85GVV` (work-item `bd-ib-5vtqaq`, 2026-10-19): `janitor@4`
completed with exit 1 at 06:27:30Z; at 06:27:31.222Z `run.log` carries ERROR
`Workflow run failed deterministic failure cycle detected: signature
janitor|deterministic|script failed with exit code ...`; at 06:27:32.701Z the
same log carries WARN `Failed to write run event error=worker lost canonical
run store during append run event`; and only then does `events.jsonl` record
`run.failed` with reason `terminated` and the generic sentence. So the real
verdict and the generic conclusion are BOTH available, one second apart, and
this module is what recovers the first and surfaces it in place of the second.

THIS IS THE FAILURE-PATH SIBLING of `_dispatcher_successful_terminal`, which
reads the same conclusion and answers the opposite question. That module asks
whether a SUCCESSFUL workflow is hiding behind the store loss and establishes
it from the newest structured checkpoint; this one asks what the engine's own
FAILURE verdict was. Both key on the one conclusion that admits it cannot
answer, which is why the sentence is named ONCE, here, and imported there: two
copies of a measured engine literal are two readings that can drift, and a
drifted copy would report the ordinary non-green for exactly the runs this rule
exists to read.

BOTH ACCOUNTS TRAVEL SEPARATELY INTO THE JOURNAL. The generic conclusion is not
noise to be discarded: it is what the engine actually recorded, it is what
`fabro ps -a` and every pruned-run surface will keep reporting, and an operator
reconciling this dispatch against those surfaces needs to see that the two
describe one run. So the journal row carries the conclusion and the recovered
verdict as distinct fields rather than one resolved cause, and the outcome
carries the recovered verdict alone, because the outcome's job is to name the
fault.

THE CLASSIFICATION FOLLOWS THE RECOVERED VERDICT, NOT THE WORKER EXIT. Where
the recovered line reports a deterministic failure cycle it also names the
signature the engine cycled on, and that signature carries its own node and
category -- so the ending is classified by the cycle it really was rather than
as a terminated run, which carries no signature at all and takes its category
from the generic conclusion. Where the recovered line is some other engine
workflow failure there is no signature to take and the arriving classification
stands; inventing one from the prose would put this module's own rendering
where the engine's grading belongs.

EVERY ARM THAT CANNOT MEASURE THE LOG LEAVES THE ENDING EXACTLY AS IT ARRIVED.
An export that failed, an export carrying no log, and a log carrying no engine
workflow-failure line are all reads that did not happen rather than evidence of
a clean worker exit. The fail-closed direction here is the ordinary non-green
the Dispatcher already reports: a recovered cause is strictly more information
than the generic sentence, so the cost of refusing is a triager reading the run
export by hand, while the cost of guessing would be a confident wrong fault
attributed to a node that never failed.

AND THE EXPORT IS ONLY TAKEN FOR THE ONE CONCLUSION THAT NEEDS IT. The
qualification is read off the outcome's own recorded cause before any engine
call, so an ordinary failed run -- which is almost every failed run -- spends
no export at all.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_failure import (
    fabro_failure_outcome_detail,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._fabro_port import (
    FabroFailureDetail,
    FabroInspectResult,
    fabro_port_for_plan,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
        CommandRunner,
        DispatchOutcome,
        JournalWriter,
    )

__all__: list[str] = [
    "WORKER_EXIT_BEFORE_TERMINAL_EVENT",
    "WORKER_EXIT_ENGINE_FAILURE_STAGE",
    "WorkerExitEngineFailure",
    "worker_exit_engine_failure_outcome",
]

# The engine's whole account of a run whose worker lost its canonical store.
# Measured, and shared with `_dispatcher_successful_terminal` rather than
# copied, for the reason the module docstring records.
WORKER_EXIT_BEFORE_TERMINAL_EVENT = (
    "Worker exited before emitting a terminal run event: exit status: 0"
)
WORKER_EXIT_ENGINE_FAILURE_STAGE = "fabro-worker-exit-engine-failure"

# The marker the engine's own workflow-failure line opens with. ANCHORED ON THE
# MARKER rather than on the log's line prefix: the timestamp and level format
# belong to the engine's logger and a pattern anchored at the start of the line
# could not match a build that reformats either, while reporting the same clean
# "no engine failure line" a genuinely silent log reports.
_ENGINE_FAILURE_MARKER = "Workflow run failed"
# The marker after which a deterministic failure cycle names the signature it
# cycled on. Read from the SAME recovered line rather than from a second pass
# over the log, so the surfaced cause and the classification can only ever
# describe one verdict.
_FAILURE_CYCLE_MARKER = "failure cycle detected: signature "
# A failure signature is `<node>|<category>|<reason>`, so the category is its
# middle field. A signature carrying fewer fields is not that shape, so it
# names no category rather than whatever happens to sit at that index.
_SIGNATURE_SEPARATOR = "|"
_SIGNATURE_CATEGORY_FIELD = 1
_SIGNATURE_FIELDS = 3
# The export path the measurement names. Read EXACTLY, and an absence reported
# as an absence: a glob over whatever else the export holds would be this
# module guessing at a file nobody has measured, and a verdict recovered from
# the wrong file is worse than none.
_MEASURED_LOG_NAME = "run.log"
_DUMP_TIMEOUT_SECONDS = 300.0


@dataclass(frozen=True, kw_only=True)
class WorkerExitEngineFailure:
    """The engine's recovered verdict, beside the conclusion it contradicts.

    BOTH accounts ride together because the journal records them separately:
    `conclusion_cause` is what the engine finalised the run with and is what
    every other surface will keep reporting, while `engine_failure` is the
    verdict it had already reached. A value carrying only the recovered line
    would leave an operator unable to tell that the two describe one run.

    `failure_cycle_signature` is the signature a recovered DETERMINISTIC
    FAILURE CYCLE names, and `None` for any other engine workflow failure --
    which is a reading rather than a defect: only a failure cycle names one,
    and manufacturing a signature for a line that does not carry one would put
    this module's own rendering where the engine's grading belongs.
    """

    conclusion_cause: str
    engine_failure: str
    failure_cycle_signature: str | None


def worker_exit_engine_failure_outcome(
    *,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    run_id: str | None,
    inspect: FabroInspectResult | None,
    terminal: DispatchOutcome | None,
) -> DispatchOutcome | None:
    """Surface the engine verdict behind a lost-store conclusion, or pass through.

    The arriving terminal is RETURNED UNCHANGED on every arm that does not
    qualify, so this reads as one step in the engine's terminal pipeline rather
    than as an override a caller has to decide whether to apply. An ordinary
    failed run leaves through the first three guards having spent nothing.
    """
    if terminal is None or run_id is None or inspect is None:
        return terminal
    if inspect.command.exit_code != 0 or inspect.status_kind != "failed":
        return terminal
    conclusion = terminal.fabro_failure_cause
    if conclusion != WORKER_EXIT_BEFORE_TERMINAL_EVENT:
        return terminal
    message = _engine_failure_message(
        text=_exported_log_text(plan=plan, runner=runner, run_id=run_id)
    )
    recovered = (
        None
        if message is None
        else WorkerExitEngineFailure(
            conclusion_cause=conclusion,
            engine_failure=message,
            failure_cycle_signature=_failure_cycle_signature(message=message),
        )
    )
    journal.append(
        record={
            "work_item_id": plan.work_item_id,
            "stage": WORKER_EXIT_ENGINE_FAILURE_STAGE,
            "run_id": run_id,
            # The engine's own conclusion, kept whatever the recovery found,
            # because it is the account every surface outside this dispatch
            # still reports. The recovered verdict is a SEPARATE field rather
            # than a replacement, so the row can be read against `fabro ps -a`
            # and seen to describe one run.
            "conclusion_cause": conclusion,
            "engine_failure": None if recovered is None else recovered.engine_failure,
            "failure_cycle_signature": (
                None if recovered is None else recovered.failure_cycle_signature
            ),
        }
    )
    if recovered is None:
        return terminal
    return _surfaced(terminal=terminal, recovered=recovered)


def _engine_failure_message(*, text: str) -> str | None:
    """The LAST engine workflow-failure line one log carries, from its marker on.

    The LAST rather than the first, because a log is append-ordered and the
    newest such line is the verdict the engine finalised on; an earlier one may
    belong to a cycle the engine went on to retry. The line is kept from the
    marker rather than whole, so the engine's own timestamp and level prefix
    stay out of a cause an operator reads.
    """
    found: str | None = None
    for line in text.splitlines():
        index = line.find(_ENGINE_FAILURE_MARKER)
        if index >= 0:
            found = line[index:].strip()
    return found


def _failure_cycle_signature(*, message: str) -> str | None:
    """The signature a recovered failure-cycle line names, else `None`.

    An EMPTY signature reads as none rather than as the empty string: the
    classification is what this value feeds, and an empty signature would be
    rendered on the ending's detail as a grading nobody recorded.
    """
    index = message.find(_FAILURE_CYCLE_MARKER)
    if index < 0:
        return None
    return message[index + len(_FAILURE_CYCLE_MARKER) :].strip() or None


def _signature_category(*, signature: str | None) -> str | None:
    """The category one failure signature names, or `None` for another shape."""
    if signature is None:
        return None
    fields = signature.split(_SIGNATURE_SEPARATOR)
    if len(fields) < _SIGNATURE_FIELDS:
        return None
    return fields[_SIGNATURE_CATEGORY_FIELD].strip() or None


def _exported_log_text(*, plan: DispatchPlan, runner: CommandRunner, run_id: str) -> str:
    """Export one run and read its log, or the empty text when either failed.

    The export goes through the port built from THIS dispatch's resolved
    factory, so the log read is about the server the run actually lived on. A
    reader that built its own port would ask whichever server a default named,
    which answers cleanly and about nothing.
    """
    port = fabro_port_for_plan(plan=plan, runner=runner)
    with tempfile.TemporaryDirectory(prefix=f"fabro-worker-exit-{run_id}-") as raw_dir:
        output_dir = Path(raw_dir)
        dumped = port.dump(
            run_id=run_id,
            output_dir=output_dir,
            timeout_seconds=_DUMP_TIMEOUT_SECONDS,
        ).command
        if dumped.exit_code != 0:
            return ""
        read = attempt(
            action=lambda: (output_dir / _MEASURED_LOG_NAME).read_text(
                encoding="utf-8", errors="replace"
            ),
            exceptions=(OSError,),
        )
    return "" if isinstance(read, AttemptFailure) else read


def _surfaced(*, terminal: DispatchOutcome, recovered: WorkerExitEngineFailure) -> DispatchOutcome:
    """The same ending, classified by the fault the engine had already named.

    THE ARRIVING CLASSIFICATION IS THE FALLBACK AND NEVER THE ANSWER WHERE A
    CYCLE WAS RECOVERED. A terminated run carries no signature at all and takes
    its category from the generic conclusion, so where the recovered verdict is
    a failure cycle both are replaced by what that cycle names -- and where it
    is not, the arriving pair stands, because there is nothing to replace it
    with that the engine recorded.
    """
    signature = recovered.failure_cycle_signature
    category = _signature_category(signature=signature)
    failure = FabroFailureDetail(
        cause=recovered.engine_failure,
        category=category if category is not None else terminal.fabro_failure_category,
        signature=signature if signature is not None else terminal.fabro_failure_signature,
    )
    return replace(
        terminal,
        detail=fabro_failure_outcome_detail(failure=failure, fallback=terminal.detail),
        fabro_failure_cause=failure.cause,
        fabro_failure_category=failure.category,
        fabro_failure_signature=failure.signature,
    )
