"""Availability evidence derived from EVERY declared factory's own run records.

This is the READ half of the host-wide availability evidence: which factories
are asked, which of their runs are worth asking about, and what one run's
records say about the attempt that failed. `_acp_factory_hold_records` beneath
it owns ONE such attempt -- its identity, its bounded expiry, the typed hold it
stands for and the journal line that audits it -- and imports nothing from
here, which is what keeps the pair acyclic and every record decision
exercisable with no factory at all.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": "Availability evidence MUST be discoverable host-wide from the
factory's native run records, without an optional per-repository peer list.
Each recorded attempt MUST identify its resolved factory, repository, run,
node attempt, candidate entitlement, occurrence time, and typed availability
outcome. ... The participating factory instances are every factory declared
under `dispatcher.factories`; each Dispatcher MUST read availability evidence
from every declared factory, so an observation made by any repository's run on
a participating factory is visible to every repository that dispatches to it."

THE FACTORY IS THE AUTHORITY AND THE JOURNAL IS AN AUDIT REFERENCE. Nothing
here reads, writes, or can even be HANDED a repository-local dispatch journal,
which is how the same clause's "Hold observations and their retirement
evidence MUST remain reconstructible after any repository-local dispatch
journal is removed" holds structurally rather than carefully: there is no
parameter a journal could arrive in. The two reads this performs are the
factory's own `ps` and `inspect`, taken fresh per evaluation and kept nowhere,
which is what "No separate hold sidecar file, cache, or store MAY hold or
mirror this evidence" requires.

THE SCAN IS BOUNDED BY THE LISTING ROW, BEFORE ANY PER-RUN READ IS SPENT. A
factory serving this fleet listed 1626 rows on 2026-10-12, and a hold outlives
its attempt by exactly `HOLD_INTERVAL`, so a failure older than that window can
only re-derive a record that is already expired. The window test therefore
reads the ROW's own recorded instants, and the per-run `inspect` is spent only
on a failed row inside it. An implementation that inspected first would reach
the identical answer and would cost one round trip per historical failure on
every admission evaluation.

THE OCCURRENCE TIME IS THE RUN'S OWN COMPLETION INSTANT, derived from the two
figures the engine records on a run row -- `start_time` advanced by
`wall_time_ms` (measured 2026-10-12 on hp, engine 0.254.0: all 1626 rows carry
both; `tests/.../test_fabro_port_records_run_rows.py` transcribes one). A row
missing either is UNOBSERVABLE rather than dated from its start, and that is
the judgement call worth naming: a run that began four hours before it failed
reads as four hours old, so every hold it could mint would be born expired and
the scan would report a clean empty answer on exactly the outage it exists to
catch. `_dispatcher_reconcile_runs_grace` excludes `start_time` from its own
park measurement for the same reason.

THE ELIGIBLE CAUSE IS THE ONE A FOREIGN RUN'S RECORD CAN CARRY. Classification
through `_acp_failure_classifier` grades a candidate's OWN declared signatures,
and this repository holds no configuration for another repository's candidates,
so the typed outcome available here is the vendor-agnostic provider ceiling
`_fabro_port_permanent_failure` already recognises from the recorded cause
chain, attributed to the entitlement the run's own labels record. That is the
`quota` cause of Scenario 127's "A provider-limit failure releases the item and
re-dispatches it to the next eligible candidate"; why it is DOMAIN-scoped
belongs to the record leaf, which is where the scope is applied.

AN ENTITLEMENT KEY MAY ARRIVE DIGESTED, and it is read as it stands, exactly as
`_fabro_executed_candidate` reads it. `candidate_label_value` leaves an
identifier-shaped key verbatim and marks any other as a `sha256:` digest, so
evidence derived from a digested key names the digest. Reading it as it stands
is honest about what the run recorded; the digest is one-way so no decoding
exists, and broadening the key would name an entitlement nobody declared.

AN UNREADABLE ROW NAMES THE ENTITLEMENTS IT LEAVES UNCONFIRMED, which is what
turns "this source is unavailable" from a label into a decision a candidate
filter can act on. "It MAY continue with candidates whose availability evidence
is independently complete; it MUST NOT treat an unobserved candidate as
confirmed unheld." The two unobservable ROW arms both name a run, and a run row
carries the entitlement labels the dispatch stamped on it, so each one reports
EVERY availability key that run recorded -- the whole set rather than one,
because an unreadable record does not say which of its node attempts failed. An
unreadable LISTING names none: there are no rows, so there is no entitlement it
could be about, and that is why a refused listing is surfaced and retried
without emptying any chain. A reading that let it empty every chain would wedge
every dispatch in the fleet the moment one factory became unreachable.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol

from livespec_orchestrator_beads_fabro.commands._acp_factory_hold_records import (
    PROVIDER_LIMIT_CAUSE,
    FactoryHoldObservation,
    observation_hold,
)
from livespec_orchestrator_beads_fabro.commands._acp_hold_records import (
    HOLD_INTERVAL,
    AcpAvailabilityHold,
    parse_hold_instant,
)
from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_factories import (
    declared_factory_names,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_labels import REPOSITORY_LABEL_KEY
from livespec_orchestrator_beads_fabro.commands._fabro_executed_candidate import (
    executed_candidate_identity,
    recorded_availability_keys,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import (
    FabroRunSummary,
    fabro_failure_detail_from_payload,
)
from livespec_orchestrator_beads_fabro.commands._fabro_terminal_evidence import terminal_evidence

__all__: list[str] = [
    "EMPTY_FACTORY_HOLD_EVIDENCE",
    "INSPECT_UNREADABLE",
    "LISTING_UNREADABLE",
    "OCCURRENCE_UNREADABLE",
    "FactoryHoldEvidence",
    "FactoryRunReader",
    "factory_hold_evidence",
]

# Why one read contributed no evidence. Each is a failure to MEASURE, reported
# as such: "An unreadable or incomplete evidence source is unavailable, not an
# empty hold set."
LISTING_UNREADABLE = "factory-listing-unreadable"
OCCURRENCE_UNREADABLE = "attempt-occurrence-unreadable"
INSPECT_UNREADABLE = "run-record-unreadable"

_FAILED_STATUS_KIND = "failed"
_ISO_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

# The sub-second fraction an engine instant may carry. The Petri-era build
# stamps nine digits (`2026-10-08T12:34:14.182000000Z`), which no stdlib
# parser accepts, and a fifteen-minute window needs no sub-second resolution.
_SUBSECOND = re.compile(r"\.\d+")


class FactoryRunReader(Protocol):
    """The two factory-native reads this evidence is derived from.

    Both answer `None` for "this read could not be taken", never an empty
    result: an empty listing is a factory holding no runs, and an unreadable
    one says nothing at all about what it holds.
    """

    def list_runs(self, *, factory: str) -> tuple[FabroRunSummary, ...] | None:
        """Every run `fabro ps -a --json` reports, or `None` when unreadable."""
        ...

    def inspect_payload(self, *, factory: str, run_id: str) -> object | None:
        """One run's `fabro inspect --json` payload, or `None` when unreadable."""
        ...


@dataclass(frozen=True, kw_only=True)
class FactoryHoldEvidence:
    """What one host-wide read derived, and which reads could not be taken.

    `unconfirmed_keys` is the SECOND half of an unobservable entry and is a
    field rather than something a consumer derives from `unobservable`: the
    entry's shape belongs to this read, and a candidate filter interpreting one
    would be a second reader of a record it never produced.
    """

    observations: tuple[FactoryHoldObservation, ...] = ()
    unobservable: tuple[Mapping[str, object], ...] = ()
    unconfirmed_keys: frozenset[str] = frozenset()

    @property
    def holds(self) -> tuple[AcpAvailabilityHold, ...]:
        """Each observation as the live typed hold the candidate filter reads.

        No expiry filter is applied here, and that is deliberate rather than
        missing: `_row_evidence` has already bounded the scan to attempts
        inside `HOLD_INTERVAL`, so every observation that reached this point
        is one whose record still stands. A second test would be a second
        measurement of one window.
        """
        return tuple(observation_hold(observation=observation) for observation in self.observations)


EMPTY_FACTORY_HOLD_EVIDENCE = FactoryHoldEvidence()


def factory_hold_evidence(
    *, repo: Path, reader: FactoryRunReader, now_iso: str
) -> FactoryHoldEvidence:
    """Derive this host's live availability evidence from every declared factory.

    The factories are enumerated through `declared_factory_names`, which is the
    same enumeration the reconciler surveys: one list, so a factory this
    repository dispatches to can never be one it declines to read evidence
    from.
    """
    reads = tuple(
        _factory_evidence(factory=factory, reader=reader, now_iso=now_iso)
        for factory in declared_factory_names(block=dispatcher_block(cwd=repo))
    )
    return _merged(reads=reads)


def _factory_evidence(
    *, factory: str, reader: FactoryRunReader, now_iso: str
) -> FactoryHoldEvidence:
    """One participating factory's whole contribution, listing included."""
    rows = reader.list_runs(factory=factory)
    if rows is None:
        return FactoryHoldEvidence(
            unobservable=({"factory": factory, "reason": LISTING_UNREADABLE},)
        )
    return _merged(
        reads=tuple(
            _row_evidence(factory=factory, row=row, reader=reader, now_iso=now_iso) for row in rows
        )
    )


def _merged(*, reads: tuple[FactoryHoldEvidence, ...]) -> FactoryHoldEvidence:
    """Several reads as one, in read order, with their key sets unioned.

    Shared by both accumulation levels so a factory's rows and a host's
    factories combine identically -- and so a field added to the value cannot
    be threaded at one level and dropped at the other.
    """
    return FactoryHoldEvidence(
        observations=tuple(observation for read in reads for observation in read.observations),
        unobservable=tuple(entry for read in reads for entry in read.unobservable),
        unconfirmed_keys=frozenset(key for read in reads for key in read.unconfirmed_keys),
    )


def _row_evidence(
    *, factory: str, row: FabroRunSummary, reader: FactoryRunReader, now_iso: str
) -> FactoryHoldEvidence:
    """One listed run's contribution, spending an `inspect` only when it must."""
    if row.status_kind != _FAILED_STATUS_KIND:
        return EMPTY_FACTORY_HOLD_EVIDENCE
    instant = _attempt_instant(row=row)
    if instant is None:
        return _row_unreadable(factory=factory, row=row)
    if not _within_hold_window(occurred=instant, now_iso=now_iso):
        return EMPTY_FACTORY_HOLD_EVIDENCE
    payload = reader.inspect_payload(factory=factory, run_id=row.run_id)
    if payload is None:
        return _row_unreadable(factory=factory, row=row, reason=INSPECT_UNREADABLE)
    observation = _observation(
        factory=factory, row=row, payload=payload, occurred_at=instant.strftime(_ISO_FORMAT)
    )
    if observation is None:
        return EMPTY_FACTORY_HOLD_EVIDENCE
    return FactoryHoldEvidence(observations=(observation,))


def _row_unreadable(
    *, factory: str, row: FabroRunSummary, reason: str = OCCURRENCE_UNREADABLE
) -> FactoryHoldEvidence:
    """One unreadable row's whole contribution: the entry, and what it leaves open.

    The surfaced entry and the unconfirmed entitlements are produced together
    because they are one reading: an entry naming a run whose entitlements were
    dropped is a condition nothing downstream can act on, and a key set with no
    entry is a skip with no surfaced reason behind it.
    """
    return FactoryHoldEvidence(
        unobservable=({"factory": factory, "run_id": row.run_id, "reason": reason},),
        unconfirmed_keys=recorded_availability_keys(labels=row.labels),
    )


def _observation(
    *, factory: str, row: FabroRunSummary, payload: object, occurred_at: str
) -> FactoryHoldObservation | None:
    """One failed run's typed availability attempt, or `None` when it is not one.

    `None` covers both ways this is not evidence about a provider, and they
    stay un-surfaced because neither is a failure to measure: a failure the
    cause chain does not classify as a ceiling, and a failing node the run
    recorded no entitlement for -- which is the conservative legacy posture an
    identity-less adapter keeps, where there is no entitlement a typed record
    could be scoped by.
    """
    failure = fabro_failure_detail_from_payload(payload=payload)
    if failure is None or not failure.provider_usage_limit:
        return None
    evidence = terminal_evidence(payload=payload)
    executed = executed_candidate_identity(
        labels=row.labels, node=None if evidence is None else evidence.current_predecessor
    )
    if executed is None:
        return None
    return FactoryHoldObservation(
        factory=factory,
        repository=row.labels.get(REPOSITORY_LABEL_KEY),
        run_id=row.run_id,
        node_attempt=executed.node,
        availability_key=executed.availability_key,
        candidate_key=executed.candidate_key,
        cause=PROVIDER_LIMIT_CAUSE,
        occurred_at=occurred_at,
    )


def _attempt_instant(*, row: FabroRunSummary) -> datetime | None:
    """When this row's run COMPLETED, from the engine's own two figures.

    `None` when either figure is absent or unreadable -- see the module
    docstring for why a run's start is not substituted for its completion.
    """
    if row.start_time is None or row.wall_time_ms is None:
        return None
    started = parse_hold_instant(text=_SUBSECOND.sub("", row.start_time))
    if started is None:
        return None
    return started + timedelta(milliseconds=row.wall_time_ms)


def _within_hold_window(*, occurred: datetime, now_iso: str) -> bool:
    """Whether a record minted at this occurrence would still stand right now.

    An unreadable clock keeps the row IN the window, which costs one `inspect`
    and derives an observation the expiry test downstream still grades.
    Dropping it instead would let a caller's malformed clock send work at a
    live outage, which is the expensive direction.
    """
    now = parse_hold_instant(text=now_iso)
    if now is None:
        return True
    return occurred + HOLD_INTERVAL > now
