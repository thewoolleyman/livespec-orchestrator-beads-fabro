"""The plan-authority epoch chain: the ONE surface a plan writer calls.

A plan epic's authority is a chain of single-use token records. A transition
commits by closing the CURRENT open token through the public
`bd close <token> --reason <payload>`, which is a server-enforced
compare-and-swap, so exactly one writer's transition is admitted from any one
epoch however many are racing and whatever hosts they run on
(`.ai/ledger-writers-are-multi-host.md`; relay research note 005).

FIVE PROPERTIES AN EDITOR MUST NOT INVERT.

THE WINNER IS READ, NEVER INFERRED. `attempt_close` learns nothing: a losing
writer exits 0 when its conditional update matched no row, or exits 1 with
Dolt `Error 1213`, and 22 of 80 closer exits were non-zero across relay
research note 005's 20 trials. So a non-zero close is "outcome unknown until
read back" and the `close_reason` comparison is the whole verdict. Treating
either exit as a verdict would hand two writers the same epoch, or make a
winner discard its own committed transition.

A CLOSE NOBODY COULD READ IS NEITHER OUTCOME, and it keeps its candidate. The
read-back has three answers, not two: the reason this writer rendered, a
different reason, or no reading at all — and `token_reading` reports the third
as `present=False` with no close reason, which compares unequal exactly as a
rival's reason does. A winner whose read-back failed would therefore delete
the candidate its OWN COMMITTED PAYLOAD names as `next_token_id`, leaving the
chain pointing at a token that no longer exists and no walk able to repair it.
So an absent reading is reported and the candidate is left standing, because
a leaked token is recoverable and a severed chain is not.

THE LOSER CHANGES NO AUTHORITY AND TAKES ITS CANDIDATE WITH IT. Its only write
was a candidate token nothing links to, which it deletes; the projections it
never reached are the winner's to write.

THE PROGRESS EVENT IS PROJECTED BEFORE THE CACHE, and the order is load-bearing
rather than tidy. A writer that stops between the close and the projections
leaves a partial write either way, but the two are not equally recoverable: a
missing cache is reconciled by walking the chain forward, while a missing
progress event is the one record a retry of that operation recovers its
original transition from. So the harder loss is written first.

A COMMITTED OPERATION IS NEVER COMMITTED TWICE. A retry carrying an operation
id the chain already holds recovers the ORIGINAL event, from the epic's
progress events, and creates no transition — so no handoff is duplicated and
no deadline moves. The bounded receipt ring in the observed authority is the
second half of that check and it is the FAIL-CLOSED half: when the ring names
an operation whose event cannot be read, the retry is REPORTED rather than
committed afresh, because the ring is proof the transition happened and a
fresh commit would duplicate the handoff it accounts for.

THAT SCAN IS ALSO PUBLIC, as `recover_committed_operation`, because a caller
has to be able to ask the question BEFORE it decides what to commit. Inside
`commit_transition` the scan is the chain's own last guard, and a caller that
refuses the write before reaching it — a plan writer whose obligation budget is
exhausted, say — never gets the recovery the clause owes it, however correct
the guard is. The public form answers the same question from the same two
sources and performs no write at all, so asking early costs one comment read
and can change nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro.commands._plan_epoch_chain_head import (
    ChainHead,
    read_chain_head,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_findings import (
    ChainFinding,
    close_outcome_unknown_finding,
    receipt_without_event_finding,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_payload import (
    OperationReceipt,
    TransitionPayload,
    carrying_receipts,
    parse_payload,
    render_payload,
    with_receipt,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_projection import (
    read_progress_events,
    write_chain_cache,
    write_progress_event,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_tokens import (
    attempt_close,
    create_token,
    discard_token,
    token_reading,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient
    from livespec_orchestrator_beads_fabro.commands._plan_epoch_payload import AuthorityState
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "COMMITTED",
    "RECOVERED_FROM_PROGRESS_EVENT",
    "RECOVERED_FROM_RECEIPT_RING",
    "ChainHead",
    "CommittedTransition",
    "StaleEpochRefusal",
    "TransitionRequest",
    "commit_transition",
    "read_chain_head",
    "recover_committed_operation",
]

# How a returned transition came to be. The three are kept apart because a
# caller that cannot tell a fresh commit from a recovery cannot tell whether
# its own write happened, which is the question a retry exists to ask — and
# the two recoveries say different things about how far behind that caller is:
# the ring was in the authority it already held, while an event had to be
# found by scanning the epic's history.
COMMITTED = "committed"
RECOVERED_FROM_RECEIPT_RING = "recovered-from-receipt-ring"
RECOVERED_FROM_PROGRESS_EVENT = "recovered-from-progress-event"


@dataclass(frozen=True, kw_only=True)
class TransitionRequest:
    """One writer's intended transition, and the head it observed.

    `observed_head` carries the TOKEN RECORD this writer read, not merely the
    epoch number it saw. The token is what the close is conditional on, so a
    request naming only an epoch would have to re-read the chain to find a
    token — and would then be racing against its own re-read.
    """

    operation_id: str
    observed_head: ChainHead
    authority: AuthorityState
    event_kind: str
    author: str
    now: str


@dataclass(frozen=True, kw_only=True)
class CommittedTransition:
    """A transition that is durable in the chain, freshly or already."""

    payload: TransitionPayload
    source: str


@dataclass(frozen=True, kw_only=True)
class StaleEpochRefusal:
    """A writer refused because another transition already took its epoch.

    `winning_operation_id` is None only when the winning transition could not
    be read — a chain whose token is gone, or whose close reason is not a
    payload. It is never a guess: naming the wrong operation as the winner
    would send an operator to reconcile against a transition that never
    happened.
    """

    epic_id: str
    attempted_operation_id: str
    observed_epoch: int
    winning_operation_id: str | None
    detail: str


def commit_transition(
    *,
    config: StoreConfig,
    epic_id: str,
    request: TransitionRequest,
) -> CommittedTransition | StaleEpochRefusal | ChainFinding:
    """Commit one authority transition, recover a retry, or refuse as stale."""
    client = make_beads_client(config=config)
    already = _already_committed(
        client=client,
        epic_id=epic_id,
        operation_id=request.operation_id,
        observed_head=request.observed_head,
    )
    if already is not None:
        return already
    observed = request.observed_head.current_token_id
    before = token_reading(client=client, token_id=observed)
    if not before.present:
        return _refusal(
            request=request,
            epic_id=epic_id,
            winner=None,
            detail=f"the observed token {observed} is no longer present",
        )
    if before.closed:
        return _refusal_from_reason(
            request=request,
            epic_id=epic_id,
            reason=before.close_reason,
            detail_prefix=f"the observed token {observed} was already closed",
        )
    return _close_and_project(client=client, epic_id=epic_id, request=request)


def _close_and_project(
    *,
    client: BeadsClient,
    epic_id: str,
    request: TransitionRequest,
) -> CommittedTransition | StaleEpochRefusal | ChainFinding:
    """Create the candidate, attempt the close, and read back who won."""
    head = request.observed_head
    candidate = create_token(client=client)
    payload = TransitionPayload(
        operation_id=request.operation_id,
        prior_epoch=head.epoch,
        new_epoch=head.epoch + 1,
        prior_token_id=head.current_token_id,
        next_token_id=candidate,
        event_kind=request.event_kind,
        authority=with_receipt(
            state=carrying_receipts(
                state=request.authority,
                receipts=head.authority.receipts,
            ),
            receipt=OperationReceipt(
                operation_id=request.operation_id,
                epoch=head.epoch + 1,
                recorded_at=request.now,
            ),
        ),
    )
    rendered = render_payload(payload=payload)
    attempt_close(client=client, token_id=head.current_token_id, reason=rendered)
    settled = token_reading(client=client, token_id=head.current_token_id)
    if not settled.present:
        return close_outcome_unknown_finding(
            epic_id=epic_id,
            token_id=head.current_token_id,
            candidate_token_id=candidate,
            operation_id=request.operation_id,
        )
    if settled.close_reason != rendered:
        discard_token(client=client, token_id=candidate)
        return _refusal_from_reason(
            request=request,
            epic_id=epic_id,
            reason=settled.close_reason,
            detail_prefix=f"the close of token {head.current_token_id} was not admitted",
        )
    write_progress_event(
        client=client,
        epic_id=epic_id,
        payload=payload,
        author=request.author,
        now=request.now,
    )
    write_chain_cache(
        client=client,
        epic_id=epic_id,
        latest_closed=head.current_token_id,
        current=candidate,
    )
    if head.latest_closed_token_id is not None:
        discard_token(client=client, token_id=head.latest_closed_token_id)
    return CommittedTransition(payload=payload, source=COMMITTED)


def recover_committed_operation(
    *,
    config: StoreConfig,
    epic_id: str,
    operation_id: str,
    observed_head: ChainHead,
) -> CommittedTransition | ChainFinding | None:
    """What the chain already holds for one operation id, asked WITHOUT writing.

    `None` means the chain holds nothing for this operation, which is the only
    answer under which a caller may go on to decide a fresh transition. The
    reading is the same one `commit_transition` takes as its own guard, and it
    is deliberately not shared state: a caller that asks early and then commits
    is scanned twice, because the chain's guard is the one the exclusion depends
    on and a guard a caller could satisfy on its behalf is no guard.
    """
    return _already_committed(
        client=make_beads_client(config=config),
        epic_id=epic_id,
        operation_id=operation_id,
        observed_head=observed_head,
    )


def _already_committed(
    *,
    client: BeadsClient,
    epic_id: str,
    operation_id: str,
    observed_head: ChainHead,
) -> CommittedTransition | ChainFinding | None:
    """Return what the chain already holds for this operation id, else None.

    The EVENTS are read on every call, not only when the ring names the
    operation, because the ring is bounded: an operation older than
    `RECEIPT_RING_SIZE` transitions is absent from it while its event is still
    on the timeline, and keying on the ring alone would read that retry as new
    work. The cost is one comment read per transition, which is the price of
    the only record that carries the transition itself.
    """
    named_by_ring = any(
        receipt.operation_id == operation_id for receipt in observed_head.authority.receipts
    )
    for event in read_progress_events(client=client, epic_id=epic_id):
        if event.operation_id != operation_id:
            continue
        if event.payload is None:
            return receipt_without_event_finding(epic_id=epic_id, operation_id=operation_id)
        return CommittedTransition(
            payload=event.payload,
            source=RECOVERED_FROM_RECEIPT_RING if named_by_ring else RECOVERED_FROM_PROGRESS_EVENT,
        )
    if named_by_ring:
        return receipt_without_event_finding(epic_id=epic_id, operation_id=operation_id)
    return None


def _refusal_from_reason(
    *,
    request: TransitionRequest,
    epic_id: str,
    reason: str | None,
    detail_prefix: str,
) -> StaleEpochRefusal:
    """Name the winner from the close reason that actually stands."""
    payload = None if reason is None else parse_payload(text=reason)
    if payload is None:
        return _refusal(
            request=request,
            epic_id=epic_id,
            winner=None,
            detail=f"{detail_prefix}, and its close reason carries no readable transition",
        )
    return _refusal(
        request=request,
        epic_id=epic_id,
        winner=payload.operation_id,
        detail=f"{detail_prefix} by operation {payload.operation_id}",
    )


def _refusal(
    *,
    request: TransitionRequest,
    epic_id: str,
    winner: str | None,
    detail: str,
) -> StaleEpochRefusal:
    return StaleEpochRefusal(
        epic_id=epic_id,
        attempted_operation_id=request.operation_id,
        observed_epoch=request.observed_head.epoch,
        winning_operation_id=winner,
        detail=detail,
    )
