"""Availability evidence derived from EVERY declared factory's own run records.

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
re-dispatches it to the next eligible candidate", and it is DOMAIN-scoped for
the reason the built-in quota signatures are: the spent allowance belongs to
the account, so holding one candidate would leave every sibling on the same
provider dispatching into the same refusal.

AN ENTITLEMENT KEY MAY ARRIVE DIGESTED, and it is read as it stands, exactly as
`_fabro_executed_candidate` reads it. `candidate_label_value` leaves an
identifier-shaped key verbatim and marks any other as a `sha256:` digest, so
evidence derived from a digested key names the digest. Reading it as it stands
is honest about what the run recorded; the digest is one-way so no decoding
exists, and broadening the key would name an entitlement nobody declared.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol

from livespec_orchestrator_beads_fabro.commands._acp_failure_classifier import (
    DOMAIN_SCOPE,
    AcpAvailabilityFailure,
)
from livespec_orchestrator_beads_fabro.commands._acp_hold_records import (
    HOLD_EVIDENCE_KINDS,
    HOLD_INTERVAL,
    HOLD_SCHEMA_VERSION,
    AcpAvailabilityHold,
    hold_observation_record,
    observation_id,
    parse_hold_instant,
)
from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_factories import (
    declared_factory_names,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_labels import REPOSITORY_LABEL_KEY
from livespec_orchestrator_beads_fabro.commands._fabro_executed_candidate import (
    executed_candidate_identity,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import (
    FabroRunSummary,
    fabro_failure_detail_from_payload,
)
from livespec_orchestrator_beads_fabro.commands._fabro_terminal_evidence import terminal_evidence

__all__: list[str] = [
    "AUDIT_REFERENCE_KEY",
    "EMPTY_FACTORY_HOLD_EVIDENCE",
    "FACTORY_EVIDENCE_KIND",
    "FACTORY_EVIDENCE_SOURCE",
    "INSPECT_UNREADABLE",
    "LISTING_UNREADABLE",
    "OCCURRENCE_UNREADABLE",
    "PROVIDER_LIMIT_CAUSE",
    "FactoryHoldEvidence",
    "FactoryHoldObservation",
    "FactoryRunReader",
    "attempt_expiry",
    "factory_hold_evidence",
    "factory_hold_observation_record",
    "observation_hold",
]

# The journal key a derived record's AUDIT reference lands under. The journal
# is never the authority for these holds, so the line names the factory run
# the record can be re-derived from rather than standing on its own.
AUDIT_REFERENCE_KEY = "audit_reference"

# The evidence kind a TERMINAL-failure-derived hold is minted under. Read off
# the hold writer's own closed set rather than spelled again, exactly as
# `_acp_event_projection` reads the failover-event kind beside it, so a rename
# there cannot leave this call site silently naming a kind that writer refuses.
FACTORY_EVIDENCE_KIND = HOLD_EVIDENCE_KINDS[1]

# The diagnostic channel this verdict was read off: the engine's own recorded
# cause chain for the failing node attempt.
FACTORY_EVIDENCE_SOURCE = "process.terminal_diagnostic"

# The ratified cause a spent provider allowance carries, identical to the one
# the built-in provider-limit signatures declare.
PROVIDER_LIMIT_CAUSE = "quota"

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
class FactoryHoldObservation:
    """One availability attempt, as the factory's own records identify it.

    The six identifying fields are the clause's own list: the resolved
    `factory`, the `repository` whose dispatch ran, the `run_id`, the
    `node_attempt`, the candidate entitlement as the
    `(availability_key, candidate_key)` pair, and the `occurred_at` instant.
    `repository` is OPTIONAL because an `omitempty`-sparse row carries no
    repository label, and a derived name would report a dispatch nobody made.
    """

    factory: str
    repository: str | None
    run_id: str
    node_attempt: str
    availability_key: str
    candidate_key: str | None
    cause: str
    occurred_at: str

    @property
    def run_reference(self) -> str:
        """The factory run reference this observation is re-derivable from.

        It is also what makes the derived observation id STABLE: the id
        digests its evidence, and this reference is a fact of the FACTORY's
        record rather than of the reading, so two Dispatchers deriving one
        attempt mint one id instead of two records of the same outage.
        """
        return f"{self.factory}:{self.run_id}:{self.node_attempt}"

    @property
    def expires_at(self) -> str:
        """The bounded expiry this attempt's OCCURRENCE time implies.

        Derived from `occurred_at` alone, with no clock anywhere in reach --
        the same property `hold_observation_record` holds by taking no clock
        parameter, and it matters more here: this evidence is re-read from the
        factory on EVERY admission evaluation, so an expiry computed from the
        reading would make one four-minute outage stand for as long as anyone
        kept looking at it.
        """
        return attempt_expiry(occurred_at=self.occurred_at)


@dataclass(frozen=True, kw_only=True)
class FactoryHoldEvidence:
    """What one host-wide read derived, and which reads could not be taken."""

    observations: tuple[FactoryHoldObservation, ...] = ()
    unobservable: tuple[Mapping[str, object], ...] = ()

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


def attempt_expiry(*, occurred_at: str) -> str:
    """One attempt's bounded expiry, or the occurrence itself when unreadable.

    The bound is the SAME `HOLD_INTERVAL` a journal-projected observation
    takes, read off the hold writer rather than respelled: the two valves
    observe the same kind of outage on the same factory, and a derived hold
    that outlived its projected counterpart would be a behaviour change
    nobody ratified.

    An occurrence nobody can read is not an instant fifteen minutes can be
    added to, so it is carried through UNCHANGED rather than replaced: both of
    the record's instants then say the same unreadable thing, where a computed
    substitute would date the record from the READING. Do NOT mistake that arm
    for a safety net -- `hold_expired` cannot read such a record either and
    reports it as standing. What keeps it harmless is that no derivation here
    can build one: `factory_hold_evidence` formats every `occurred_at` from an
    instant it has already parsed.
    """
    occurred = parse_hold_instant(text=occurred_at)
    if occurred is None:
        return occurred_at
    return (occurred + HOLD_INTERVAL).strftime(_ISO_FORMAT)


def observation_hold(*, observation: FactoryHoldObservation) -> AcpAvailabilityHold:
    """The live schema-v1 hold one derived observation stands for."""
    failure = _observation_failure(observation=observation)
    return AcpAvailabilityHold(
        schema_version=HOLD_SCHEMA_VERSION,
        observation_id=observation_id(
            evidence_kind=FACTORY_EVIDENCE_KIND,
            evidence_id=observation.run_reference,
            failure=failure,
        ),
        scope=failure.scope,
        hold_key=failure.hold_key,
        candidate_key=failure.candidate_key,
        cause=failure.cause,
        occurred_at=observation.occurred_at,
        expires_at=observation.expires_at,
    )


def factory_hold_observation_record(
    *, observation: FactoryHoldObservation, work_item_id: str
) -> dict[str, object] | str:
    """The appendable AUDIT line one derived observation writes, or a refusal.

    "Dispatch journals MAY record audit references but MUST NOT be the sole
    authority for holds." The line is therefore the ORDINARY v1 observation --
    it reads back through `parse_hold_record` to the very hold the evidence
    stands for -- plus the factory run it was derived from, so a reader of the
    journal is pointed at the authority rather than left holding the only
    copy.

    The writer's own refusal is RETURNED rather than swallowed into a record.
    A line whose occurrence nobody can read is an audit reference to nothing:
    the hold it claims to mirror cannot be re-derived from it, which is the
    one property this copy exists to preserve.
    """
    record = hold_observation_record(
        failure=_observation_failure(observation=observation),
        evidence_kind=FACTORY_EVIDENCE_KIND,
        evidence_id=observation.run_reference,
        occurred_at=observation.occurred_at,
        work_item_id=work_item_id,
        node=observation.node_attempt,
    )
    if isinstance(record, str):
        return record
    return {**record, AUDIT_REFERENCE_KEY: observation.run_reference}


def _observation_failure(*, observation: FactoryHoldObservation) -> AcpAvailabilityFailure:
    """The typed verdict this observation carries, scoped to its provider domain.

    `candidate_key` is deliberately absent from the FAILURE even though the
    observation records one: a domain-scoped record must name none -- the hold
    parser refuses one that does -- and the entitlement that ran is identifying
    evidence about the attempt rather than the thing being held.
    """
    return AcpAvailabilityFailure(
        cause=observation.cause,
        scope=DOMAIN_SCOPE,
        hold_key=observation.availability_key,
        availability_key=observation.availability_key,
        candidate_key=None,
        source=FACTORY_EVIDENCE_SOURCE,
    )


def factory_hold_evidence(
    *, repo: Path, reader: FactoryRunReader, now_iso: str
) -> FactoryHoldEvidence:
    """Derive this host's live availability evidence from every declared factory.

    The factories are enumerated through `declared_factory_names`, which is the
    same enumeration the reconciler surveys: one list, so a factory this
    repository dispatches to can never be one it declines to read evidence
    from.
    """
    observations: list[FactoryHoldObservation] = []
    unobservable: list[Mapping[str, object]] = []
    for factory in declared_factory_names(block=dispatcher_block(cwd=repo)):
        read = _factory_evidence(factory=factory, reader=reader, now_iso=now_iso)
        observations.extend(read.observations)
        unobservable.extend(read.unobservable)
    return FactoryHoldEvidence(observations=tuple(observations), unobservable=tuple(unobservable))


def _factory_evidence(
    *, factory: str, reader: FactoryRunReader, now_iso: str
) -> FactoryHoldEvidence:
    """One participating factory's whole contribution, listing included."""
    rows = reader.list_runs(factory=factory)
    if rows is None:
        return FactoryHoldEvidence(
            unobservable=({"factory": factory, "reason": LISTING_UNREADABLE},)
        )
    observations: list[FactoryHoldObservation] = []
    unobservable: list[Mapping[str, object]] = []
    for row in rows:
        read = _row_evidence(factory=factory, row=row, reader=reader, now_iso=now_iso)
        observations.extend(read.observations)
        unobservable.extend(read.unobservable)
    return FactoryHoldEvidence(observations=tuple(observations), unobservable=tuple(unobservable))


def _row_evidence(
    *, factory: str, row: FabroRunSummary, reader: FactoryRunReader, now_iso: str
) -> FactoryHoldEvidence:
    """One listed run's contribution, spending an `inspect` only when it must."""
    if row.status_kind != _FAILED_STATUS_KIND:
        return EMPTY_FACTORY_HOLD_EVIDENCE
    instant = _attempt_instant(row=row)
    if instant is None:
        return FactoryHoldEvidence(unobservable=(_row_unobservable(factory=factory, row=row),))
    if not _within_hold_window(occurred=instant, now_iso=now_iso):
        return EMPTY_FACTORY_HOLD_EVIDENCE
    payload = reader.inspect_payload(factory=factory, run_id=row.run_id)
    if payload is None:
        return FactoryHoldEvidence(
            unobservable=(_row_unobservable(factory=factory, row=row, reason=INSPECT_UNREADABLE),)
        )
    observation = _observation(
        factory=factory, row=row, payload=payload, occurred_at=instant.strftime(_ISO_FORMAT)
    )
    if observation is None:
        return EMPTY_FACTORY_HOLD_EVIDENCE
    return FactoryHoldEvidence(observations=(observation,))


def _row_unobservable(
    *, factory: str, row: FabroRunSummary, reason: str = OCCURRENCE_UNREADABLE
) -> Mapping[str, object]:
    """The surfaced entry one unreadable row or run record contributes."""
    return {"factory": factory, "run_id": row.run_id, "reason": reason}


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
