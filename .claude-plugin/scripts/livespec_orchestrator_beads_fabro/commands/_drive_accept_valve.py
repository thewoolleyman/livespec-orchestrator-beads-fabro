"""The `accept:<id>` human valve, and the human-attested leg it gates on.

The human-attested-leg clause of `SPECIFICATION/contracts.md` (v114) says an item
with at least one `human_attested` assertion "MUST rest in `acceptance` after its
factory-captured assertions pass, regardless of policy, until a human-attested
record exists on its pull request. The `accept:<id>` valve MUST refuse such an
item while that record is absent, naming the assertions awaiting attestation and
the record format … `done` for such an item means both records observed."

WHY THE VALVE READS THE FORGE AND THE AI PASS DOES NOT. The human record is
posted by a HUMAN, at a time nobody schedules, long after the run that merged the
item has exited. There is no moment at which the Dispatcher could observe it as
part of the dispatch, so the only place the observation can happen is the valve
the human drives when they believe they are finished — which is also the one
place where refusing is useful rather than merely informative.

WHY THE PULL REQUEST COMES FROM THE POINTER. The pointer section the post-merge
write left on the description names the pull request, and that is deliberately
the ONLY route: re-deriving the pull request from the branch name would let the
valve read a DIFFERENT pull request from the one the acceptance pass graded, and
a human record on the wrong pull request is exactly the shape this gate exists to
catch. An item with no pointer is therefore refused rather than accepted — the
absence is unobserved evidence, and the evidence rule never disposes on absence.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from livespec_orchestrator_beads_fabro._store_description import update_work_item_description
from livespec_orchestrator_beads_fabro.commands._dispatcher_effective_criteria import (
    effective_criteria,
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
    PROOF_RECORD_TITLE,
    VERDICT_HUMAN_ATTESTED,
    ProofRecord,
    latest_proof_record,
)
from livespec_orchestrator_beads_fabro.commands._drive_valve_result import (
    invalid_source_state,
    valve_refusal,
    valve_success,
)

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
    from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = [
    "HUMAN_ATTESTATION_PENDING_ERR",
    "accept_item",
]

HUMAN_ATTESTATION_PENDING_ERR = "human-attestation-pending"
_ACCEPTANCE_STATUS = "acceptance"
_RECORD_FORMAT = (
    f"{PROOF_RECORD_TITLE} — {VERDICT_HUMAN_ATTESTED} — <human identity> — <UTC timestamp>"
)


def accept_item(
    *,
    repo: Path,
    config: StoreConfig,
    item: WorkItem,
    action_id: str,
    runner: CommandRunner | None = None,
) -> dict[str, Any]:
    """Accept one parked item, or refuse it while its human leg is outstanding."""
    if item.status != _ACCEPTANCE_STATUS:
        return invalid_source_state(aid=action_id, item=item, expected=_ACCEPTANCE_STATUS)
    pending = effective_criteria(item=item).human_attested_assertions
    if not pending:
        return _close(config=config, item=item, action_id=action_id)
    pointer = pointer_in(description=item.description)
    if pointer is None:
        return _refusal(item=item, action_id=action_id, pending=pending, detail=_NO_POINTER_DETAIL)
    record = _human_attested_record(repo=repo, pointer=pointer, runner=runner)
    if record is None:
        return _refusal(
            item=item,
            action_id=action_id,
            pending=pending,
            detail=f"no such record on pull request #{pointer.pull_request}",
        )
    _carry_both_links(config=config, item=item, pointer=pointer, record=record)
    return _close(config=config, item=item, action_id=action_id)


def _carry_both_links(
    *, config: StoreConfig, item: WorkItem, pointer: ProofPointer, record: ProofRecord
) -> None:
    """Rewrite the pointer so it cites BOTH records, which is what `done` means here.

    The pointer is EXTENDED, not replaced: the verified record stays exactly where
    it was, because it is the evidence the acceptance pass actually graded and the
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


_NO_POINTER_DETAIL = (
    "the description carries no Proof of Done pointer, so the pull request"
    " holding the record cannot be identified"
)


def _human_attested_record(
    *, repo: Path, pointer: ProofPointer, runner: CommandRunner | None
) -> ProofRecord | None:
    records = read_pull_request_records(
        repo=repo,
        pr_number=pointer.pull_request,
        runner=ShellCommandRunner() if runner is None else runner,
    )
    if records is None:
        return None
    return latest_proof_record(records=records, verdict=VERDICT_HUMAN_ATTESTED)


def _close(*, config: StoreConfig, item: WorkItem, action_id: str) -> dict[str, Any]:
    write_work_item_status_and_reconcile(path=config, item_id=item.id, status="done")
    return valve_success(
        aid=action_id,
        wid=item.id,
        stage="human-valve-accept",
        status="done",
        assignee=None,
        msg=f"Accepted {item.id}: acceptance -> done.",
    )


def _refusal(
    *, item: WorkItem, action_id: str, pending: tuple[str, ...], detail: str
) -> dict[str, Any]:
    """The refusal, naming every assertion awaiting attestation AND the format.

    Both halves are required by the clause and neither substitutes for the other:
    the assertions say what has to be proved, and the format says what the human
    has to post before this valve will take the item — a refusal carrying only the
    first leaves the operator to guess the header the reader matches on.
    """
    named = "; ".join(repr(assertion) for assertion in pending)
    return valve_refusal(
        aid=action_id,
        wid=item.id,
        err=HUMAN_ATTESTATION_PENDING_ERR,
        msg=(
            f"accept refused: work-item {item.id} awaits human attestation of"
            f" {named} — {detail}. Post one new comment on the pull request whose"
            f" first line is `{_RECORD_FORMAT}`, carrying each assertion's steps"
            " and proof, then drive this valve again."
        ),
    )
