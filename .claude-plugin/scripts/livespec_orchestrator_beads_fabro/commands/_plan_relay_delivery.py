"""The plan primitive that records a relay, and the one thing that discharges it.

`contracts.md` section "Relay delivery": "The plan primitive recording a relay
MUST accept a stable relay id, typed expected result and absolute UTC deadline,
and MUST read the target before recording `delivered`. A sender queue receipt,
peer acknowledgment or peer_recorded value MUST NOT establish delivery."

THE READ IS NOT OPTIONAL AND IS NOT SUBSTITUTABLE. `delivered` is written from
one input — a `satisfied` reading taken by the shared authoritative result reader
in this call — and from nothing the caller supplied. The caller's transport legs
ride along unchanged, which is what makes the acknowledged-but-unmoved case
record as what it is: an undelivered relay whose sender still owes it.

AN UNTYPED EXPECTED RESULT IS REFUSED BEFORE ANYTHING IS WRITTEN, and the refusal
is not merely tidiness. The relay's canonical identity is the identity of its
typed target, and every later decision about the relay — whether a recheck is
observing the SAME obligation, whether a reused relay id has a conflicting target
— compares that identity. A relay recorded without one is an obligation nothing
can ever re-observe, which is worse than no record at all: it reads as tracked.
The same refusal is what keeps "Arbitrary shell predicates MUST NOT be accepted
as result references" a property of this surface rather than a scan for
shell-looking strings; the closed kind set in `_plan_result_targets` does the
work and this call simply declines what it will not admit.

EVERY OTHER GRADE LIVES IN `_plan_relay_admission` and runs here in the
fail-closed order: the identity fields, then the relay's own recorded history,
then the supersession — each before the target is read, because a read spent on
a relay no later call can address or take is a read spent on a question nobody
can ask again. The epic's relay comments are read ONCE and the resolved records
are handed down, so no two grades can disagree about what the ledger holds.

A RETRY IS ANSWERED FROM THE RECORD AND NEVER BY OBSERVING AGAIN. "Retrying the
same operation identity for an existing relay MUST return its recorded
observation and MUST NOT extend the original deadline": a retry is the SAME act
re-entered, by a caller that could not tell whether its first attempt landed, so
asking twice must be indistinguishable from asking once. A primitive that simply
re-observed would return a record agreeing on the deadline, the relay and the
target while writing a second comment and — if the target had moved in between —
reporting a DIFFERENT observation under one operation identity.

THE MATCH IS WITHIN THE RELAY, never across the epic. A sender numbering its
operations per relay is the ordinary case, so an identity matched epic-wide
would answer a fresh relay's FIRST recording with another relay's record: a
target the caller never named, under a deadline it never set. The retry check
runs before the target grades for the same reason the grades run before the
read — a retry has nothing left to grade, because the act it repeats was graded
when it happened.

THE DEADLINE AND THE SENDER A RECORD CARRIES ARE BOTH READ BACK OFF THE RELAY'S
OWN HISTORY, never off the request. "If the result is unsatisfied or
unobservable, the primitive MUST record an undelivered relay, its unchanged
deadline and the observation; the sender retains the obligation" — and the party
doing the recording is not necessarily the party that owes it, so a primitive
that stored either value as handed would let a sender roll its own clock forward
every time it re-observed its own relay, with every record well-formed either
way. The request supplies both only where the relay has no history, which is the
one call that establishes them.

THE OWNER IS CARRIED PAST THE RECHECK RECORDER SPECIFICALLY, which is the half of
that rule easiest to leave out — the deadline reads as the whole of it, because a
recheck ordinarily restates the sender it already has and nothing then looks
wrong. "Timeout MUST retain sender ownership and the original deadline while the
independent consumer performs bounded recovery, even when the sender produces no
new handoff", and "Owner disappearance requires explicit recoverable takeover,
not silent discharge": the independent consumer IS this primitive's recheck
caller, so it records an observation without becoming the owner. Taking `sender`
from the request instead transfers ownership with none of the three legs present
and with no record saying a transfer happened — and because `write_relay_event`
authors the comment AS the relay's sender, the timeline would then report an
expiry as falling to the consumer rather than to the party that still owes it.
The recording party stays attributable by its own `operation_id`.

A SUPERSEDING RECORD CARRIES THE DISPOSITION IT DISPLACES, which is the half of
the conflicting-target rule that lives here rather than in the grade. The
predecessor's own comment cannot be amended, so "preserves the old obligation's
disposition" is satisfiable only on the record that replaces it — and the
deadline rides with that disposition, because being displaced does not discharge
an obligation and a reader asked whether anything is still owed needs the clock
it was owed against.

THE TRANSPORT LEGS CARRY FORWARD and a supplied value replaces the one it
supersedes. A recheck that dropped them would make a relay look LESS acknowledged
the more often it was observed, while a recheck that could not replace them could
never record a peer's later recording — and neither leg moves the delivery
verdict in either direction.

WHAT THIS CALL NEVER DOES. It never transfers ownership and it never closes an
obligation: those take all three legs, which `RelayRecord.ownership_transferable`
answers and which no single recording decides.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro.commands._plan_relay_admission import (
    RelayRefusal,
    RelaySupersession,
    identity_refusal,
    target_refusal,
)
from livespec_orchestrator_beads_fabro.commands._plan_relay_projection import (
    read_relay_records,
    write_relay_event,
)
from livespec_orchestrator_beads_fabro.commands._plan_relay_record import (
    RelayAcknowledgements,
    RelayLegs,
    RelayRecord,
    latest_relay,
    recorded_operation,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_observation import (
    OBSERVATION_SATISFIED,
    ResultObservation,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_reader import read_result
from livespec_orchestrator_beads_fabro.commands._plan_result_reference import parse_result_reference
from livespec_orchestrator_beads_fabro.commands._plan_result_targets import ResultReference

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
    from livespec_orchestrator_beads_fabro.types import StoreConfig

# `RelayRefusal` and `RelaySupersession` are defined in `_plan_relay_admission`
# and named here because they are this primitive's own public surface: a caller
# supplies the one and reads the other, and neither is reached except through
# `record_relay`. The GRADE moved out by cohesion; the vocabulary did not.
__all__: list[str] = [
    "RelayRefusal",
    "RelayRequest",
    "RelaySupersession",
    "record_relay",
]


@dataclass(frozen=True, kw_only=True)
class RelayRequest:
    """Everything one relay recording needs, across the public module boundary.

    `operation_id` is the identity a RETRY is recognised by and is independent of
    `relay_id`: one relay accumulates many observations, each taken by its own
    operation, and conflating the two would make every recheck read as a retry.
    """

    config: StoreConfig
    project_root: Path
    runner: CommandRunner
    epic_id: str
    relay_id: str
    operation_id: str
    sender: str
    required_result: object
    deadline: str
    acknowledgements: RelayAcknowledgements
    now: str
    supersedes: RelaySupersession | None = None


def record_relay(*, request: RelayRequest) -> RelayRecord | RelayRefusal:
    """Observe the relay's requested target effect, then record what was observed."""
    refusal = identity_refusal(
        relay_id=request.relay_id,
        operation_id=request.operation_id,
        sender=request.sender,
        deadline=request.deadline,
    )
    if refusal is not None:
        return refusal
    reference = parse_result_reference(value=request.required_result)
    if not isinstance(reference, ResultReference):
        return RelayRefusal(
            detail=(
                "a relay must name a typed expected result the shared authoritative"
                f" result reader can observe: {reference.detail}"
            )
        )
    client = make_beads_client(config=request.config)
    records = read_relay_records(client=client, epic_id=request.epic_id)
    own = tuple(record for record in records if record.relay_id == request.relay_id)
    retried = recorded_operation(records=own, operation_id=request.operation_id)
    if retried is not None:
        return retried
    history = latest_relay(records=records, relay_id=request.relay_id)
    displaced = latest_relay(
        records=records,
        relay_id="" if request.supersedes is None else request.supersedes.relay_id,
    )
    refusal = target_refusal(
        relay_id=request.relay_id,
        epic_id=request.epic_id,
        requested_identity=reference.identity,
        supersedes=request.supersedes,
        history=history,
        displaced=displaced,
    )
    if refusal is not None:
        return refusal
    observation = read_result(
        project_root=request.project_root,
        reference=request.required_result,
        runner=request.runner,
        now=request.now,
    )
    record = _record(
        request=request,
        reference=reference,
        observation=observation,
        history=history,
        displaced=displaced,
    )
    write_relay_event(client=client, epic_id=request.epic_id, record=record)
    return record


def _record(
    *,
    request: RelayRequest,
    reference: ResultReference,
    observation: ResultObservation,
    history: RelayRecord | None,
    displaced: RelayRecord | None,
) -> RelayRecord:
    """Assemble the record this observation produces.

    `target_evidence` is derived from the observation and never from the request:
    a satisfied reading contributes the evidence identity it rests on, and every
    other reading contributes nothing. That is the whole of "only an
    authoritative observation of the requested target effect discharges it".
    """
    delivered = observation.status == OBSERVATION_SATISFIED
    return RelayRecord(
        relay_id=request.relay_id,
        operation_id=request.operation_id,
        sender=request.sender if history is None else history.sender,
        required_result=request.required_result,
        result_identity=reference.identity,
        original_deadline=request.deadline if history is None else history.original_deadline,
        delivered=delivered,
        legs=RelayLegs(
            receipt_ack=_carried(
                supplied=request.acknowledgements.receipt_ack,
                history=None if history is None else history.legs.receipt_ack,
            ),
            peer_recorded=_carried(
                supplied=request.acknowledgements.peer_recorded,
                history=None if history is None else history.legs.peer_recorded,
            ),
            target_evidence=observation.evidence if delivered else None,
        ),
        observation=observation,
        recorded_at=request.now,
        superseded_relay_id=None if displaced is None else displaced.relay_id,
        superseded_disposition=None if displaced is None else _disposition_of(record=displaced),
    )


def _carried(*, supplied: str | None, history: str | None) -> str | None:
    """A supplied transport leg, else the one this relay already recorded."""
    return history if supplied is None else supplied


def _disposition_of(*, record: RelayRecord) -> str:
    """The displaced obligation's disposition, as its successor preserves it.

    The deadline rides WITH the disposition because the displaced obligation is
    not discharged by being displaced: a reader asked whether anything is still
    owed needs the clock it was owed against, and the predecessor's own record
    cannot be amended to say so later.
    """
    return (
        f"{record.disposition} ({record.observation.status})"
        f" under deadline {record.original_deadline}"
    )
