"""The completion valve's claim-changing writes, under the claim-token cutover.

Split from `_dispatcher_completion`, which is at its size ceiling. That module
decides WHAT a green or non-converging dispatch does to its item; this one is
how each of those ledger writes is made once `dispatcher.claim_tokens` is true.
`SPECIFICATION/contracts.md` ("Claim tokens") makes every Dispatcher terminal
write a claim-changing write, so each of them goes through
`_dispatcher_claim_writes`.

THE STORE WRITERS ARE HANDED IN BY THE VALVE and not imported here. With the
key false or unset each is called exactly as `_dispatcher_completion` called it
before this module existed, and a close is preceded by no write at all.

A CLOSE IS TWO WRITES ONCE THE KEY IS TRUE. `bd close` is its own verb and
cannot name a successor token, so the valve first wins the item's current token
in a write that names the successor and changes nothing else, and closes only
after that write landed. A valve that loses the token never reaches the close.

Every method answers `None` when its write landed and the claim-token
protocol's outcome when it did not. A refused write has written nothing to the
item and is journaled once, as `claim-write-refused`.

EACH WRITE STATES WHAT THE VALVE DECIDED ON. The claim is built from the item
and the outcome the valve was handed, so the completion and the bounce rest on
that item's status and assignee and on a claim stamp that names no other run,
and a close rests on the `acceptance` the completion itself just wrote.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_guard import (
    Decided,
    claimed_by_run,
    terminal_claim,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_writes import (
    claim_hold,
    claim_status_write,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import (
    DispatchOutcome,
    JournalWriter,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_reconcile_hook import (
    reconcile_after_lifecycle_write,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = ["CompletionClaim"]

_ACCEPTANCE_STATUS = "acceptance"
_BACKLOG_STATUS = "backlog"


@dataclass(frozen=True, kw_only=True)
class CompletionClaim:
    """One dispatched item's claim, as the completion valve is about to change it."""

    repo: Path
    path: StoreConfig
    item: WorkItem
    outcome: DispatchOutcome
    journal: JournalWriter

    def _as_handed(self) -> Decided:
        """The claim as the valve was handed it, under the run its outcome names."""
        return terminal_claim(item=self.item, run_id=self.outcome.fabro_run_id)

    def complete(self, *, write: Callable[..., None]) -> str | None:
        """The `active -> acceptance` completion of a merged dispatch.

        `write` is the valve's own writer, which reconciles the item's runs
        after it lands. A guarded write does not pass through it, so the same
        reconciliation is run here once the guarded write has landed.
        """
        return claim_status_write(
            repo=self.repo,
            path=self.path,
            intent="complete",
            write=write,
            item_id=self.item.id,
            status=_ACCEPTANCE_STATUS,
            reconcile=reconcile_after_lifecycle_write,
            journal=self.journal,
            still_as_decided=self._as_handed(),
        )

    def hold_for_close(self, *, intent: str) -> str | None:
        """Win the item's token ahead of a close; before the cutover, write nothing."""
        return claim_hold(
            repo=self.repo,
            path=self.path,
            intent=intent,
            item_id=self.item.id,
            journal=self.journal,
            # A close follows the completion, which left the item in `acceptance`.
            still_as_decided=claimed_by_run(
                assignee=self.item.assignee,
                run_id=self.outcome.fabro_run_id,
                status=_ACCEPTANCE_STATUS,
                unstamped_ok=True,
            ),
        )

    def bounce(self, *, write: Callable[..., None]) -> str | None:
        """The non-convergence bounce of a claim to `backlog`."""
        return claim_status_write(
            repo=self.repo,
            path=self.path,
            intent="non-convergence-bounce",
            write=write,
            item_id=self.item.id,
            status=_BACKLOG_STATUS,
            journal=self.journal,
            still_as_decided=self._as_handed(),
        )
