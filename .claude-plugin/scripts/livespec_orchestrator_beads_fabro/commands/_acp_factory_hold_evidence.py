"""Availability evidence derived from EVERY declared factory's own run records.

This is the READ half of the host-wide availability evidence: which factories
are asked, which of their runs are worth asking about, and what one run's
records say about the attempts it made -- the one that FAILED, which observes a
hold, and the ones that SUCCEEDED, which confirm an allowance and retire one.
`_acp_factory_hold_records` and `_acp_factory_success_records` beneath it own
ONE such attempt each -- identity, bounded expiry, the typed hold it stands for
and the journal line that audits it, on the failure side -- and neither imports
anything from here, which is what keeps the group acyclic and every record
decision exercisable with no factory at all.

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
only re-derive a record that is already expired -- and a SUCCESS whose run began
longer ago than that can only retire a record that has already expired on its
own. The window test therefore reads the ROW's own recorded instants, and the
single per-run `inspect` is spent only on a row at least one of the two arms
reaches. An implementation that inspected first would reach the identical answer
and would cost one round trip per historical run on every admission evaluation.

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

from livespec_orchestrator_beads_fabro.commands._acp_clearance_records import is_clearance_run
from livespec_orchestrator_beads_fabro.commands._acp_factory_clearance_evidence import (
    recorded_clearance,
)
from livespec_orchestrator_beads_fabro.commands._acp_factory_hold_records import (
    PROVIDER_LIMIT_CAUSE,
    FactoryHoldObservation,
    observation_hold,
)
from livespec_orchestrator_beads_fabro.commands._acp_factory_success_records import (
    FactorySuccessObservation,
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
from livespec_orchestrator_beads_fabro.commands._fabro_port_checkpoints import (
    fabro_inspect_checkpoints,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_node_outcomes import (
    fabro_node_outcomes,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import (
    FabroRunSummary,
    fabro_failure_detail_from_payload,
    fabro_inspect_record,
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
_SUCCEEDED_STATUS = "succeeded"
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

    `retired_observation_ids` is what the OPERATOR-CLEARANCE arm found, and it
    is reported rather than applied for the same reason the two halves of the
    retirement routes are applied at the union: a clearance recorded on the
    factory may name an observation this read derived, one the reading
    repository's own journal carries, or one neither holds any more, and only
    the union has all of them in hand. Reporting it here is what makes a
    clearance recorded by ANOTHER repository visible to this one at all.
    """

    observations: tuple[FactoryHoldObservation, ...] = ()
    successes: tuple[FactorySuccessObservation, ...] = ()
    unobservable: tuple[Mapping[str, object], ...] = ()
    unconfirmed_keys: frozenset[str] = frozenset()
    retired_observation_ids: frozenset[str] = frozenset()

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
        successes=tuple(success for read in reads for success in read.successes),
        unobservable=tuple(entry for read in reads for entry in read.unobservable),
        unconfirmed_keys=frozenset(key for read in reads for key in read.unconfirmed_keys),
        retired_observation_ids=frozenset(
            identifier for read in reads for identifier in read.retired_observation_ids
        ),
    )


def _row_evidence(
    *, factory: str, row: FabroRunSummary, reader: FactoryRunReader, now_iso: str
) -> FactoryHoldEvidence:
    """One listed run's contribution, spending at most ONE `inspect` on it.

    TWO ARMS, TWO WINDOW TESTS, ONE PER-RUN READ. The OBSERVATION arm is bounded
    by the attempt's completion instant, because that is when the allowance was
    spent; the CONFIRMATION arm is bounded by the run's START, because that is
    the instant the retirement rule compares against an observation and because
    a confirmation whose run began more than `HOLD_INTERVAL` ago can only retire
    a record that has already expired on its own. Both bounds are read off the
    LISTING ROW before any per-run read is spent, which is what keeps the scan
    affordable against the 1626 rows a factory serving this fleet listed.

    A row whose status is not failed therefore no longer returns early: a run
    that is still RUNNING can already carry a succeeded node attempt, and that
    attempt is a confirmation whether or not the run it belongs to ever
    finishes. The occurrence-unreadable surface stays scoped to a FAILED row,
    because an undatable success retires nothing and so is not a failure to
    measure anything a decision rests on.
    """
    failed_at = _observation_instant(row=row, now_iso=now_iso)
    if row.status_kind == _FAILED_STATUS_KIND and _attempt_instant(row=row) is None:
        return _row_unreadable(factory=factory, row=row)
    began_at = _confirmation_instant(row=row, now_iso=now_iso)
    if failed_at is None and began_at is None:
        return EMPTY_FACTORY_HOLD_EVIDENCE
    payload = reader.inspect_payload(factory=factory, run_id=row.run_id)
    if payload is None:
        return _row_unreadable(factory=factory, row=row, reason=INSPECT_UNREADABLE)
    return _read_evidence(
        factory=factory, row=row, payload=payload, failed_at=failed_at, began_at=began_at
    )


def _read_evidence(
    *,
    factory: str,
    row: FabroRunSummary,
    payload: object,
    failed_at: datetime | None,
    began_at: datetime | None,
) -> FactoryHoldEvidence:
    """What ONE per-run record says, graded on whichever arms its row reached."""
    observation = (
        None
        if failed_at is None
        else _observation(
            factory=factory, row=row, payload=payload, occurred_at=failed_at.strftime(_ISO_FORMAT)
        )
    )
    successes = (
        ()
        if began_at is None
        else _successes(
            factory=factory, row=row, payload=payload, started_at=began_at.strftime(_ISO_FORMAT)
        )
    )
    return FactoryHoldEvidence(
        observations=() if observation is None else (observation,),
        successes=successes,
        retired_observation_ids=_cleared_ids(row=row, payload=payload, began_at=began_at),
    )


def _cleared_ids(
    *, row: FabroRunSummary, payload: object, began_at: datetime | None
) -> frozenset[str]:
    """The observations one OPERATOR-CLEARANCE run's record names as cleared.

    Bounded by the run's START, exactly as the confirmation arm is -- but NOT
    any longer for the same reason, and the difference is worth stating because
    the original premise has been falsified by its own consumer. That premise
    was that a clearance older than `HOLD_INTERVAL` can only retire a record
    which has already expired on its own, and therefore retires nothing that
    decides anything. Since the post-expiry confirmation
    (`_acp_availability_confirmation`) an EXPIRED record is no longer inert: it
    carries an outstanding availability confirmation and GOVERNS selection, so
    such a clearance now does have an effect to be missed.

    The bound is kept anyway, on a cost argument rather than a vacuity one.
    Reading past the window costs one `fabro inspect` per historical clearance
    on EVERY admission evaluation, against a factory that listed 1626 rows for
    this fleet; what missing one costs is a single confirmation turn, since the
    ordinary route to satisfying a post-expiry confirmation is a successful
    attempt and not a clearance at all. That is the conservative direction, and
    the same asymmetry `_acp_availability_confirmation` already reasons from.
    A future editor who finds that trade has changed should widen the window
    here -- the arm is correct, its justification is simply no longer the one
    it was written with.

    Empty is what EVERY non-clearance row answers, and also what a clearance
    run whose record states nothing readable answers. The two are deliberately
    not distinguished: retirement is the destructive direction, so a record
    this read could not recover simply leaves the observation standing.
    """
    if began_at is None or not is_clearance_run(labels=row.labels):
        return frozenset()
    clearance = recorded_clearance(payload=payload)
    if clearance is None:
        return frozenset()
    return frozenset(clearance.observation_ids)


def _observation_instant(*, row: FabroRunSummary, now_iso: str) -> datetime | None:
    """When this row's FAILING attempt occurred, if it is still in window."""
    if row.status_kind != _FAILED_STATUS_KIND:
        return None
    instant = _attempt_instant(row=row)
    if instant is None or not _within_hold_window(occurred=instant, now_iso=now_iso):
        return None
    return instant


def _confirmation_instant(*, row: FabroRunSummary, now_iso: str) -> datetime | None:
    """When this row's run BEGAN, if a confirmation from it could still matter."""
    if row.start_time is None:
        return None
    started = parse_hold_instant(text=_SUBSECOND.sub("", row.start_time))
    if started is None or not _within_hold_window(occurred=started, now_iso=now_iso):
        return None
    return started


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


def _successes(
    *, factory: str, row: FabroRunSummary, payload: object, started_at: str
) -> tuple[FactorySuccessObservation, ...]:
    """Every SUCCEEDED node attempt one run's record carries, as confirmations.

    The grading is the port's own `fabro_node_outcomes`, which resolves BOTH
    inputs the two engines write -- the newest checkpoint's `node_outcomes`,
    else the record's own top-level `stages` map, visit-collapsed. A second
    reading here would make this and `_observation` above disagree about
    whether one record is readable at all.

    A succeeded node the run recorded NO entitlement for yields nothing, which
    is the same conservative legacy posture `_observation` keeps one function
    up: an identity-less adapter names no allowance, so its success confirms no
    allowance either. An unusable payload yields nothing for the same reason it
    yields no observation -- the record was read, and what it says is that it
    establishes no attempt.
    """
    record = fabro_inspect_record(payload=payload)
    if record is None:
        return ()
    checkpoints = fabro_inspect_checkpoints(record=record)
    outcomes = fabro_node_outcomes(record=record, checkpoint=checkpoints[-1] if checkpoints else {})
    return tuple(
        FactorySuccessObservation(
            factory=factory,
            repository=row.labels.get(REPOSITORY_LABEL_KEY),
            run_id=row.run_id,
            node_attempt=executed.node,
            availability_key=executed.availability_key,
            candidate_key=executed.candidate_key,
            started_at=started_at,
        )
        for stage, outcome in outcomes.items()
        if outcome.get("status") == _SUCCEEDED_STATUS
        and (executed := executed_candidate_identity(labels=row.labels, node=stage)) is not None
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
