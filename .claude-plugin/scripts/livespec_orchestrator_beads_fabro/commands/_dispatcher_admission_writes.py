"""The admission valve's ledger writes, and the outcomes of the ones it withheld.

Split from `_dispatcher_admission`, which plans a pass and is at its size
ceiling. This owns what the plan then does to the ledger: the auto-approval
leg, the claim of each admitted item, and the terminal outcomes of everything
the valve planned but did not launch.

THE TWO STORE WRITERS ARE HANDED IN BY THE VALVE and not imported here. With
`dispatcher.claim_tokens` false or unset they are called exactly as the valve
called them before this module existed: the pending claim stamp, then the
`ready -> active` write with its assignee.

WITH THE KEY TRUE AN ADMISSION IS ONE WRITE. The item moves to `active` with
its assignee only after this admission has won the item's current claim token,
and that same write names the successor token and carries the pending claim
stamp. The stamp cannot go first as it does before the cutover: a writer that
does not win must write nothing to the item, and a stamp written ahead of a
lost claim would replace the winning dispatch's stamp with the loser's.

A REFUSED CLAIM IS A FAILED OUTCOME, NOT A DEFERRAL. An item the plan admitted
and the protocol refused was not short of capacity, so it must not be reported
as capacity-deferred, and a targeted dispatch of it must not report nothing at
all. It rides the pass's refused outcomes at the `admission-claim-refused`
stage, naming the protocol outcome, so the next pass tries again and an
operator can see why this one did not launch.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import asdict
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_admission_slots import (
    auto_approve_governing_settings,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_guard import (
    guarded_status_write,
    status_is,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_stamp import (
    journal_pending_claim_stamp,
    pending_claim_stamp_metadata,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_writes import (
    WRITER_ADMISSION,
    claim_status_write,
    settle_claim_write,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_decision_journal import (
    auto_disposition_journal_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_valves import (
    AdmissionPlan,
    admission_held_detail,
)
from livespec_orchestrator_beads_fabro.io import write_stderr
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = [
    "ADMISSION_CLAIM_REFUSED_STAGE",
    "admission_held_outcome",
    "admit_item",
    "approve_ready_items",
    "withheld_outcomes",
]

ADMISSION_CLAIM_REFUSED_STAGE = "admission-claim-refused"

_ADMIT_INTENT = "admit"
_APPROVE_INTENT = "auto-approve"
_ACTIVE_STATUS = "active"
_READY_STATUS = "ready"


def approve_ready_items(
    *,
    repo: Path,
    plan: AdmissionPlan,
    config: StoreConfig,
    journal: JournalFile,
    write: Callable[..., None],
) -> tuple[set[str], list[tuple[WorkItem, str]]]:
    """Write the plan's auto-approval leg, before any admission.

    Returns the ids that landed at `ready` and, beside them, each item whose
    approval the claim-token protocol refused together with the outcome. A
    refused item is still `pending-approval`, so the valve must not go on to
    admit it in this pass.
    """
    approved_ids: set[str] = set()
    refused: list[tuple[WorkItem, str]] = []
    for item in plan.approved:
        refusal = claim_status_write(
            repo=repo,
            path=config,
            intent=_APPROVE_INTENT,
            write=write,
            item_id=item.id,
            status=_READY_STATUS,
            writer=WRITER_ADMISSION,
            journal=journal,
            # The plan approved the item as it then rested, `pending-approval`.
            still_as_decided=status_is(status=item.status),
        )
        if refusal is not None:
            refused.append((item, refusal))
            continue
        approved_ids.add(item.id)
        journal.append(record={"stage": "ledger-approve", "work_item_id": item.id})
        journal.append(
            record=auto_disposition_journal_record(
                work_item_id=item.id,
                disposition="auto-approve",
                governing_settings=auto_approve_governing_settings(item=item),
            )
        )
    return approved_ids, refused


def admit_item(  # noqa: PLR0913 — kw-only; one admission's facts plus the valve's two store writers.
    *,
    repo: Path,
    config: StoreConfig,
    journal: JournalFile,
    item_id: str,
    assignee: str,
    dispatch_id: str,
    resume: bool,
    explicit_factory: str | None,
    stamp: Callable[..., None],
    write: Callable[..., None],
) -> str | None:
    """Claim one admitted item; `None` when it is `active`, else the refusal."""
    return settle_claim_write(
        repo=repo,
        item_id=item_id,
        writer=WRITER_ADMISSION,
        intent=_ADMIT_INTENT,
        journal=journal,
        unguarded=lambda: _admit_unguarded(
            repo=repo,
            config=config,
            journal=journal,
            item_id=item_id,
            assignee=assignee,
            dispatch_id=dispatch_id,
            resume=resume,
            explicit_factory=explicit_factory,
            stamp=stamp,
            write=write,
        ),
        guarded=lambda: _admit_guarded(
            repo=repo,
            config=config,
            journal=journal,
            item_id=item_id,
            assignee=assignee,
            dispatch_id=dispatch_id,
            resume=resume,
            explicit_factory=explicit_factory,
        ),
    )


def _admit_unguarded(  # noqa: PLR0913 — kw-only; the valve's own two writes, argument for argument.
    *,
    repo: Path,
    config: StoreConfig,
    journal: JournalFile,
    item_id: str,
    assignee: str,
    dispatch_id: str,
    resume: bool,
    explicit_factory: str | None,
    stamp: Callable[..., None],
    write: Callable[..., None],
) -> None:
    """The stamp BEFORE the transition, as `_dispatcher_claim_stamp` requires."""
    stamp(
        repo=repo,
        work_item_id=item_id,
        dispatch_id=dispatch_id,
        journal=journal,
        resume=resume,
        explicit_factory=explicit_factory,
    )
    write(path=config, item_id=item_id, status=_ACTIVE_STATUS, assignee=assignee)


def _admit_guarded(  # noqa: PLR0913 — kw-only; one admission's facts.
    *,
    repo: Path,
    config: StoreConfig,
    journal: JournalFile,
    item_id: str,
    assignee: str,
    dispatch_id: str,
    resume: bool,
    explicit_factory: str | None,
) -> str | None:
    """Win the token, then land status, assignee, successor and stamp together."""
    built = pending_claim_stamp_metadata(
        repo=repo,
        work_item_id=item_id,
        dispatch_id=dispatch_id,
        resume=resume,
        explicit_factory=explicit_factory,
    )
    unbuilt = built if isinstance(built, str) else None
    refusal = guarded_status_write(
        path=config,
        item_id=item_id,
        status=_ACTIVE_STATUS,
        intent=_ADMIT_INTENT,
        writer=WRITER_ADMISSION,
        assignee=assignee,
        metadata=None if isinstance(built, str) else built,
        # Admission is `ready -> active`: an item another dispatch already
        # moved is not this admission's to claim, whichever token it names.
        still_as_decided=status_is(status=_READY_STATUS),
    )
    if refusal is None:
        journal_pending_claim_stamp(
            journal=journal, work_item_id=item_id, dispatch_id=dispatch_id, detail=unbuilt
        )
    return refusal


def admission_held_outcome(*, item: WorkItem, reason: str) -> DispatchOutcome:
    """Build the `admission-held` terminal for an item held at the admission valve.

    A `failed` outcome (so the dispatch exit code flips to 1 and the
    maintainer's eyes are required) at the `admission-held` stage; nothing is
    launched and nothing is closed — a manual item stays at `pending-approval`
    for the maintainer to approve, while an unresolvable item stays put until
    assignment is fixed.
    """
    return DispatchOutcome(
        work_item_id=item.id,
        status="failed",
        stage="admission-held",
        pr_number=None,
        merge_sha=None,
        detail=admission_held_detail(item_id=item.id, reason=reason),
    )


def withheld_outcomes(
    *,
    held: Sequence[tuple[WorkItem, str]],
    claim_refused: Sequence[tuple[WorkItem, str]],
    journal: JournalFile,
) -> list[DispatchOutcome]:
    """Journal and surface every item the valve planned for but did not launch."""
    outcomes = [admission_held_outcome(item=item, reason=reason) for item, reason in held]
    outcomes.extend(
        _claim_refused_outcome(item=item, reason=reason) for item, reason in claim_refused
    )
    for outcome in outcomes:
        journal.append(record={"stage": "outcome", "outcome": asdict(outcome)})
        _ = write_stderr(text=f"SURFACE: {outcome.detail}\n")
    return outcomes


def _claim_refused_outcome(*, item: WorkItem, reason: str) -> DispatchOutcome:
    """The terminal for an item whose claim-token write was refused."""
    return DispatchOutcome(
        work_item_id=item.id,
        status="failed",
        stage=ADMISSION_CLAIM_REFUSED_STAGE,
        pr_number=None,
        merge_sha=None,
        detail=(
            f"admission refused: work-item {item.id} was not claimed because the "
            f"claim-token protocol reported {reason}; nothing was written to the item "
            "and the next admission pass decides again."
        ),
    )
