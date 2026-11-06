"""The claim-token hold a session-performed close takes before it closes.

`SPECIFICATION/contracts.md` ("Claim tokens") makes any write that changes an
item's status a claim-changing write, and a close changes it. `bd close` is its
own verb and cannot name a successor token, so a closer wins the item's current
token in a HOLD that names the successor and changes nothing else, and closes
only after that write landed (`ClaimWrite.hold`). The Dispatcher's closes and
the groom apply seam already do this. This module is the same hold for the
closes an operator or a plan session makes: `close-work-item`, a plan child
disposition and a plan archive.

THE REFUSAL IS AN EXCEPTION HERE, BECAUSE THESE CALLERS ARE. `ClaimWrite`
answers a refusal as a value, which is right for a valve that reports a payload
and for intake's result track. The three callers here are exception-based
seams whose every expected refusal is a typed error from `errors.py`, so a
lost hold is `ClaimWriteRefusedError`, carrying the protocol's own outcome and
the valve wording (`ClaimWriteRefused`) as its detail. A caller that catches
it has closed nothing.

BEFORE THE CUTOVER NOTHING IS WRITTEN. `ClaimWrite.hold` reads the committed
key of the repository the descriptor names; while it is `false` or unset, or
the descriptor names no repository, the hold is a no-op and the close is the
one write it always was.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._intake_valve_claim_writes import (
    WRITER_HUMAN_VALVE,
    ClaimWrite,
    resting_at,
)
from livespec_orchestrator_beads_fabro.errors import ClaimWriteRefusedError
from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = ["hold_before_close"]


def hold_before_close(
    *,
    path: StoreConfig,
    item_id: str,
    intent: str,
    status: str,
    repo: Path | None = None,
) -> None:
    """Win `item_id`'s current token ahead of a close, or raise `ClaimWriteRefusedError`.

    `status` is the livespec status the caller read the item at: the hold is
    bound to it, so an item another writer moved since that read is not closed
    on the strength of the old read. `repo` is the repository whose committed
    key selects the writer; `None` reads the descriptor's own.
    """
    write = ClaimWrite(
        path=path,
        item_id=item_id,
        writer=WRITER_HUMAN_VALVE,
        intent=intent,
        still_as_decided=resting_at(status=status),
        repo=repo,
    )
    refusal = write.hold()
    if refusal is not None:
        raise ClaimWriteRefusedError(
            item_id=item_id, outcome=refusal, detail=str(write.refused(outcome=refusal))
        )
