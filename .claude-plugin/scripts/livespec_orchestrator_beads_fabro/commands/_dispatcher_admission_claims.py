"""Admitting a row that is ALREADY `active`, once dispatch claims carry tokens.

The admission valve usually claims a `ready` item, and "still `ready`" states
that decision whole: the claiming write itself moves the item off `ready`, so a
second admission that decided on the same read is refused by its own
predicate. Two rows reach the valve already `active`, and for them that
predicate is wrong in both directions:

- A GROOM-DOOR CLAIM. The door moved the item `backlog -> active` under an
  assignee and a groom-variant pin and returned, and the drain then admits the
  row to launch it. "Still `ready`" refuses that admission on every pass.
- A REWORK RE-DISPATCH. The row is `active`, marked `rework:pending`, and still
  stamped with the PREVIOUS dispatch's claim. The rework leg writes no status,
  so before the cutover it writes nothing to the ledger at all.

Neither row's status moves when it is admitted, so status cannot be what the
admission binds to. What an admission of either row does change is the CLAIM
STAMP: it stamps a pending claim naming its own dispatch. So the decision is
stated as the row's whole claim row (status, assignee and stamp) AS THIS PASS
READ IT, and a write lands only on a row that still reads that way.

THE READ IS TAKEN WHEN THE PASS PLANS, NOT WHEN IT WRITES. `planned_claim_rows`
is called before the pass's first ledger write and its answer is carried to
each admission. Two passes that both planned on one state of a row therefore
admit it exactly once: the first to write changes the stamp, and the second is
refused as `claim-changed` however long after the first it writes. A read
taken beside the write would bind to nothing, because the row would already
carry the first admission's stamp.

WHAT THIS DOES NOT REFUSE is a pass that planned AFTER another admission's
write landed. It read the other dispatch's pending stamp, and a pending stamp
is also what a dispatch that died before learning its run leaves behind, which
is exactly the row a later drain must be able to pick up again. The ledger
cannot tell the two apart, so that case stays with the rules that decide
WHETHER a row is a candidate at all: the dispatch lock, and the door's own
recognition of its claim.

WHY THE REWORK LEG NOW WRITES. With `dispatcher.claim_tokens` true the run
stamp and every terminal write of a dispatch are refused on a row whose claim
stamp names another dispatch's run. A rework dispatch that left the previous
stamp in place could therefore never stamp its run or complete, bounce or
release its item, and the item would be re-dispatched for ever. So the rework
admission claims the row for its own dispatch in ONE token-guarded write that
replaces the stamp with a pending one. With the key false or unset it writes
nothing to the ledger, exactly as before.

A PENDING STAMP THAT CANNOT BE BUILT CLEARS THE OLD ONE. Admission stays
fail-open on the stamp, as `_dispatcher_claim_stamp` requires. But leaving the
previous dispatch's stamp on a row this dispatch now holds is the one outcome
that is worse than no stamp: the dispatch's own writes are refused, and a
reconciler reads a claim on a run the factory reports absent. No stamp grades
`claim-unattributable`, which is a hold.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    CLAIM_STAMP_METADATA_KEY,
    ClaimRow,
    claim_row_for,
)
from livespec_orchestrator_beads_fabro._store_rework_mutations import LABEL_REWORK_PENDING
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_guard import (
    Decided,
    guarded_metadata_write,
    same_claim_row,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_stamp import (
    journal_pending_claim_stamp,
    pending_claim_stamp_metadata,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_writes import (
    WRITER_ADMISSION,
    claim_tokens_setting,
    settle_claim_write,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import JournalWriter
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "REWORK_ADMIT_INTENT",
    "claim_rework_row",
    "planned_claim_rows",
]

REWORK_ADMIT_INTENT = "rework-admit"

_ACTIVE_STATUS = "active"


def planned_claim_rows(
    *,
    repo: Path,
    candidates: Iterable[WorkItem],
    items: Iterable[WorkItem] = (),
    rework_ids: Iterable[str] = (),
) -> dict[str, ClaimRow]:
    """The claim row of each already-`active` row this pass may admit, as read now.

    `candidates` are the pass's ready-leg candidates, of which only a groom-door
    claim is `active`. `items` and `rework_ids` name the rework leg's rows: the
    listed items whose ids the accounting marked. Call it before the pass's
    first ledger write, and hand each admission its row.

    Empty, with no ledger read, unless `dispatcher.claim_tokens` is committed
    `true`: an unguarded admission states no decision. A ledger fault raises,
    as it does out of the admission write itself.
    """
    if claim_tokens_setting(repo=repo) is not True:
        return {}
    marked = frozenset(rework_ids)
    config = store_config(repo=repo)
    return {
        item.id: claim_row_for(path=config, work_item_id=item.id)
        for item in (*candidates, *(listed for listed in items if listed.id in marked))
        if item.status == _ACTIVE_STATUS
    }


def claim_rework_row(  # noqa: PLR0913 — kw-only; one rework admission's facts.
    *,
    repo: Path,
    journal: JournalWriter,
    item_id: str,
    dispatch_id: str,
    planned: ClaimRow | None,
    resume: bool = False,
    explicit_factory: str | None = None,
) -> str | None:
    """Claim one marked row for its rework dispatch; `None` when it may launch.

    With `dispatcher.claim_tokens` false or unset this writes nothing and
    answers `None`, which is the rework leg as it always was. With the key true
    the row's claim stamp is replaced by a pending one naming `dispatch_id`, in
    one write that lands only after this admission has won the row's current
    claim token and only on a row that is still `active`, still marked
    `rework:pending`, and still carrying the claim row `planned`. Otherwise
    nothing is written and the protocol's outcome is returned.

    `planned` is this row's entry in `planned_claim_rows`. A caller that planned
    on no read hands `None`, and the row is read here instead, which fences
    only a writer racing on the token.
    """
    return settle_claim_write(
        repo=repo,
        item_id=item_id,
        writer=WRITER_ADMISSION,
        intent=REWORK_ADMIT_INTENT,
        journal=journal,
        unguarded=_write_nothing,
        guarded=lambda: _claim_guarded(
            repo=repo,
            journal=journal,
            item_id=item_id,
            dispatch_id=dispatch_id,
            planned=planned,
            resume=resume,
            explicit_factory=explicit_factory,
        ),
    )


def _write_nothing() -> None:
    """The rework leg's ledger write before the cutover: none."""


def _claim_guarded(  # noqa: PLR0913 — kw-only; one rework admission's facts.
    *,
    repo: Path,
    journal: JournalWriter,
    item_id: str,
    dispatch_id: str,
    planned: ClaimRow | None,
    resume: bool,
    explicit_factory: str | None,
) -> str | None:
    """Win the token, then land the pending stamp and the successor together."""
    config = store_config(repo=repo)
    row = planned if planned is not None else claim_row_for(path=config, work_item_id=item_id)
    built = pending_claim_stamp_metadata(
        repo=repo,
        work_item_id=item_id,
        dispatch_id=dispatch_id,
        resume=resume,
        explicit_factory=explicit_factory,
    )
    unbuilt = built if isinstance(built, str) else None
    stamp: dict[str, Any] = {CLAIM_STAMP_METADATA_KEY: None} if isinstance(built, str) else built
    refusal = guarded_metadata_write(
        path=config,
        item_id=item_id,
        intent=REWORK_ADMIT_INTENT,
        writer=WRITER_ADMISSION,
        metadata=stamp,
        still_as_decided=_marked_row(row=row),
    )
    if refusal is None:
        journal_pending_claim_stamp(
            journal=journal, work_item_id=item_id, dispatch_id=dispatch_id, detail=unbuilt
        )
    return refusal


def _marked_row(*, row: ClaimRow) -> Decided:
    """Still `active`, still marked `rework:pending`, and still claimed as `row` read."""
    unchanged = same_claim_row(row=row)
    # `bd` omits an empty label list from a record rather than sending `[]`.
    return lambda record: (
        unchanged(record) and LABEL_REWORK_PENDING in (record.get("labels") or ())
    )
