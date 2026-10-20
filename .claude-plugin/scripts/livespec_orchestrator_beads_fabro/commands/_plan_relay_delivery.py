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

THE IDENTITY FIELDS ARE GRADED BEFORE THE READ, which is the fail-closed order.
A relay with a blank id, a blank operation identity, a blank sender or a blank
deadline is one no later call can address, so spending a tenant or forge read on
it would be spending it on a question nobody can ask again.

WHAT THIS CALL NEVER DOES. It never transfers ownership and it never closes an
obligation: those take all three legs, which `RelayRecord.ownership_transferable`
answers and which no single recording decides. And it never extends a deadline —
the deadline a record carries is read back from the relay's own history, never
from the request, so a later caller naming a longer one changes nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro.commands._plan_relay_projection import write_relay_event
from livespec_orchestrator_beads_fabro.commands._plan_relay_record import (
    RelayAcknowledgements,
    RelayLegs,
    RelayRecord,
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

__all__: list[str] = [
    "RelayRefusal",
    "RelayRequest",
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


@dataclass(frozen=True, kw_only=True)
class RelayRefusal:
    """Why one relay was not recorded. Nothing was written when this is returned."""

    detail: str


def record_relay(*, request: RelayRequest) -> RelayRecord | RelayRefusal:
    """Observe the relay's requested target effect, then record what was observed."""
    refusal = _identity_refusal(request=request)
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
    observation = read_result(
        project_root=request.project_root,
        reference=request.required_result,
        runner=request.runner,
        now=request.now,
    )
    record = _record(request=request, reference=reference, observation=observation)
    write_relay_event(
        client=make_beads_client(config=request.config),
        epic_id=request.epic_id,
        record=record,
    )
    return record


def _identity_refusal(*, request: RelayRequest) -> RelayRefusal | None:
    """Refuse a relay no later call could address, before any read is spent."""
    named = (
        ("relay id", request.relay_id),
        ("operation identity", request.operation_id),
        ("sender", request.sender),
        ("deadline", request.deadline),
    )
    blank = [field for field, value in named if value.strip() == ""]
    if not blank:
        return None
    return RelayRefusal(
        detail=(
            "a relay must carry a stable relay id, a stable operation identity, the"
            f" sender that owes it and an absolute UTC deadline; absent: {', '.join(blank)}"
        )
    )


def _record(
    *,
    request: RelayRequest,
    reference: ResultReference,
    observation: ResultObservation,
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
        sender=request.sender,
        required_result=request.required_result,
        result_identity=reference.identity,
        original_deadline=request.deadline,
        delivered=delivered,
        legs=RelayLegs(
            receipt_ack=request.acknowledgements.receipt_ack,
            peer_recorded=request.acknowledgements.peer_recorded,
            target_evidence=observation.evidence if delivered else None,
        ),
        observation=observation,
        recorded_at=request.now,
    )
