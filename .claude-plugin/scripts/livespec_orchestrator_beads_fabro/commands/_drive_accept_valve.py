"""The `accept:<id>` human valve, and the two pending legs it gates on.

The human-attested-leg clause of `SPECIFICATION/contracts.md` (v114) says an item
with at least one `human_attested` assertion "MUST rest in `acceptance` after its
factory-captured assertions pass, regardless of policy, until a human-attested
record exists on its pull request. The `accept:<id>` valve MUST refuse such an
item while that record is absent, naming the assertions awaiting attestation and
the record format … `done` for such an item means both records observed." The
host-captured leg (v115) says the same of the OTHER mode: the valve "MUST refuse
an item with a `host_captured` assertion while no `host_verified` record lists it
as reproduced, naming the assertions and the record format", and "`done` for such
an item means the `verified` and `host_verified` records both observed".

WHY THE VALVE READS THE FORGE AND THE AI PASS DOES NOT. Both records are published
outside any dispatch — the human one by a human, at a time nobody schedules, and
the host one by an agent session on an operator host after the change is released
and installed. There is no moment at which the Dispatcher could observe either as
part of the dispatch that merged the item, so the only place the observation can
happen is the valve the operator drives when they believe they are finished —
which is also the one place where refusing is useful rather than merely
informative.

WHY THE PULL REQUEST COMES FROM THE POINTER. The pointer section the post-merge
write left on the description names the pull request, and that is deliberately
the ONLY route: re-deriving the pull request from the branch name would let the
valve read a DIFFERENT pull request from the one the acceptance pass graded, and a
record on the wrong pull request is exactly what the clause calls not evidence —
for the host leg it says so outright. An item with no pointer is therefore refused
rather than accepted; the absence is unobserved evidence, and the evidence rule
never disposes on absence.

WHY THE HOST LEG IS CHECKED FIRST AND PER ASSERTION. The modes are ordered
`factory_captured`, `host_captured`, `human_attested`, and the host leg is the one
an agent can clear without a human — so reporting it first hands the operator the
work that does not need them. And the host condition is not "a `host_verified`
record exists" but "a `host_verified` record LISTS THIS ASSERTION as reproduced":
a record whose own `Reproduced:` line says the proof did not reproduce carries the
right verdict word and is evidence of the opposite, so a check on the verdict
alone would accept an item its own evidence refutes.

WHAT THIS VALVE DOES NOT CHECK, recorded so the gap is not read as an oversight.
It does not verify the record's BUILD IDENTITY contains the merge, nor that the
replaying identity differs from the recording one. Both are duties the clause
places on the acceptance PASS and on the posting primitive that renders these
records, and both arrive with that primitive. The clause's own statement of this
valve's duty is the narrower one implemented here.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from livespec_orchestrator_beads_fabro._store_description import update_work_item_description
from livespec_orchestrator_beads_fabro.commands._dispatcher_effective_criteria import (
    EffectiveCriteria,
    effective_criteria,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_incident_closure import (
    INCIDENT_OBLIGATION_ERR,
    closure_obligations_for,
    incident_refusal_detail,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_lifecycle_writes import (
    write_work_item_status_and_reconcile,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_evidence import (
    read_pull_request_records,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_pointer import (
    ProofPointer,
    description_with_updated_pointer,
    pointer_in,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    VERDICT_HOST_VERIFIED,
    VERDICT_HUMAN_ATTESTED,
    ProofRecord,
    latest_proof_record,
)
from livespec_orchestrator_beads_fabro.commands._drive_accept_valve_leg import (
    OutstandingLeg,
    host_leg,
    human_leg,
)
from livespec_orchestrator_beads_fabro.commands._drive_valve_result import (
    invalid_source_state,
    valve_refusal,
    valve_success,
)
from livespec_orchestrator_beads_fabro.commands._intake_valve_claim_writes import (
    WRITER_HUMAN_VALVE,
    ClaimWrite,
    resting_at,
    valve_claim_refusal,
)

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
    from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = [
    "HOST_REPLAY_PENDING_ERR",
    "HUMAN_ATTESTATION_PENDING_ERR",
    "accept_item",
]

HOST_REPLAY_PENDING_ERR = "host-replay-pending"
HUMAN_ATTESTATION_PENDING_ERR = "human-attestation-pending"
_ACCEPTANCE_STATUS = "acceptance"
# What an accept that carried the human-attested link has done by the time its
# close is refused. The pointer is rewritten first, and a refused close does
# not restore it; the rewrite is idempotent, so a second press is safe.
_POINTER_REWRITTEN = (
    "the proof pointer in the item's description was already rewritten to cite the "
    "human-attested record, and that rewrite stands"
)
_NO_POINTER_DETAIL = (
    "the description carries no Proof of Done pointer, so the pull request"
    " holding the record cannot be identified"
)


def accept_item(
    *,
    repo: Path,
    config: StoreConfig,
    item: WorkItem,
    action_id: str,
    runner: CommandRunner | None = None,
) -> dict[str, Any]:
    """Accept one parked item, or refuse it while a host or human leg is outstanding."""
    if item.status != _ACCEPTANCE_STATUS:
        return invalid_source_state(aid=action_id, item=item, expected=_ACCEPTANCE_STATUS)
    # An expedited incident is accepted only once its chain records `closed`:
    # a human press is not final normal proof, and an expedited merge is not one.
    incident = closure_obligations_for(config=config, item_id=item.id)
    if incident:
        detail = incident_refusal_detail(item_id=item.id, outstanding=incident)
        return valve_refusal(
            aid=action_id,
            wid=item.id,
            err=INCIDENT_OBLIGATION_ERR,
            msg=f"accept refused: {detail}.",
        )
    criteria = effective_criteria(item=item)
    if not criteria.pending_leg_assertions:
        return _close(repo=repo, config=config, item=item, action_id=action_id)
    return _gated_accept(
        repo=repo, config=config, item=item, action_id=action_id, criteria=criteria, runner=runner
    )


def _gated_accept(
    *,
    repo: Path,
    config: StoreConfig,
    item: WorkItem,
    action_id: str,
    criteria: EffectiveCriteria,
    runner: CommandRunner | None,
) -> dict[str, Any]:
    """Grade both pending legs off ONE read of the pull request's records.

    One read rather than one per leg, because the two legs ask different questions
    of the SAME comment list and a second `gh` call could answer from a pull request
    that gained a record in between — which would let an item be accepted against a
    host record the human leg's read never saw, or the reverse.
    """
    pointer = pointer_in(description=item.description)
    if pointer is None:
        return _refusal(
            item=item,
            action_id=action_id,
            leg=_leading_leg(criteria=criteria),
            detail=_NO_POINTER_DETAIL,
        )
    records = _records(repo=repo, pointer=pointer, runner=runner)
    unreproduced = _unreproduced_host_assertions(criteria=criteria, records=records)
    if unreproduced:
        return _refusal(
            item=item,
            action_id=action_id,
            leg=_host_leg(assertions=unreproduced),
            detail=(
                f"no {VERDICT_HOST_VERIFIED} record on pull request #{pointer.pull_request}"
                " lists them as reproduced"
            ),
        )
    human = criteria.human_attested_assertions
    if not human:
        return _close(repo=repo, config=config, item=item, action_id=action_id)
    attested = (
        None
        if records is None
        else latest_proof_record(records=records, verdict=VERDICT_HUMAN_ATTESTED)
    )
    if attested is None:
        return _refusal(
            item=item,
            action_id=action_id,
            leg=_human_leg(assertions=human),
            detail=f"no such record on pull request #{pointer.pull_request}",
        )
    _carry_both_links(config=config, item=item, pointer=pointer, record=attested)
    return _close(
        repo=repo, config=config, item=item, action_id=action_id, already_done=_POINTER_REWRITTEN
    )


def _records(
    *, repo: Path, pointer: ProofPointer, runner: CommandRunner | None
) -> tuple[ProofRecord, ...] | None:
    return read_pull_request_records(
        repo=repo,
        pr_number=pointer.pull_request,
        runner=ShellCommandRunner() if runner is None else runner,
    )


def _unreproduced_host_assertions(
    *, criteria: EffectiveCriteria, records: tuple[ProofRecord, ...] | None
) -> tuple[str, ...]:
    """The host-captured assertions no decisive `host_verified` record reproduces.

    An UNREADABLE pull request (`records is None`) leaves every host assertion
    outstanding, which is the same answer an empty pull request gives and is the
    right one for both: the valve disposes on observed evidence, and a failed read
    is evidence of nothing.

    Records are shared by every item whose run used the pull request, so the newest
    record can name a sibling item's assertions. Each assertion therefore finds its
    own newest record that names it; a record that omits it decides nothing.
    """
    host = criteria.host_captured_assertions
    if not host:
        return ()
    if records is None:
        return host
    return tuple(
        one for one in host if not _host_assertion_reproduced(records=records, assertion=one)
    )


def _host_assertion_reproduced(*, records: tuple[ProofRecord, ...], assertion: str) -> bool:
    """Whether the newest `host_verified` record naming one assertion reproduces it."""
    for record in reversed(records):
        if record.verdict != VERDICT_HOST_VERIFIED:
            continue
        reproduced = record.reproduced(assertion=assertion)
        if reproduced is not None:
            return reproduced
    return False


def _leading_leg(*, criteria: EffectiveCriteria) -> OutstandingLeg:
    """The leg a no-pointer refusal reports, host first for the usual reason.

    A no-pointer item owes every leg it declares, and the refusal can name one; the
    host leg leads because it is the one an agent session can clear without a human.
    """
    host = criteria.host_captured_assertions
    if host:
        return _host_leg(assertions=host)
    return _human_leg(assertions=criteria.human_attested_assertions)


def _host_leg(*, assertions: tuple[str, ...]) -> OutstandingLeg:
    return host_leg(assertions=assertions, err=HOST_REPLAY_PENDING_ERR)


def _human_leg(*, assertions: tuple[str, ...]) -> OutstandingLeg:
    return human_leg(assertions=assertions, err=HUMAN_ATTESTATION_PENDING_ERR)


def _carry_both_links(
    *, config: StoreConfig, item: WorkItem, pointer: ProofPointer, record: ProofRecord
) -> None:
    """Rewrite the pointer so it cites BOTH records, which is what `done` means here.

    The pointer is EXTENDED, not replaced: the verified record stays exactly where it
    was, because it is the evidence the acceptance pass actually graded and the
    staleness fact still compares against it. The rewrite is in place and
    idempotent, so an item accepted twice ends with one section either way.
    """
    update_work_item_description(
        path=config,
        item_id=item.id,
        description=description_with_updated_pointer(
            description=item.description,
            pointer=replace(pointer, human_attested_url=record.url),
        ),
    )


def _close(
    *,
    repo: Path,
    config: StoreConfig,
    item: WorkItem,
    action_id: str,
    already_done: str | None = None,
) -> dict[str, Any]:
    """Close the accepted item; `already_done` is what this press wrote before the close."""
    lost = ClaimWrite(
        repo=repo,
        path=config,
        item_id=item.id,
        writer=WRITER_HUMAN_VALVE,
        intent="accept",
        still_as_decided=resting_at(status=_ACCEPTANCE_STATUS),
    ).write_status(
        status="done",
        reconcile=True,
        unguarded=lambda: write_work_item_status_and_reconcile(
            path=config, item_id=item.id, status="done"
        ),
    )
    if lost is not None:
        return valve_claim_refusal(
            aid=action_id, wid=item.id, verb="accept", outcome=lost, already_done=already_done
        )
    return valve_success(
        aid=action_id,
        wid=item.id,
        stage="human-valve-accept",
        status="done",
        assignee=None,
        msg=f"Accepted {item.id}: acceptance -> done.",
    )


def _refusal(*, item: WorkItem, action_id: str, leg: OutstandingLeg, detail: str) -> dict[str, Any]:
    """The refusal, naming every assertion the leg covers AND the record format.

    Both halves are required by the clause and neither substitutes for the other:
    the assertions say what has to be proved, and the format says what has to be
    posted before this valve will take the item — a refusal carrying only the first
    leaves the operator to guess the header the reader matches on.
    """
    named = "; ".join(repr(assertion) for assertion in leg.assertions)
    return valve_refusal(
        aid=action_id,
        wid=item.id,
        err=leg.err,
        msg=(
            f"accept refused: work-item {item.id} awaits {leg.awaited}"
            f" {named} — {detail}. Post one new comment on the pull request whose"
            f" first line is `{leg.record_format}`, carrying each assertion's steps"
            " and proof, then drive this valve again."
        ),
    )
