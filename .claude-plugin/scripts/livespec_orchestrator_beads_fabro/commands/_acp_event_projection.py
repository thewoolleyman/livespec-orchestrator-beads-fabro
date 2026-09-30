"""Turning ONE run's fetched event stream into holds, warnings, or a fact.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": "The Dispatcher MUST fetch events from the run's resolved
factory target, project by stable event id, calculate holds from
occurrence time, and replay projection during reconciliation. Read
failure is not absence."

THIS MODULE NEVER FETCHES. It is handed what a fetch returned -- a
payload and an exit code -- so the whole decision table is testable
without a factory, and so the terminal-completion caller and the
reconciliation caller cannot drift into two different projections of the
same bytes. `_acp_projection_run` owns the port call.

THE FOUR FAILURE ARMS ARE CLASSIFIED HERE AND TYPED IMMEDIATELY. The
clause names them -- "the fetch fails, times out, returns unparseable
output, or the run cannot be found on the resolved target" -- and the
classification is the only place the adapter's own text is read at all.
What leaves this module is one closed token plus an exit code, because
every downstream record is bound by "no ... raw error, or unredacted
diagnostic".

ONE SUCCESSFUL READ CLEARS, ONE FAILED READ AGGREGATES, AND BOTH ARE
PER-NODE. The fact's identity carries a node, so a projection attempt is
scoped to the repository's fallback-enabled nodes and writes one line per
node either way. A repository with no fallback-enabled node has no such
node, projects nothing, and stays byte-identically on the v107 path --
the additive guarantee expressed as an empty loop rather than as a flag.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from livespec_orchestrator_beads_fabro.commands._acp_fallback_event_types import (
    AcpEventScan,
    event_failure,
)
from livespec_orchestrator_beads_fabro.commands._acp_fallback_events import scan_acp_events
from livespec_orchestrator_beads_fabro.commands._acp_fallback_warning_ledger import (
    ingest_model_fallback_warning,
    primary_attempts_from_scan,
    primary_replacement_records,
    primary_success_clearance_records,
    read_model_fallback_warnings,
)
from livespec_orchestrator_beads_fabro.commands._acp_fallback_warning_records import (
    model_fallback_warning_record,
)
from livespec_orchestrator_beads_fabro.commands._acp_hold_ledger import (
    ingest_hold_observation,
    read_acp_hold_ledger,
)
from livespec_orchestrator_beads_fabro.commands._acp_hold_records import (
    HOLD_EVIDENCE_KINDS,
    hold_observation_record,
)
from livespec_orchestrator_beads_fabro.commands._acp_projection_failure import (
    REASON_FETCH_FAILED,
    REASON_RUN_NOT_FOUND,
    REASON_TIMED_OUT,
    REASON_UNPARSEABLE,
    AcpProjectionFailureTarget,
    projection_failure_record,
    projection_success_record,
)

__all__: list[str] = [
    "AcpProjectionResult",
    "AcpProjectionTarget",
    "classify_events_failure",
    "project_fetched_events",
    "record_projection_failure",
]

# The evidence kind the hold writer accepts for a projected event. Read off
# the closed set rather than spelled again, so a rename there cannot leave
# this call site silently refusing every observation.
_EVIDENCE_KIND = HOLD_EVIDENCE_KINDS[0]

_TIMEOUT_EXIT_CODE = 124

# The hold ledger's read takes a `now` only to decide EXPIRY, and this read
# wants none: dedupe is against every observation the journal has ever
# carried, which `read_acp_hold_ledger` reports whatever the clock says. A
# fixed sentinel therefore makes the ingest independent of wall time --
# the same property "expiry is computed from occurrence time and never
# from ingestion" asks of the writer.
_EPOCH_SENTINEL = "1970-01-01T00:00:00Z"

# The adapter phrases that mean "this factory has no such run". Matched
# case-folded against the command's own output HERE and nowhere else; only
# the resulting token is ever recorded.
_RUN_ABSENT_MARKERS: tuple[str, ...] = ("not found", "no such run", "unknown run")


class _Journal(Protocol):
    def append(self, *, record: dict[str, object]) -> None:
        """Persist one journal record."""
        ...


@dataclass(frozen=True, kw_only=True)
class AcpProjectionTarget:
    """Which run, on which factory, for which repository's fallback nodes.

    `nodes` is DERIVED from `primary_generations` rather than carried
    beside it, so the set of nodes a projection failure is reported for
    and the set its supersede pass compares generations over are the same
    set by construction. Two independent fields would let a caller report
    a fact for a node whose generation it never checked.
    """

    repo_name: str
    run_id: str
    work_item_id: str
    factory_name: str
    factory_server_url: str
    primary_generations: Mapping[str, str]
    succeeded_nodes: frozenset[str] = frozenset()

    @property
    def nodes(self) -> tuple[str, ...]:
        """Every fallback-enabled node of this repository, in stable order."""
        return tuple(sorted(self.primary_generations))


@dataclass(frozen=True, kw_only=True)
class AcpProjectionResult:
    """What one projection attempt wrote, or why it wrote a failure instead."""

    holds: int = 0
    warnings: int = 0
    cleared: int = 0
    superseded: int = 0
    unobservable: int = 0
    nodes: tuple[str, ...] = ()
    reason: str | None = None

    @property
    def read(self) -> bool:
        """Whether the run's event stream was actually read."""
        return self.reason is None


def classify_events_failure(*, exit_code: int, output: str, payload: object) -> str | None:
    """The typed reason this fetch cannot be projected, or `None` when it can.

    Order matters. The timeout exit code is tested before the generic
    non-zero arm because a timed-out read is the one failure an operator
    can act on differently -- it says the factory is reachable and slow,
    not that the run is gone.
    """
    if exit_code == _TIMEOUT_EXIT_CODE:
        return REASON_TIMED_OUT
    if exit_code != 0:
        folded = output.casefold()
        if any(marker in folded for marker in _RUN_ABSENT_MARKERS):
            return REASON_RUN_NOT_FOUND
        return REASON_FETCH_FAILED
    if payload is None:
        return REASON_UNPARSEABLE
    return None


def record_projection_failure(
    *, target: AcpProjectionTarget, reason: str, exit_code: int | None, journal: _Journal
) -> AcpProjectionResult:
    """Append one failure line per fallback-enabled node of this run."""
    for node in target.nodes:
        journal.append(
            record=projection_failure_record(
                target=AcpProjectionFailureTarget(
                    repo=target.repo_name,
                    run_id=target.run_id,
                    node=node,
                    factory_name=target.factory_name,
                    factory_server_url=target.factory_server_url,
                ),
                reason=reason,
                exit_code=exit_code,
            )
        )
    return AcpProjectionResult(nodes=target.nodes, reason=reason)


def project_fetched_events(
    *,
    target: AcpProjectionTarget,
    payload: object,
    journal: _Journal,
    journal_path: Path | None,
) -> AcpProjectionResult:
    """Project one run's readable event stream, idempotently.

    The scan's own refusal is routed to the unparseable arm rather than
    raised: a payload that parsed as JSON but is not an event array is
    still "returns unparseable output" as far as the contract's failure
    fact is concerned, and the alternative -- treating it as an empty
    stream -- is precisely the read-failure-as-absence the clause forbids.
    """
    scanned = scan_acp_events(payload=payload)
    if isinstance(scanned, str):
        return record_projection_failure(
            target=target, reason=REASON_UNPARSEABLE, exit_code=0, journal=journal
        )
    ingested = _ingest_scan(target=target, scan=scanned, journal=journal, journal_path=journal_path)
    written = _retire_warnings(
        target=target,
        scan=scanned,
        ingested=ingested,
        journal=journal,
        journal_path=journal_path,
    )
    for node in target.nodes:
        journal.append(
            record=projection_success_record(
                repo=target.repo_name,
                run_id=target.run_id,
                node=node,
                projected=written.holds,
                unobservable=written.unobservable,
            )
        )
    return written


def _ingest_scan(
    *,
    target: AcpProjectionTarget,
    scan: AcpEventScan,
    journal: _Journal,
    journal_path: Path | None,
) -> AcpProjectionResult:
    """Append every new hold observation and warning this scan yields.

    Both ledgers are read ONCE, before the loop, and the dedupe sets are
    carried forward by the ingest helpers themselves. Re-reading per event
    would make a run emitting two transitions cost two folds of the whole
    journal, and would still not change the outcome -- first write wins
    either way.
    """
    holds = read_acp_hold_ledger(journal_path=journal_path, now_iso=_EPOCH_SENTINEL)
    warnings = read_model_fallback_warnings(journal_path=journal_path)
    appended_holds = 0
    appended_warnings = 0
    for event in scan.events:
        record = hold_observation_record(
            failure=event_failure(event=event),
            evidence_kind=_EVIDENCE_KIND,
            evidence_id=event.event_id,
            occurred_at=event.occurred_at,
            work_item_id=target.work_item_id,
            node=event.node,
        )
        if isinstance(record, dict) and ingest_hold_observation(
            record=record, ledger=holds, journal=journal
        ):
            appended_holds += 1
        warning = model_fallback_warning_record(event=event, work_item_id=target.work_item_id)
        if warning is not None and ingest_model_fallback_warning(
            record=warning, ledger=warnings, journal=journal
        ):
            appended_warnings += 1
    return AcpProjectionResult(
        holds=appended_holds,
        warnings=appended_warnings,
        unobservable=len(scan.unobservable),
        nodes=target.nodes,
    )


def _retire_warnings(
    *,
    target: AcpProjectionTarget,
    scan: AcpEventScan,
    ingested: AcpProjectionResult,
    journal: _Journal,
    journal_path: Path | None,
) -> AcpProjectionResult:
    """Append every warning retirement this run and this configuration justify.

    The ledger is re-read AFTER ingestion on purpose: a warning this very
    run just wrote is part of the live set the clearance rule is applied
    to, and leaving it out would let a stale in-memory ledger decide the
    lifecycle. It changes no outcome for that warning -- the primary that
    fell over started BEFORE it -- but making the read the authority is
    what keeps that a measured fact rather than an assumption.
    """
    ledger = read_model_fallback_warnings(journal_path=journal_path)
    cleared = 0
    for attempt in primary_attempts_from_scan(scan=scan, succeeded_nodes=target.succeeded_nodes):
        for record in primary_success_clearance_records(ledger=ledger, attempt=attempt):
            journal.append(record=record)
            cleared += 1
    superseded = primary_replacement_records(
        ledger=ledger, primary_generations=target.primary_generations
    )
    for record in superseded:
        journal.append(record=record)
    return AcpProjectionResult(
        holds=ingested.holds,
        warnings=ingested.warnings,
        cleared=cleared,
        superseded=len(superseded),
        unobservable=ingested.unobservable,
        nodes=target.nodes,
    )
