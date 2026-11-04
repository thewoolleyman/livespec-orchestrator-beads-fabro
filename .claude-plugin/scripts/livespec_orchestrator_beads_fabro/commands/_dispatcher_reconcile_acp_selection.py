"""Replay each dispatch's own ACP selection against the run it launched.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" requires reconciliation to "replay selection-to-execution
observation idempotently using factory, run, node attempt and selection
identity". All four keys are already recorded and none of them is derived
here: the `dispatch-run-stamp` record names the FACTORY and the RUN, the
engine's own node outcomes name the NODE ATTEMPT, and the
`acp-node-selection` record names the SELECTION IDENTITY -- joined to its run
through the immutable `dispatch_id` both records carry, which is the only key
that survives a same-item re-dispatch.

IT IS A LANE OF ITS OWN rather than a step of the orphan path, exactly as the
container sweep is. The orphan join considers only NON-TERMINAL runs, while
the evidence this replay reads belongs to runs that have already ENDED, so a
replay folded into the orphan loop would never see one. It also addresses each
surveyed factory's own server, for `port_for`'s reason: a replay that read
every stamped run through one client would get a clean, plausible, empty
answer from any factory running a different engine.

IDEMPOTENCE IS THE LEDGER'S, NOT A FLAG HELD HERE. Every append goes through
`ingest_model_fallback_warning`, which dedupes on the warning id -- a digest of
the selection identity and the node -- so a run replayed on several passes
appends exactly one record. The ledger is re-read before each item's ingest
rather than once per pass, because this pass writes to the very file the ledger
is folded from and a snapshot taken before the first append cannot see the
second.

THE REPLAY SET IS BOUNDED, AND BOTH BOUNDS ARE READ OFF THE JOURNAL. Idempotence
makes a repeat append harmless; it does nothing about the COST of taking the
reading again, and this lane is driven by a timer every ten minutes. An unbounded
set re-inspects every stamp the journal has ever carried, so per-pass cost grows
monotonically with the repository's lifetime dispatch count, for ever -- and the
growth feeds back, because the journal is the same file this lane re-reads per
warning and per attempt. So:

- A stamp older than `SELECTION_REPLAY_WINDOW`, measured from the NEWEST stamp
  the journal carries, is passed over. The reference is the journal's own
  newest stamp rather than a wall clock, so the window is a span of the
  repository's own dispatch history and a pass takes the same decision whenever
  it runs. The window bounds the SET; a burst is not truncated by it, because
  every stamp of one burst sits within minutes of that burst's own newest.
- A run this lane has already reported unavailable
  `SELECTION_OUTCOMES_UNAVAILABLE_ATTEMPT_LIMIT` times is passed over. Factory
  run storage is pruned, so a historical run becomes PERMANENTLY unreadable, and
  the clause's retry has to be a retry rather than one append per pass for the
  rest of the journal's life. The standing warning is untouched either way --
  the ceiling stops the lane ASKING, and never clears anything.

- A run whose node outcomes this lane has already read WHILE THE RUN WAS TERMINAL
  is passed over. A terminal run's outcomes cannot change, so the reading taken
  once is the reading, and a ten-minute timer re-inspecting it for the whole
  window measured 159 `fabro inspect` calls and 25 minutes for one pass, 151 of
  them for runs that had already ended. The fact that the read happened is
  journaled as `SELECTION_OUTCOMES_READ_STAGE`, so the skip survives the fresh
  process every timer tick starts. The record is written only for a run the
  engine itself reports terminal: a run still moving, or whose status cannot be
  recognised as terminal, is read again, because the extra read is the
  conservative direction. A run whose outcomes were unreadable earns the
  unavailable record instead and is retried under the ceiling above, so this
  skip never narrows that retry.

- The `fabro inspect` calls that remain are issued CONCURRENTLY, at most
  `SELECTION_INSPECT_WORKERS` at a time. Each is an independent read of one
  run, about nine seconds apiece when measured, so taking them one after another
  made the pass's duration the sum of its round trips. Only the READS overlap:
  every journal append and ledger fold still happens in the pass's own thread,
  in the order the stamps were found, so the lane's idempotence argument above
  is untouched and no two threads ever write the journal.

A stamp whose own `at` cannot be read is passed over too, because the window is
what bounds this set and a record the bound cannot PLACE would otherwise be
replayed for ever. A journal in which NO stamp can be dated establishes no
window at all and replays nothing, which is the same answer as having no stamps.

UNAVAILABLE EVIDENCE IS RECORDED AND RETRIED, NEVER RESOLVED. A run whose node
outcomes cannot be read says nothing about whether a fallback executed, so the
pass journals that it could not look and leaves every standing warning alone;
the next pass asks again. The alternative -- reading an unreadable run as a run
that executed nothing -- would clear a warning on the strength of a failed
read, which is the one direction the clause calls out.

THE SUPERSEDE PASS RUNS ONCE PER RECONCILIATION, NOT ONCE PER FACTORY. It is
driven by the repository's CURRENT primaries rather than by any run, so a
per-factory call would append the identical retirement once per configured
factory and make one replacement read as several.

A DRY RUN REPLAYS NOTHING AT ALL. Every output of this lane is a journal
append, so a pass asked only to report has nothing it could legitimately do
here -- and a read spent against a factory would be a round trip taken on
behalf of a decision nobody is going to record.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._acp_fallback_warning_ledger import (
    ModelFallbackWarningLedger,
    fold_model_fallback_warnings,
    ingest_model_fallback_warning,
    ledger_with_appended,
    primary_replacement_records,
    primary_success_clearance_records,
    selection_primary_attempts,
    selection_warning_records,
)
from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import JournalWriter
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_acp_selection_stamps import (
    SELECTION_OUTCOMES_READ_STAGE,
    SELECTION_OUTCOMES_UNAVAILABLE_STAGE,
    StampedRun,
    stamped_runs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_inputs import (
    ReconcileInputs,
    port_for,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection_journal import (
    read_journal_records,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort
from livespec_orchestrator_beads_fabro.commands._fabro_port_checkpoints import (
    fabro_inspect_checkpoints,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_node_outcomes import (
    fabro_node_outcomes,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import (
    fabro_inspect_record,
)

__all__: list[str] = [
    "SELECTION_INSPECT_WORKERS",
    "pass_selection_replays",
]

# The status kinds after which a run's node outcomes are final. Deliberately an
# explicit list rather than the complement of the non-terminal kinds: a status
# this lane does not recognise must read as not terminal and be read again.
_TERMINAL_STATUS_KINDS = frozenset({"cancelled", "canceled", "dead", "failed", "succeeded"})

# How many `fabro inspect` calls one pass may have in flight at once. The reads
# are independent and each spends nearly all its time waiting on the factory, so
# the bound exists to keep one pass from flooding a shared factory server, and is
# not a throttle on this lane's own work.
SELECTION_INSPECT_WORKERS = 8

_INSPECT_TIMEOUT_SECONDS = 60.0


@dataclass(frozen=True, kw_only=True)
class _Reading:
    """One inspect of one run: its readable outcomes, and whether they are final."""

    outcomes: Mapping[str, Mapping[str, object]] | None
    terminal: bool


@dataclass(frozen=True, kw_only=True)
class _ReplayJob:
    """One stamped run to read, with the factory and port that ran it."""

    factory: FactoryTarget
    port: FabroPort
    target: StampedRun


def pass_selection_replays(
    *,
    inputs: ReconcileInputs,
    factories: Sequence[FactoryTarget],
    dry_run: bool,
) -> None:
    """Replay every surveyed factory's stamped runs, then retire replaced primaries.

    The journal source carried by the reconciliation input is the same snapshot
    that attributed the factory pass. A pathless in-memory input has no durable
    selection history to join, so it deliberately does nothing rather than
    guessing from an item or from journal order.
    """
    if dry_run:
        return
    records = read_journal_records(journal_path=inputs.journaled.source_path)
    if not records:
        return
    ledger = _PassLedger(
        journal=inputs.journal, ledger=fold_model_fallback_warnings(records=records)
    )
    jobs: list[_ReplayJob] = []
    for factory in factories:
        port = port_for(inputs=inputs, factory=factory)
        jobs.extend(
            _ReplayJob(factory=factory, port=port, target=target)
            for target in stamped_runs(
                records=records, factory=factory, only_work_item_id=inputs.only_work_item_id
            )
        )
    with ThreadPoolExecutor(max_workers=SELECTION_INSPECT_WORKERS) as pool:
        pending = [pool.submit(_read_run, port=job.port, run_id=job.target.run_id) for job in jobs]
        for job, reading in zip(jobs, pending, strict=True):
            _replay_one_run(
                inputs=inputs,
                factory=job.factory,
                target=job.target,
                reading=reading.result(),
                records=records,
                ledger=ledger,
            )
    _retire_replaced_primaries(inputs=inputs, ledger=ledger)


@dataclass(kw_only=True)
class _PassLedger:
    """The pass's warning ledger, kept current with every record the pass appends.

    Folded ONCE from the records the pass already read, instead of re-reading
    the journal per warning and per attempt (bd-ib-6bbcda).
    """

    journal: JournalWriter
    ledger: ModelFallbackWarningLedger

    def append(self, *, record: dict[str, object]) -> None:
        self.journal.append(record=record)
        self.ledger = ledger_with_appended(ledger=self.ledger, record=record)


def _replay_one_run(
    *,
    inputs: ReconcileInputs,
    factory: FactoryTarget,
    target: StampedRun,
    reading: _Reading,
    records: tuple[Mapping[str, object], ...],
    ledger: _PassLedger,
) -> None:
    """Mint this run's warnings and apply the primary attempts it evidences."""
    outcomes = reading.outcomes
    if outcomes is None:
        inputs.journal.append(
            record={
                "stage": SELECTION_OUTCOMES_UNAVAILABLE_STAGE,
                "work_item_id": target.work_item_id,
                "run_id": target.run_id,
                "factory_name": factory.name,
                "factory_server_url": factory.server,
            }
        )
        return
    for warning in (
        selection_warning_records(
            records=records,
            work_item_id=target.work_item_id,
            run_id=target.run_id,
            outcomes=outcomes,
        )
        or ()
    ):
        _ = ingest_model_fallback_warning(record=warning, ledger=ledger.ledger, journal=ledger)
    for attempt in (
        selection_primary_attempts(
            records=records,
            work_item_id=target.work_item_id,
            run_id=target.run_id,
            outcomes=outcomes,
        )
        or ()
    ):
        for clearance in primary_success_clearance_records(ledger=ledger.ledger, attempt=attempt):
            ledger.append(record=clearance)
    if reading.terminal:
        inputs.journal.append(
            record={
                "stage": SELECTION_OUTCOMES_READ_STAGE,
                "work_item_id": target.work_item_id,
                "run_id": target.run_id,
                "factory_name": factory.name,
                "factory_server_url": factory.server,
            }
        )


def _retire_replaced_primaries(*, inputs: ReconcileInputs, ledger: _PassLedger) -> None:
    """Supersede every warning whose primary this repository has since replaced.

    The resolution is lazy and fail-soft by construction, so a repository
    declaring no fallback metadata resolves the empty mapping and retires
    nothing -- which is also the conservative answer for a configuration that
    will not resolve, because this runs AFTER the work it follows and refusing
    here would strand the evidence an operator still needs.
    """
    # Imported lazily because `_dispatcher_acp_preflight` sits on a
    # module-level cycle through `_dispatcher_engine`, which reaches the
    # terminal dispositions and one of those reaches this lane back. The
    # reconciliation input seam exists for the same cycle; this is the one read
    # it does not carry, because the mapping is a fact about the repository
    # rather than something a pass is handed.
    from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_preflight import (
        resolve_acp_primary_generations,
    )

    for replacement in primary_replacement_records(
        ledger=ledger.ledger,
        primary_generations=resolve_acp_primary_generations(repo=inputs.repo),
    ):
        ledger.append(record=replacement)


def _read_run(*, port: FabroPort, run_id: str) -> _Reading:
    """One run's readable node outcomes (`None` when unavailable) and its finality.

    The two-input reading, because the Petri engine records no `node_outcomes`
    at all and an empty map there is a record offering nothing to grade rather
    than a run that reached no node. Every arm that cannot measure answers
    `None` outcomes, which is what the caller records and retries.
    """
    inspect = port.inspect(run_id=run_id, timeout_seconds=_INSPECT_TIMEOUT_SECONDS)
    if inspect.command.exit_code != 0:
        return _Reading(outcomes=None, terminal=False)
    record = fabro_inspect_record(payload=inspect.payload)
    if record is None:
        return _Reading(outcomes=None, terminal=False)
    checkpoints = fabro_inspect_checkpoints(record=record)
    outcomes = fabro_node_outcomes(record=record, checkpoint=checkpoints[-1] if checkpoints else {})
    return _Reading(
        outcomes=outcomes or None, terminal=inspect.status_kind in _TERMINAL_STATUS_KINDS
    )
