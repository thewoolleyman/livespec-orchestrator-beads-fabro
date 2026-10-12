"""The plan-authority epoch chain: the ONE surface a plan writer calls.

A plan epic's authority is a chain of single-use token records. A transition
commits by closing the CURRENT open token through the public
`bd close <token> --reason <payload>`, which is a server-enforced
compare-and-swap, so exactly one writer's transition is admitted from any one
epoch however many are racing and whatever hosts they run on
(`.ai/ledger-writers-are-multi-host.md`; relay research note 005).

FOUR PROPERTIES AN EDITOR MUST NOT INVERT.

THE WINNER IS READ, NEVER INFERRED. `attempt_close` learns nothing: a losing
writer exits 0 when its conditional update matched no row, or exits 1 with
Dolt `Error 1213`, and 22 of 80 closer exits were non-zero across relay
research note 005's 20 trials. So a non-zero close is "outcome unknown until
read back" and the `close_reason` comparison is the whole verdict. Treating
either exit as a verdict would hand two writers the same epoch, or make a
winner discard its own committed transition.

THE LOSER CHANGES NO AUTHORITY AND TAKES ITS CANDIDATE WITH IT. Its only write
was a candidate token nothing links to, which it deletes; the projections it
never reached are the winner's to write.

THE PROGRESS EVENT IS PROJECTED BEFORE THE CACHE, and the order is load-bearing
rather than tidy. A writer that stops between the close and the projections
leaves a partial write either way, but the two are not equally recoverable: a
missing cache is reconciled by walking the chain forward, while a missing
progress event is the one record a retry of that operation recovers its
original transition from. So the harder loss is written first.

EVERY TRANSITION CARRIES ITS OWN RECEIPT into the authority's bounded ring,
which is what later lets a retried operation be recognised as one the chain
already holds rather than committed a second time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro.commands._plan_epoch_chain_head import (
    ChainHead,
    read_chain_head,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_findings import ChainFinding
from livespec_orchestrator_beads_fabro.commands._plan_epoch_payload import (
    OperationReceipt,
    TransitionPayload,
    parse_payload,
    render_payload,
    with_receipt,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_projection import (
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
    "ChainHead",
    "CommittedTransition",
    "StaleEpochRefusal",
    "TransitionRequest",
    "commit_transition",
    "read_chain_head",
]

# How a returned transition came to be. A caller that cannot tell a fresh
# commit from something the chain already held cannot tell whether its own
# write happened, which is the question a retried operation exists to ask.
COMMITTED = "committed"


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
    """Commit one authority transition, or refuse the writer as stale."""
    client = make_beads_client(config=config)
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
) -> CommittedTransition | StaleEpochRefusal:
    """Create the candidate, attempt the close, and read back who won."""
    head = request.observed_head
    candidate = create_token(client=client)
    payload = TransitionPayload(
        operation_id=request.operation_id,
        prior_epoch=head.epoch,
        new_epoch=head.epoch + 1,
        prior_token_id=head.current_token_id,
        next_token_id=candidate,
        authority=with_receipt(
            state=request.authority,
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
        event_kind=request.event_kind,
        author=request.author,
        now=request.now,
    )
    write_chain_cache(
        client=client,
        epic_id=epic_id,
        latest_closed=head.current_token_id,
        current=candidate,
    )
    return CommittedTransition(payload=payload, source=COMMITTED)


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
