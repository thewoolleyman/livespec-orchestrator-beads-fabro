"""Admission's size-decomposition route to `backlog`, under the claim-token cutover.

An item whose assertion count exceeds the adopted ceiling without a recorded
justification is refused at a dispatch entry and routed to `backlog` for
decomposition. That route changes the item's status and is made by admission,
so it is a claim-changing write (`SPECIFICATION/contracts.md`, "Claim tokens")
at both places the Dispatcher makes it: the dispatch-entry size gate and the
groom door.

THE STORE ROUTE IS HANDED IN and not imported here. With
`dispatcher.claim_tokens` false or unset it is called exactly as each caller
called it before this module existed, and it writes what it always wrote: the
`backlog` status, then a ledger comment carrying the reason.

WITH THE KEY TRUE THE TOKEN-CARRYING PART IS ONE WRITE. It sends the `backlog`
status and nothing else, as the store route does, and names the successor
token. It lands only after this route has won the item's current claim token.
The comment is a second write, as it always was, made only once the first has
landed: a route that loses the token writes nothing to the item and comments
nothing, because a comment saying the item was routed would be false.

A REFUSED ROUTE STILL REFUSES THE DISPATCH. The item is oversized whoever holds
its claim, so the entry does not admit it. The refusal is reported at its own
stage, naming the protocol outcome, so the result does not claim a route to
`backlog` that never happened.

A STORE CONFIGURATION NAMING NO REPOSITORY has no committed key to read. Every
configuration the Dispatcher resolves names one, so this is a hand-built
configuration, and the route is made as it was before the cutover.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from livespec_orchestrator_beads_fabro._store_comments import append_work_item_comment
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_guard import (
    guarded_write,
    status_is,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_writes import (
    WRITER_ADMISSION,
    settle_claim_write,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import JournalWriter
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_outcomes import (
    failed_dispatch_outcome,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = [
    "SIZE_DECOMPOSITION_CLAIM_REFUSED_STAGE",
    "SIZE_DECOMPOSITION_STAGE",
    "route_size_decomposition",
    "routed_size_refusal",
]

SIZE_DECOMPOSITION_STAGE = "size-decomposition"
SIZE_DECOMPOSITION_CLAIM_REFUSED_STAGE = "size-decomposition-claim-refused"

_INTENT = "size-decomposition"
_BACKLOG_STATUS = "backlog"


def route_size_decomposition(  # noqa: PLR0913 — kw-only; one route, its store writer and its audit.
    *,
    repo: Path | None,
    path: StoreConfig,
    work_item_id: str,
    status: str,
    reason: str,
    journal: JournalWriter,
    route: Callable[..., None],
) -> str | None:
    """Route one oversized item to `backlog`; `None` when routed, else the refusal.

    `status` is where the item rested when the size gate judged it. A guarded
    route lands only while the item still rests there: an item another writer
    has since moved is not this gate's to send to `backlog`.
    """
    if repo is None:
        route(path=path, work_item_id=work_item_id, reason=reason)
        return None
    return settle_claim_write(
        repo=repo,
        item_id=work_item_id,
        writer=WRITER_ADMISSION,
        intent=_INTENT,
        journal=journal,
        unguarded=lambda: route(path=path, work_item_id=work_item_id, reason=reason),
        guarded=lambda: _route_guarded(
            path=path, work_item_id=work_item_id, status=status, reason=reason
        ),
    )


def _route_guarded(*, path: StoreConfig, work_item_id: str, status: str, reason: str) -> str | None:
    """Win the token and land `backlog`; comment the reason only once that landed."""
    refusal = guarded_write(
        path=path,
        item_id=work_item_id,
        writer=WRITER_ADMISSION,
        intent=_INTENT,
        status=_BACKLOG_STATUS,
        still_as_decided=status_is(status=status),
    )
    if refusal is None:
        append_work_item_comment(path=path, work_item_id=work_item_id, body=reason)
    return refusal


def routed_size_refusal(
    *,
    path: StoreConfig,
    item: WorkItem,
    reason: str,
    journal: JournalFile,
    route: Callable[..., None],
) -> DispatchOutcome:
    """Route an oversized item at a dispatch entry and build the entry's refusal."""
    refusal = route_size_decomposition(
        repo=path.repo_root,
        path=path,
        work_item_id=item.id,
        status=item.status,
        reason=reason,
        journal=journal,
        route=route,
    )
    if refusal is None:
        return failed_dispatch_outcome(
            journal=journal,
            work_item_id=item.id,
            stage=SIZE_DECOMPOSITION_STAGE,
            detail=reason,
        )
    return failed_dispatch_outcome(
        journal=journal,
        work_item_id=item.id,
        stage=SIZE_DECOMPOSITION_CLAIM_REFUSED_STAGE,
        detail=(
            f"{reason}; the item was not routed to backlog because the claim-token "
            f"protocol reported {refusal}, and nothing was written to it"
        ),
    )
