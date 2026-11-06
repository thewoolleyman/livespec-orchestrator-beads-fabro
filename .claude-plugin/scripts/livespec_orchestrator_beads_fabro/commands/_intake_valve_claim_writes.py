"""Intake's and the human valves' claim-changing writes, under the claim-token cutover.

`SPECIFICATION/contracts.md` ("Claim tokens") names five writers of a dispatch
claim. `_dispatcher_claim_writes` routes the three that belong to the
Dispatcher. This module routes the other two: intake and a human valve, which
here includes the `driver-dispatch` door and the `reconcile-merged --regrade`
arm. While the committed key `dispatcher.claim_tokens` is `true`, each of them
may change an item's status or its `fabro` assignee only after winning the
item's current token, and must name the successor in that one write.

THE DECISION IS THE DISPATCHER'S, REUSED. Every write here ends in
`settle_claim_write`, so the key is read the same way for all five writers: an
absent file or key is `false`, and a key that cannot be read withholds the write
as `claim-tokens-unreadable`.

THE UNGUARDED WRITER STAYS AT THE CALL SITE AND IS HANDED IN. While the key is
`false` or unset, the write is the caller's own store call, exactly as that
caller made it before this module existed.

A REFUSAL IS A RETURN VALUE, NEVER AN EXCEPTION. Every write answers `None`
when it landed and the protocol's outcome name when it did not (`claim-changed`
for a lost token). A refused writer has written nothing to the item. Ledger
faults still raise.

A ONE-SHOT WRITER WAITS OUT AN UNAPPLIED TRANSITION ITSELF. A writer whose
winner closed the item's token and then failed before its item write leaves
the item naming a closed token. The protocol (step 5) lets another writer take
the successor over only after that writer has itself watched the unapplied
transition for the takeover wait, on its own monotonic clock. A Dispatcher
loop does that across passes. Intake and a valve press are one process each,
so a press that only reported `claim-transition-pending` would start the next
press with no observation and report it again, for ever. So when a guarded
write here reports `claim-transition-pending`, the same process says so on
stderr, waits out the takeover wait (`TakeoverWait`, about three minutes) and
makes the write again, once. The second answer is final. Nothing waits while
the key is `false`, or for any other outcome.

EVERY WRITE STATES WHAT ITS DECISION RESTED ON. The token alone excludes two
writers that contest it at the same instant. It does not stop a writer that
decided on an earlier read and writes after another writer has finished: that
writer would simply win the successor the first one named. So each `ClaimWrite`
carries `still_as_decided`, a predicate over the item record that is read with
the token. When it is false nothing is closed or written and the outcome is
`claim-changed`. `resting_at` builds the predicate these writers need: the
status the writer read, and the labels its own precondition checked.

THE REPOSITORY IS THE STORE DESCRIPTOR'S, UNLESS THE CALLER NAMES ONE. Intake
and two of the valves are handed a `StoreConfig` and no repository path. Every
descriptor resolved through `resolve_store_config` carries its `repo_root`. A
descriptor with none has no `.livespec.jsonc` to read the key from, so the
write is made unguarded, which is the rule
`_dispatcher_run_reconcile_hook.reconcile_after_lifecycle_write` already
follows for the same descriptor.

A RAW WRITE IS SENT UNCHANGED. `write_raw` hands `guarded_write` the fields its
caller names and nothing else, for the writes that the store's status writer
does not make: intake's routing write, the size-decomposition route and the
transition out of `blocked`. A guarded write of one of those therefore differs
from the unguarded one only by the token.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from livespec_orchestrator_beads_fabro._beads_client import BeadsRecord, make_beads_client
from livespec_orchestrator_beads_fabro._store_blocked_mutations import blocked_reason_labels
from livespec_orchestrator_beads_fabro._store_claim_tokens import TRANSITION_WAIT_SECONDS
from livespec_orchestrator_beads_fabro._store_factory_size_gate import (
    route_factory_size_decomposition,
)
from livespec_orchestrator_beads_fabro._store_rework_mutations import (
    rework_pending_label_removals,
)
from livespec_orchestrator_beads_fabro._store_statuses import beads_status_for
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_guard import (
    guarded_hold,
    guarded_status_write,
    guarded_write,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_writes import (
    settle_claim_write,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import JournalWriter
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_reconcile_hook import (
    reconcile_after_lifecycle_write,
)
from livespec_orchestrator_beads_fabro.commands._drive_valve_result import valve_refusal
from livespec_orchestrator_beads_fabro.io import write_stderr
from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "WRITER_HUMAN_VALVE",
    "WRITER_INTAKE",
    "ClaimWrite",
    "ClaimWriteRefused",
    "TakeoverWait",
    "resting_at",
    "valve_claim_refusal",
]

# The two writers the contract names beside the Dispatcher's three. The name is
# recorded in the token's close reason with the intent, which names the verb.
WRITER_INTAKE = "intake"
WRITER_HUMAN_VALVE = "human-valve"

_BACKLOG_STATUS = "backlog"
_TRANSITION_PENDING = "claim-transition-pending"
# Said on stderr before the process blocks, so a press that takes three minutes
# is not a silent one.
_WAITING = (
    "NOTICE: work-item {write.item_id} names a claim token that another writer closed "
    "without finishing its item write, so {write.writer} ({write.intent}) found "
    "claim-transition-pending. Waiting {seconds:.0f} seconds, the protocol's takeover "
    "wait, and then making this write once more.\n"
)


@dataclass(frozen=True, kw_only=True)
class ClaimWriteRefused:
    """An intake write the claim-token protocol refused: nothing was written.

    Intake answers on a result track, so its refusal is a failure value and not
    a routed status: the item was not routed, and a caller reading a status
    here would report a transition that never happened.
    """

    work_item_id: str
    writer: str
    intent: str
    outcome: str


def resting_at(*, status: str, labels: tuple[str, ...] = ()) -> Callable[[BeadsRecord], bool]:
    """The predicate "still at `status`, still carrying every one of `labels`".

    `status` is the livespec status the writer read. `labels` are the raw
    ledger labels its own precondition checked, such as the needs-human reason
    a `resolve-blocked` press requires. A record that omits its label list
    carries none: `bd` leaves out a field that holds its zero value.
    """
    expected = beads_status_for(status=status)
    return lambda record: record.get("status") == expected and _carries(
        record=record, labels=labels
    )


def _carries(*, record: BeadsRecord, labels: tuple[str, ...]) -> bool:
    carried = record.get("labels")
    present = cast("list[object]", carried) if isinstance(carried, list) else []
    return all(label in present for label in labels)


@dataclass(frozen=True, kw_only=True)
class TakeoverWait:
    """How a one-shot writer waits out an unapplied transition before its one retry.

    `seconds` is the protocol's own takeover wait. `change_claim` records its
    first observation of the unapplied transition on `time.monotonic`, before
    this wait starts, so `seconds` elapsed on that same clock from a later
    reading is always at least the takeover wait since that observation.
    `clock` and `sleep` are fields so a test supplies both and never sleeps.
    """

    seconds: float = TRANSITION_WAIT_SECONDS
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep

    def wait_out(self) -> None:
        """Return once `seconds` have elapsed on `clock`, however short `sleep` slept."""
        deadline = self.clock() + self.seconds
        while (remaining := deadline - self.clock()) > 0:
            self.sleep(remaining)


@dataclass(frozen=True, kw_only=True)
class ClaimWrite:
    """One claim-changing write by intake or a human valve, and what it was decided on.

    `repo` is the repository whose committed key selects the writer; `None`
    reads the descriptor's own. `journal` is the caller's journal when it has
    one: a refusal is then journaled once, as `claim-write-refused`.
    `takeover_wait` is how a write that finds an unapplied transition waits
    before its one retry; `None` is the protocol's wait on the real clock.
    """

    path: StoreConfig
    item_id: str
    writer: str
    intent: str
    still_as_decided: Callable[[BeadsRecord], bool]
    repo: Path | None = None
    journal: JournalWriter | None = None
    takeover_wait: TakeoverWait | None = None

    def write_status(
        self,
        *,
        status: str,
        unguarded: Callable[[], None],
        clear_assignee: bool = False,
        reconcile: bool = False,
    ) -> str | None:
        """Make a transition the store's status writer makes, guarded once the key is true.

        `reconcile` is true for a caller whose unguarded writer reconciles the
        item's runs after it lands. A guarded write does not pass through that
        writer, so the same reconciliation is run here once it has landed.
        """
        return self._settle(
            unguarded=unguarded,
            guarded=lambda: guarded_status_write(
                path=self.path,
                item_id=self.item_id,
                status=status,
                intent=self.intent,
                writer=self.writer,
                clear_assignee=clear_assignee,
                still_as_decided=self.still_as_decided,
            ),
            landed=self._reconciler(status=status) if reconcile else None,
        )

    def write_raw(
        self, *, unguarded: Callable[[], None], reconcile_status: str | None = None, **update: Any
    ) -> str | None:
        """Make a raw item write, guarded once the key is true.

        `update` is what the guarded write sends, field for field.
        `reconcile_status` is the livespec status the write lands the item on,
        for a caller whose unguarded writer reconciles the item's runs
        afterwards.
        """
        return self._settle(
            unguarded=unguarded,
            guarded=lambda: self._guarded(**update),
            landed=None if reconcile_status is None else self._reconciler(status=reconcile_status),
        )

    def write_cleared_block(self, *, status: str, unguarded: Callable[[], None]) -> str | None:
        """Move an item out of `blocked` with its reason cleared, guarded once the key is true.

        The guarded write sends what `update_work_item_blocked_state` sends for
        a cleared reason, in the one write the protocol allows its winner, and
        then reconciles the item's runs as the lifecycle seam does for the
        unguarded one. It is not a status write: that store writer stamps no
        ready-dwell instant, so neither does this.
        """
        return self.write_raw(
            unguarded=unguarded,
            reconcile_status=status,
            status=beads_status_for(status=status),
            remove_labels=blocked_reason_labels() + rework_pending_label_removals(status=status),
        )

    def write_size_decomposition(self, *, reason: str) -> str | None:
        """Route one oversized item to `backlog` with its reason, guarded once the key is true.

        The reason is a comment and follows the status write, as it does
        unguarded. A route that loses the token writes neither.
        """
        client = make_beads_client(config=self.path)
        return self._settle(
            unguarded=lambda: route_factory_size_decomposition(
                path=self.path, work_item_id=self.item_id, reason=reason
            ),
            guarded=lambda: self._guarded(status=_BACKLOG_STATUS),
            landed=lambda: client.add_comment(issue_id=self.item_id, body=reason),
        )

    def hold(self) -> str | None:
        """Win the item's token ahead of a close; before the cutover, write nothing.

        `bd close` is its own verb and cannot name a successor, so the winner
        names it in this write and the caller closes only after it landed.
        """
        return self._settle(
            unguarded=lambda: None,
            guarded=lambda: guarded_hold(
                path=self.path,
                item_id=self.item_id,
                intent=self.intent,
                writer=self.writer,
                still_as_decided=self.still_as_decided,
            ),
            landed=None,
        )

    def refused(self, *, outcome: str) -> ClaimWriteRefused:
        """This write's refusal, as the failure value intake answers with."""
        return ClaimWriteRefused(
            work_item_id=self.item_id, writer=self.writer, intent=self.intent, outcome=outcome
        )

    def _guarded(self, **update: Any) -> str | None:
        return guarded_write(
            path=self.path,
            item_id=self.item_id,
            writer=self.writer,
            intent=self.intent,
            still_as_decided=self.still_as_decided,
            **update,
        )

    def _settle(
        self,
        *,
        unguarded: Callable[[], None],
        guarded: Callable[[], str | None],
        landed: Callable[[], None] | None,
    ) -> str | None:
        """Run the writer the committed key selects; `landed` follows a guarded write.

        A guarded write that finds an unapplied transition is made a second
        time after the takeover wait, and that second answer is the one
        reported and journaled.
        """
        where = self.path.repo_root if self.repo is None else self.repo
        if where is None:
            unguarded()
            return None

        def _guarded_then_landed() -> str | None:
            refusal = guarded()
            if refusal == _TRANSITION_PENDING:
                self._wait_out_takeover()
                refusal = guarded()
            if refusal is None and landed is not None:
                landed()
            return refusal

        return settle_claim_write(
            repo=where,
            item_id=self.item_id,
            writer=self.writer,
            intent=self.intent,
            unguarded=unguarded,
            guarded=_guarded_then_landed,
            journal=self.journal,
        )

    def _wait_out_takeover(self) -> None:
        """Say why this process is about to block, then wait out the takeover wait."""
        wait = TakeoverWait() if self.takeover_wait is None else self.takeover_wait
        _ = write_stderr(text=_WAITING.format(write=self, seconds=wait.seconds))
        wait.wait_out()

    def _reconciler(self, *, status: str) -> Callable[[], None]:
        """The post-write run reconciliation the lifecycle seam runs for an unguarded write."""
        return lambda: reconcile_after_lifecycle_write(
            path=self.path, item_id=self.item_id, status=status
        )


def valve_claim_refusal(
    *, aid: str, wid: str, verb: str, outcome: str, already_done: str | None = None
) -> dict[str, Any]:
    """The failed valve payload for a write the claim-token protocol refused.

    The protocol's own outcome name is the `domain_error`, so a valve that lost
    its token reports `claim-changed`.

    `already_done` is for a valve whose own order puts a side effect BEFORE its
    guarded write: a reverted merge, an answer comment, a rewritten proof
    pointer. The refused write cannot undo it, so the summary states it and
    says only that the item's status and claim were not written. Without it
    the valve wrote nothing at all, and the summary says so.

    A `claim-transition-pending` reported here has already been waited out and
    retried once by `ClaimWrite`, so the summary says that too.
    """
    refused = f"{verb} refused: the claim-token protocol reported {outcome}"
    if outcome == _TRANSITION_PENDING:
        refused += ", after this press waited out the takeover wait and tried once more"
    written = (
        f"nothing was written to {wid}"
        if already_done is None
        else f"{already_done}; the status and claim of {wid} were not written"
    )
    return valve_refusal(aid=aid, wid=wid, err=outcome, msg=f"{refused}; {written}.")
