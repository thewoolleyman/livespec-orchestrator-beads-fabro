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
from dataclasses import dataclass
from datetime import datetime, timedelta

from livespec_orchestrator_beads_fabro.commands._acp_fallback_warning_ledger import (
    ingest_model_fallback_warning,
    primary_replacement_records,
    primary_success_clearance_records,
    read_model_fallback_warnings,
    selection_primary_attempts,
    selection_warning_records,
)
from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_inputs import (
    ReconcileInputs,
    port_for,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection_journal import (
    read_journal_records,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_stamp import (
    STAMP_JOURNAL_STAGE,
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
from livespec_orchestrator_beads_fabro.effects import (
    IsoDatetimeParseFailure,
    parse_iso_datetime,
)

__all__: list[str] = [
    "SELECTION_OUTCOMES_UNAVAILABLE_ATTEMPT_LIMIT",
    "SELECTION_OUTCOMES_UNAVAILABLE_STAGE",
    "SELECTION_REPLAY_WINDOW",
    "pass_selection_replays",
]

# The stage one unreadable run earns. Its own stage rather than an error row,
# because its SILENCE changes an answer: a run nobody could read leaves every
# standing warning in place, which at the attention lane is indistinguishable
# from a run that executed no fallback.
SELECTION_OUTCOMES_UNAVAILABLE_STAGE = "acp-selection-outcomes-unavailable"

# How far back from the journal's NEWEST stamp a stamp may sit and still be
# replayed. A week of this repository's own dispatch history: a run whose
# terminal node outcomes have not been read within that span will not become
# readable later, because factory run storage is pruned, so the window is this
# lane's reach rather than a throttle on it.
SELECTION_REPLAY_WINDOW = timedelta(days=7)

# How many times one run may be reported unavailable before this lane stops
# asking. The root timer drives a pass every ten minutes, so this is about two
# hours of asking -- long enough to ride out a factory restart or a transient
# outage, and a ceiling rather than one append per pass for ever.
SELECTION_OUTCOMES_UNAVAILABLE_ATTEMPT_LIMIT = 12

_INSPECT_TIMEOUT_SECONDS = 60.0


@dataclass(frozen=True, kw_only=True)
class _StampedRun:
    """One run this factory ran, and the work-item whose selection launched it."""

    run_id: str
    work_item_id: str


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
    for factory in factories:
        port = port_for(inputs=inputs, factory=factory)
        for target in _stamped_runs(records=records, factory=factory, inputs=inputs):
            _replay_one_run(
                inputs=inputs, factory=factory, port=port, target=target, records=records
            )
    _retire_replaced_primaries(inputs=inputs)


def _replay_one_run(
    *,
    inputs: ReconcileInputs,
    factory: FactoryTarget,
    port: FabroPort,
    target: _StampedRun,
    records: tuple[Mapping[str, object], ...],
) -> None:
    """Mint this run's warnings and apply the primary attempts it evidences."""
    outcomes = _node_outcomes(port=port, run_id=target.run_id)
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
        _ = ingest_model_fallback_warning(
            record=warning,
            ledger=read_model_fallback_warnings(journal_path=inputs.journaled.source_path),
            journal=inputs.journal,
        )
    for attempt in (
        selection_primary_attempts(
            records=records,
            work_item_id=target.work_item_id,
            run_id=target.run_id,
            outcomes=outcomes,
        )
        or ()
    ):
        for clearance in primary_success_clearance_records(
            ledger=read_model_fallback_warnings(journal_path=inputs.journaled.source_path),
            attempt=attempt,
        ):
            inputs.journal.append(record=clearance)


def _retire_replaced_primaries(*, inputs: ReconcileInputs) -> None:
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
        ledger=read_model_fallback_warnings(journal_path=inputs.journaled.source_path),
        primary_generations=resolve_acp_primary_generations(repo=inputs.repo),
    ):
        inputs.journal.append(record=replacement)


def _stamped_runs(
    *,
    records: tuple[Mapping[str, object], ...],
    factory: FactoryTarget,
    inputs: ReconcileInputs,
) -> tuple[_StampedRun, ...]:
    """Every run THIS factory ran that is still inside both of the lane's bounds.

    Keyed by run id so a re-stamped run is replayed once per pass; a stamp
    missing any of the three identities is passed over, because a run nothing
    joins to a selection cannot be evidence about one and guessing the join
    from journal order is exactly what the dispatch id replaced.

    The two bounds are the module docstring's, and the ORDER between them is
    not load-bearing -- a stamp outside either is passed over, and neither
    reading writes anything. They are applied here rather than inside
    `_replay_one_run` because the cost this bounds is the `fabro inspect` that
    function OPENS with: a ceiling read after the round trip has been spent
    would bound the journal and not the pass.
    """
    dated = _dated_stamps(records=records)
    if not dated:
        return ()
    horizon = max(instant for instant, _ in dated)
    attempts = _unavailable_attempts(records=records)
    found: dict[str, _StampedRun] = {}
    for instant, record in dated:
        target = _replay_target(record=record, factory=factory, inputs=inputs)
        if target is None or horizon - instant > SELECTION_REPLAY_WINDOW:
            continue
        if attempts.get(target.run_id, 0) >= SELECTION_OUTCOMES_UNAVAILABLE_ATTEMPT_LIMIT:
            continue
        found[target.run_id] = target
    return tuple(found.values())


def _replay_target(
    *,
    record: Mapping[str, object],
    factory: FactoryTarget,
    inputs: ReconcileInputs,
) -> _StampedRun | None:
    """One stamp as this factory's replay target, or `None` when it is not one."""
    if (
        record.get("dispatch_factory") != factory.name
        or record.get("dispatch_factory_server") != factory.server
    ):
        return None
    run_id = _text(value=record.get("run_id"))
    work_item_id = _text(value=record.get("work_item_id"))
    if run_id is None or work_item_id is None or _text(value=record.get("dispatch_id")) is None:
        return None
    if inputs.only_work_item_id is not None and work_item_id != inputs.only_work_item_id:
        return None
    return _StampedRun(run_id=run_id, work_item_id=work_item_id)


def _dated_stamps(
    *, records: tuple[Mapping[str, object], ...]
) -> tuple[tuple[datetime, Mapping[str, object]], ...]:
    """Every launch stamp this lane can DATE, paired with the instant it read.

    Across every factory, because the window's reference is the journal's own
    newest stamp: a per-factory horizon would let a quiet factory's whole
    history stay in the set for ever, which is the unbounded set arriving one
    factory at a time.
    """
    found: list[tuple[datetime, Mapping[str, object]]] = []
    for record in records:
        if record.get("stage") != STAMP_JOURNAL_STAGE:
            continue
        instant = _instant(value=record.get("at"))
        if instant is not None:
            found.append((instant, record))
    return tuple(found)


def _unavailable_attempts(*, records: tuple[Mapping[str, object], ...]) -> dict[str, int]:
    """How many times this lane has already reported each run unavailable."""
    counts: dict[str, int] = {}
    for record in records:
        run_id = _text(value=record.get("run_id"))
        if record.get("stage") != SELECTION_OUTCOMES_UNAVAILABLE_STAGE or run_id is None:
            continue
        counts[run_id] = counts.get(run_id, 0) + 1
    return counts


def _instant(*, value: object) -> datetime | None:
    """One journal instant as a comparable datetime, or `None` when unreadable.

    The journal writes the `%Y-%m-%dT%H:%M:%SZ` form and this runtime's
    `fromisoformat` does not accept the trailing `Z`, so the suffix is rewritten
    to the offset it means rather than stripped -- a naive datetime would raise
    on comparison against the aware ones every other instant here produces.
    """
    text = _text(value=value)
    if text is None:
        return None
    parsed = parse_iso_datetime(text=text.removesuffix("Z") + "+00:00")
    return None if isinstance(parsed, IsoDatetimeParseFailure) else parsed


def _node_outcomes(*, port: FabroPort, run_id: str) -> Mapping[str, Mapping[str, object]] | None:
    """One run's readable node outcomes, or `None` when the evidence is unavailable.

    The two-input reading, because the Petri engine records no `node_outcomes`
    at all and an empty map there is a record offering nothing to grade rather
    than a run that reached no node. Every arm that cannot measure answers
    `None`, which is what the caller records and retries.
    """
    inspect = port.inspect(run_id=run_id, timeout_seconds=_INSPECT_TIMEOUT_SECONDS)
    if inspect.command.exit_code != 0:
        return None
    record = fabro_inspect_record(payload=inspect.payload)
    if record is None:
        return None
    checkpoints = fabro_inspect_checkpoints(record=record)
    outcomes = fabro_node_outcomes(record=record, checkpoint=checkpoints[-1] if checkpoints else {})
    return outcomes or None


def _text(*, value: object) -> str | None:
    """Return a non-empty text identity, otherwise `None`."""
    return value.strip() if isinstance(value, str) and value.strip() else None
