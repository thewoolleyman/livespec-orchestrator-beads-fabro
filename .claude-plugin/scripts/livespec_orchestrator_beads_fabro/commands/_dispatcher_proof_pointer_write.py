"""The post-merge Proof of Done pointer write.

The pointer clause of `SPECIFICATION/contracts.md` (v114) makes this a Dispatcher
duty discharged AFTER merge, against the description of the item that merged. It
runs here rather than inside the acceptance pass because the pass is a read: it
judges and reports, and giving it a ledger write would make a verdict and a
mutation inseparable.

THE RECORD IS NOT RE-READ. The `ProofLeg` the acceptance pass already produced
carries the record it graded against, so the pointer cites exactly the record the
verdict was reached on. A second forge read here would be a second answer to the
same question, and the two could differ — a `proof_capture` fix round can publish
a newer record between the two reads — leaving a pointer that names a record no
verdict was ever taken on.

EVERY REFUSAL IS JOURNALED AND NONE RAISES. The pointer is provenance, not a
gate: an item whose merge is real and whose work landed must not be left
undisposed because its description could not be rewritten. So an absent record,
an absent Definition of Done section, and a failed ledger write each journal what
stopped the write and return, exactly as the sibling fail-soft dispositions do.

A HOST-ONLY ITEM'S CITED RECORD IS ITS HOST REPLAY, and the write used to refuse
it. The cited record was read from `proof.record` alone — the FACTORY `verified`
record — so an item declaring only `host_captured` assertions, which owes no
factory record and whose acceptance genuinely rests on an independent
`host_verified` replay, journaled `proof-pointer-skipped` "no verified Proof of
Done record for the merging run". The consequence compounds rather than stopping
at the missing section: the `accept` valve reads the pull request OFF THE POINTER
and refuses an item carrying none, so the item could neither close on its own
evidence nor be accepted by hand. `host_only_record` is that arm.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._store_description import update_work_item_description
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_pointer import (
    ProofPointer,
    description_with_pointer,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    VERDICT_HUMAN_ATTESTED,
    ProofRecord,
    latest_proof_record,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    WorkItemNotFoundError,
)

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
    from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
    from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_evidence import ProofLeg
    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "PROOF_POINTER_STAGE",
    "host_only_record",
    "host_verified_record_url",
    "human_attested_record_url",
    "write_proof_pointer",
]

PROOF_POINTER_STAGE = "proof-pointer"
_SKIPPED_STAGE = "proof-pointer-skipped"
_ERROR_STAGE = "proof-pointer-error"
_LEDGER_WRITE_ERRORS = (
    WorkItemNotFoundError,
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
)


def write_proof_pointer(
    *,
    repo: Path,
    item: WorkItem,
    outcome: DispatchOutcome,
    proof: ProofLeg | None,
    journal: JournalFile,
) -> None:
    """Write the pointer at the record this item's acceptance pass graded.

    Each reason a pointer is NOT written is journaled with its OWN wording. They
    are three different facts about the item — it declares no proof mode at all,
    its merge recorded no pull request, or its run published no verified record —
    and only the last is a missing proof; reporting all three as one would make
    the ordinary legacy-item case look like absent evidence.

    WHICH record is cited follows what the pass actually rested on. A factory
    `verified` record attributed to the merging dispatch leads, because that is the
    evidence for every item declaring a `factory_captured` assertion. A HOST-ONLY
    item owes no such record at all, so `host_only_record` supplies the independent
    `host_verified` replay instead — see that function for why both of its guards
    are load-bearing.
    """
    if proof is None:
        _skip(journal=journal, item=item, reason="the effective criteria declare no proof mode")
        return
    pr_number = outcome.pr_number
    if pr_number is None:
        _skip(journal=journal, item=item, reason="the merged dispatch recorded no pull request")
        return
    record = proof.record if proof.record is not None else host_only_record(proof=proof)
    if record is None:
        _skip(
            journal=journal,
            item=item,
            reason="no verified Proof of Done record for the merging run",
        )
        return
    _write(
        repo=repo,
        item=item,
        pointer=ProofPointer(
            pull_request=pr_number,
            record_url=record.url,
            run_id=record.run_id,
            timestamp=record.timestamp,
            verdict=record.verdict,
            # The host link comes off the leg's OWN verdict rather than from a scan
            # of the records: the leg populates it only for a `host_verified` record
            # that actually passed an assertion, so the pointer can never cite a
            # record the pass refused for failing containment or independence.
            host_verified_url=host_verified_record_url(proof=proof),
            human_attested_url=human_attested_record_url(proof=proof),
        ),
        journal=journal,
    )


def _skip(*, journal: JournalFile, item: WorkItem, reason: str) -> None:
    journal.append(record={"stage": _SKIPPED_STAGE, "work_item_id": item.id, "reason": reason})


def host_only_record(*, proof: ProofLeg) -> ProofRecord | None:
    """The record a HOST-ONLY item's pointer cites, when the pass rested on one.

    A host-only item declares no `factory_captured` assertion, so no factory
    `verified` record is owed and the evidence the acceptance pass actually graded
    is the independent `host_verified` replay. Requiring `proof.record` regardless
    left such an item with NO pointer — and because the `accept` valve reads the
    pull request off the pointer and refuses an item that carries none, the item
    could then never be accepted either. The loss is provenance, not verdict: the
    merge was real and the proof was published, and the item's own description
    ended up naming neither.

    BOTH guards are load-bearing and neither substitutes for the other. The
    host-only test keeps a MIXED item's factory attribution fail-closed, so an
    unattributable `verified` record is never papered over with a host one. And
    `host_verified_record` is the HOST LEG'S OWN verdict rather than a scan for the
    newest `host_verified` comment, so a replay the pass refused — for failing
    containment, for an unreadable comparison, or for being published by the
    capturing identity — can never reach the pointer: it is `None` unless a record
    actually PASSED an assertion.

    THE SAME LINK THEN APPEARS TWICE in the rendered section, and that is the
    honest reading rather than an oversight. The two bullets answer two different
    questions the clause names separately — which record this item's acceptance was
    judged against, and which `host_verified` record discharged its host leg — and
    for a host-only item ONE record is the answer to both. Rendering only the
    second would leave the section with no cited record at all; suppressing it
    would make a host-only item the one case where the host link is absent while a
    host replay is exactly what closed it.
    """
    if not proof.host_captured_only:
        return None
    return proof.host_verified_record


def host_verified_record_url(*, proof: ProofLeg) -> str | None:
    """The `host_verified` record's comment link, when the pass rested on one.

    Taken from the host leg's own verdict rather than by scanning the records for the
    newest `host_verified` comment, and the difference is load-bearing: the leg
    populates that field only for a record that PASSED an assertion, having cleared
    both the containment check and the identity-independence rule. A scan would cite
    a record the same pass refused — advertising, in the item's own description, proof
    the verdict explicitly declined to rest on.
    """
    return None if proof.host_verified_record is None else proof.host_verified_record.url


def human_attested_record_url(*, proof: ProofLeg) -> str | None:
    """The human-attested record's comment link, when the item needs one and it exists.

    Scoped to items that actually carry a human-attested assertion: the clause
    adds the link "when the item has `human_attested` assertions", and a link
    rendered for an item with none would advertise a leg nobody owes.
    """
    if not proof.pending_human_attested:
        return None
    record = latest_proof_record(records=proof.records, verdict=VERDICT_HUMAN_ATTESTED)
    return None if record is None else record.url


def _write(*, repo: Path, item: WorkItem, pointer: ProofPointer, journal: JournalFile) -> None:
    description = description_with_pointer(description=item.description, pointer=pointer)
    if description is None:
        journal.append(
            record={
                "stage": _SKIPPED_STAGE,
                "work_item_id": item.id,
                "reason": "the description carries no Definition of Done section to write after",
            }
        )
        return
    written = attempt(
        action=lambda: update_work_item_description(
            path=store_config(repo=repo), item_id=item.id, description=description
        ),
        exceptions=_LEDGER_WRITE_ERRORS,
    )
    if isinstance(written, AttemptFailure):
        journal.append(
            record={
                "stage": _ERROR_STAGE,
                "work_item_id": item.id,
                "reason": type(written.error).__name__,
            }
        )
        return
    journal.append(
        record={"stage": PROOF_POINTER_STAGE, "work_item_id": item.id, **pointer.as_record()}
    )
