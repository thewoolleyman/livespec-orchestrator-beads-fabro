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

THE CITED RECORD IS THE LATEST ONE THAT COUNTS FOR A DECLARED MODE. The factory
`verified` record leads when the merging dispatch published one. Without it the
cited record is the independent `host_verified` replay the host leg itself
accepted, and that holds for a MIXED item as much as for a host-only one: the
`accept` valve reads the pull request OFF THE POINTER and refuses an item carrying
none, so an item whose pull request holds a replay and no `verified` record
(a factory `captured` record counts for no mode, because it carries no
per-assertion verdict) could neither close on its own evidence nor be accepted by
hand. A pointer citing the replay says only which record counts; the acceptance
verdict still rests on the factory leg, which stays unevidenced and parks.
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
    VERDICT_CARRIED_FORWARD,
    VERDICT_HUMAN_ATTESTED,
    VERDICT_VERIFIED,
    latest_proof_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection_journal import (
    read_journal_records,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_journal import was_resumed
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
    "carried_forward_record_url",
    "host_verified_record_url",
    "human_attested_record_url",
    "resumed_run_id",
    "write_proof_pointer",
]

PROOF_POINTER_STAGE = "proof-pointer"
# The two verdicts a record may anchor the published head with, read by POSITION
# so the newest decides. Spelled here rather than imported from
# `_dispatcher_publication_head` because that module is the SANDBOX side of the
# same rule and importing it would pull a program renderer into the host-side
# pointer writer; the two are held to one reading by `carried_forward_record_url`
# naming that module in its own docstring and by the pointer's paired test.
_ANCHOR_VERDICTS = (VERDICT_VERIFIED, VERDICT_CARRIED_FORWARD)
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
    # A `not_reproduced` record can be the one the pass graded, and the pointer cites only
    # a record that counts as proof, so it never rests on one.
    graded = proof.record
    record = (
        graded
        if graded is not None and graded.verdict == VERDICT_VERIFIED
        else proof.host_verified_record
    )
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
            resumed_run_id=resumed_run_id(
                journal_path=journal.path,
                item=item,
                outcome=outcome,
                pull_request=pr_number,
            ),
            # The carry-forward link follows the newest ANCHOR record rather than
            # the presence of a carry-forward anywhere on the pull request, for
            # the reason that resolver's own docstring gives.
            carried_forward_url=carried_forward_record_url(proof=proof),
            # The host link comes off the leg's OWN verdict rather than from a scan
            # of the records: the leg populates it only for a `host_verified` record
            # that actually passed an assertion, so the pointer can never cite a
            # record the pass refused for failing containment or independence.
            host_verified_url=host_verified_record_url(proof=proof),
            human_attested_url=human_attested_record_url(proof=proof),
        ),
        journal=journal,
    )


def resumed_run_id(
    *, journal_path: Path, item: WorkItem, outcome: DispatchOutcome, pull_request: int
) -> str | None:
    """The dispatch that MERGED a resumed item, or `None` for an ordinary one.

    The clause asks the pointer of a resumed item to name "the resumed run's
    identifier beside the record's own run id", and those two differ precisely
    because the record was published by the EARLIER run. So the value here is the
    merging dispatch's own identifier, taken off the outcome, and the journal is
    consulted only to answer whether this merge was reached through a resume at
    all.

    KEYED ON THE PULL REQUEST, not on the item. An item whose earlier pull
    request was resumed and whose current one was dispatched plainly was not
    resumed into THIS merge, and naming a resumed run on its pointer would credit
    a dispatch that had nothing to do with the record being cited.

    `None` also covers a resumed merge whose outcome carries no run id — the
    reconcile path builds its outcome from a resolved merged pull request and has
    none. An empty bullet would be worse than no bullet: the clause says the
    section carries only the fields it names, and a reader would take the blank
    for an identifier that had been recorded and lost.
    """
    if outcome.fabro_run_id is None:
        return None
    if not was_resumed(
        records=read_journal_records(journal_path=journal_path),
        work_item_id=item.id,
        pull_request=pull_request,
    ):
        return None
    return outcome.fabro_run_id


def _skip(*, journal: JournalFile, item: WorkItem, reason: str) -> None:
    journal.append(record={"stage": _SKIPPED_STAGE, "work_item_id": item.id, "reason": reason})


def carried_forward_record_url(*, proof: ProofLeg) -> str | None:
    """The `carried_forward` record's link, when the merged head was reached by one.

    The clause adds the link "when the merged head was reached through a
    carry-forward", and that is a question about the NEWEST ANCHOR rather than
    about whether such a record exists anywhere on the pull request. A run may
    carry its proof forward, be sent back round capture and replay by a later
    refresh, and merge on a freshly VERIFIED head; the carry-forward is then a
    superseded decision, and citing it would advertise — in the item's own
    description — proof of a tree that is not the one that merged.

    So the two ANCHOR verdicts are read by POSITION and the last one decides,
    which is the identical reading `_dispatcher_publication_head` takes when it
    establishes which head `pr` may ready. Reading it any other way here would
    make the pointer and the publication gate disagree about the same chain.
    """
    anchors = [one for one in proof.records if one.verdict in _ANCHOR_VERDICTS]
    if not anchors or anchors[-1].verdict != VERDICT_CARRIED_FORWARD:
        return None
    return anchors[-1].url


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
