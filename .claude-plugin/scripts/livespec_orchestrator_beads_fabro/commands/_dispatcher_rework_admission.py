"""The rework-pending re-dispatch leg of the Dispatcher's drain.

The executor half of the ratified rework-pending re-dispatch contract in
`SPECIFICATION/contracts.md`: WHICH marked rows a pass drives, and how many of
them capacity admits. It is a cohesive concern of its own rather than more of
`_dispatcher_admission`, because the ready-side valve moves an item
`ready -> active` while this leg re-occupies a WIP slot an `active` row
ALREADY holds — it writes no status, resolves no assignee, and deliberately
leaves the `rework:pending` marker in place until the rework dispatch's
terminal disposition clears it through the store's lifecycle write seams.

WITH `dispatcher.claim_tokens` TRUE AN ADMISSION CLAIMS THE ROW. The row still
carries the previous dispatch's claim stamp, and under the claim-token protocol
a dispatch can neither stamp its run nor write its terminal onto a row stamped
with another dispatch's run. So each admission first replaces that stamp with a
pending one naming its own dispatch, in one token-guarded write
(`_dispatcher_admission_claims.claim_rework_row`). A row whose claim the
protocol refused is not admitted, takes no dispatch lock, and is reported with
the outcome. With the key false or unset the leg writes nothing to the ledger,
as it always has.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from livespec_runtime.work_items.lifecycle import ready_sort_key

from livespec_orchestrator_beads_fabro._store_dispatch_claim import ClaimRow
from livespec_orchestrator_beads_fabro.commands import _dispatcher_self_update as selfup
from livespec_orchestrator_beads_fabro.commands._dispatcher_admission_claims import (
    claim_rework_row,
    planned_claim_rows,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_reclaim import (
    ActiveClaimAccounting,
    claimed_active_projection,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_lock import (
    write_dispatch_lock,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._ready_aging_order import (
    ReadyAgingOrder,
    ready_aging_order,
    unaged_ready_order,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "REWORK_ADMIT_STAGE",
    "ReworkAdmission",
    "ReworkPass",
    "admit_rework",
    "projected_rework_candidates",
    "rework_pending_candidates",
    "rework_redispatch_eligible_ids",
]

# The journal stage that records a rework admission. It is deliberately NOT
# `ledger-admit`: that stage is the claim-accounting's marker for "a fresh
# `ready -> active` transition happened here", and reusing it would make a
# re-dispatch of an already-`active` row look like a new admission.
REWORK_ADMIT_STAGE = "ledger-rework-admit"


@dataclass(frozen=True, kw_only=True)
class ReworkPass:
    """How one dispatch pass narrows and bounds its rework leg.

    `scope_ids` is the `--item` narrowing — `None` means "every marked row",
    and a non-`None` set can only ever REMOVE rows, so a named marked item is
    eligible THROUGH the selection rather than as an exception to it.
    `budget` is the per-run `--budget` ceiling; it bounds the pass as a whole,
    so rework re-dispatches and new admissions draw on one allowance rather
    than two.
    """

    scope_ids: frozenset[str] | None = None
    budget: int | None = None


@dataclass(frozen=True, kw_only=True)
class ReworkAdmission:
    """The rework leg's verdict over the marked, lock-less `active` rows.

    `admitted` carries the rows this pass re-dispatches; `deferred` carries the
    rows the capacity condition held back, reported with the same
    `capacity-deferred` status the ready side uses so a deferral stays a
    non-defect in the run's verdict. `refused` carries each row the claim-token
    protocol would not let this pass claim, beside the protocol's outcome: such
    a row was not short of capacity, so it is not a deferral, and it is always
    empty while `dispatcher.claim_tokens` is false or unset.
    """

    admitted: tuple[WorkItem, ...]
    deferred: tuple[DispatchOutcome, ...]
    refused: tuple[tuple[WorkItem, str], ...] = ()


def rework_pending_candidates(
    *,
    items: list[WorkItem],
    accounting: ActiveClaimAccounting,
    rework: ReworkPass,
    ready_aging: ReadyAgingOrder | None = None,
) -> tuple[WorkItem, ...]:
    """The marked, lock-less `active` rows to re-dispatch, in ready-queue order.

    Membership is the ACCOUNTING's verdict, never a fresh read of the ledger
    label: `rework_pending_active_ids` is exposed precisely so ONE authority
    answers "is this row a sanctioned rework park?", and the accounting is also
    where the double-selection guard lives — a marked row holding a live
    dispatch lock is classified as a live lock and never reaches this list.
    The ordering authority is the same key the ready queue uses, composed with
    the same `ready_aging` inputs, so the two legs of one drain cannot rank the
    same tenant differently. `ready_aging` is optional for the same reason it is
    on `rank_candidates`: a caller with no project root to resolve a tenant from
    orders by the ratified unknowable-instant path.
    """
    marked = set(accounting.rework_pending_active_ids)
    order = ready_aging if ready_aging is not None else unaged_ready_order()
    selected = sorted(
        (
            item
            for item in items
            if item.id in marked and (rework.scope_ids is None or item.id in rework.scope_ids)
        ),
        # Built ONCE per pass, exactly as the ready queue builds it.
        key=ready_sort_key(
            now=datetime.now(tz=timezone.utc),
            ready_since_lookup=order.ready_since_lookup,
            ready_aging_threshold_hours=order.ready_aging_threshold_hours,
        ),
    )
    if rework.budget is None:
        return tuple(selected)
    return tuple(selected[: rework.budget])


def admit_rework(  # noqa: PLR0913 — kw-only; the pass's capacity plus what a claim's stamp needs.
    *,
    repo: Path,
    candidates: tuple[WorkItem, ...],
    journal: JournalFile,
    active_count: int,
    wip_cap: int | None,
    planned: Mapping[str, ClaimRow] | None = None,
    resume_ids: frozenset[str] = frozenset(),
    explicit_factory: str | None = None,
) -> ReworkAdmission:
    """Admit marked rows into free capacity, in order, touching no status.

    The capacity condition EXCLUDES the candidate's own `active` row for free:
    a marked lock-less row is already outside `active_count`, because the
    accounting parks it rather than counting it, so `occupied < wip_cap` IS
    "the count of `active` items other than this one is below the cap". Each
    admission then takes a live dispatch lock and joins `occupied`, which is
    what stops two marked rows from oversubscribing one free slot. A `wip_cap`
    of `0` therefore admits nothing (no count is below zero), and the
    `wip_cap: 1` self-deadlock cannot arise, because the parked row never
    saturates the condition it must itself pass. `wip_cap` is `None` on the
    cap-free `dispatch --item` operator override, read here exactly as the
    ready-side valve reads it — the override narrows the selection to one
    named item without granting rework any bypass the ready path lacks.

    The admission is journaled BEFORE the run launches, and the marker is left
    stamped: it clears only at the terminal disposition, so a rework dispatch
    that dies before publishing leaves the row marked and (its lock now stale,
    its process gone) lock-less — re-selectable by a later drain rather than
    re-stranded.

    `planned` is the pass's `planned_claim_rows` reading, which the valve takes
    before its first ledger write; a caller that hands none has it taken here.
    `resume_ids` and `explicit_factory` are the valve's own, and decide the
    factory a claim's pending stamp names exactly as they do for a ready
    admission. All three are read only while `dispatcher.claim_tokens` is true.
    """
    rows = planned if planned is not None else planned_claim_rows(repo=repo, candidates=candidates)
    occupied = active_count
    admitted: list[WorkItem] = []
    deferred: list[DispatchOutcome] = []
    refused: list[tuple[WorkItem, str]] = []
    for item in candidates:
        if wip_cap is not None and occupied >= wip_cap:
            outcome = _rework_deferred_outcome(item=item, occupied=occupied, wip_cap=wip_cap)
            journal.append(record={"stage": "outcome", "outcome": asdict(outcome)})
            deferred.append(outcome)
            continue
        dispatch_id = selfup.run_id()
        refusal = claim_rework_row(
            repo=repo,
            journal=journal,
            item_id=item.id,
            dispatch_id=dispatch_id,
            planned=rows.get(item.id),
            resume=item.id in resume_ids,
            explicit_factory=explicit_factory,
        )
        if refusal is not None:
            refused.append((item, refusal))
            continue
        _ = write_dispatch_lock(repo=repo, work_item_id=item.id, dispatch_id=dispatch_id)
        journal.append(
            record={
                "stage": REWORK_ADMIT_STAGE,
                "work_item_id": item.id,
                "assignee": item.assignee,
                "rework_pending": True,
            }
        )
        admitted.append(item)
        occupied += 1
    return ReworkAdmission(
        admitted=tuple(admitted), deferred=tuple(deferred), refused=tuple(refused)
    )


def projected_rework_candidates(
    *,
    repo: Path,
    items: list[WorkItem],
    journal: JournalFile,
    rework: ReworkPass,
) -> tuple[WorkItem, ...]:
    """The rows the rework leg WOULD drive, computed without side effects.

    Read through the accounting's READ-ONLY projection, because both callers
    ask a question rather than run a pass: `--dry-run` must report exactly the
    selection the same invocation would dispatch while mutating nothing, and
    the `--item` preflight decides eligibility long before the admitting pass
    exists. The admitting variant of the same accounting journals
    abandoned-claim rows, which would attribute a pass's bookkeeping to a
    question that never dispatched anything.
    """
    projection = claimed_active_projection(repo=repo, items=items, journal=journal)
    return rework_pending_candidates(
        items=items,
        accounting=projection,
        rework=rework,
        ready_aging=ready_aging_order(project_root=repo),
    )


def rework_redispatch_eligible_ids(
    *,
    repo: Path,
    items: list[WorkItem],
    journal: JournalFile,
) -> frozenset[str]:
    """The ids a `--item` narrowing may name in addition to the ready set.

    Unnarrowed and unbounded by construction: this answers "could this item be
    named at all?", so applying the caller's own narrowing here would make the
    question answer itself.
    """
    return frozenset(
        item.id
        for item in projected_rework_candidates(
            repo=repo, items=items, journal=journal, rework=ReworkPass()
        )
    )


def _rework_deferred_outcome(*, item: WorkItem, occupied: int, wip_cap: int) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=item.id,
        status="capacity-deferred",
        stage="rework-capacity-deferred",
        pr_number=None,
        merge_sha=None,
        detail=(
            f"rework re-dispatch deferred: work-item {item.id} carries rework:pending"
            f" and holds no live dispatch lock, but other_active_count={occupied}"
            f" is not below wip_cap={wip_cap}; it stays marked and is re-selected by"
            " a later drain pass."
        ),
    )
