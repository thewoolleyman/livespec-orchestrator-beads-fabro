"""Grading and repairing a plan epic's chain projections, and withholding dispatch.

`contracts.md` section "Required result, budget and progress epoch" requires
that "A partial write MUST be diagnosable and must not authorize a fresh
dispatch until reconciled". This module is both halves: `verify_projections`
makes the state diagnosable, `authorized_head` withholds the dispatch while it
stands, and `reconcile_projections` repairs it.

FIVE PROPERTIES AN EDITOR MUST NOT INVERT.

THE CHAIN IS THE AUTHORITY AND THE PROJECTIONS ARE REPAIRED FROM IT, never the
reverse. A transition commits in one server statement and its two projections
are written afterwards, so a disagreement always means the projections lag —
and "reconciling" the chain to match a projection would discard a durable
transition that another writer has already been refused against.

THE TWO PROJECTIONS ARE GRADED SEPARATELY, because they are separate writes
that fail independently: a writer can stop after the progress event and before
the cache. A single combined test would report one as the other, and their
repairs are different writes.

THE RE-PROJECTED EVENT IS REBUILT FROM THE CLOSED TOKEN'S OWN PAYLOAD, not from
the authority the head now carries. The payload is the lossless record of the
transition — its operation id, both epochs, both links and its event kind — and
a reconciler that re-derived the event from current state would publish a
transition nobody committed.

THE RECONCILER SIGNS THE EVENT AS ITSELF. The write it finishes was owed by
another writer that is gone, so no session identity is its honest author — the
same reservation `plan-resume` and `plan-archive` make for the pointers they
write on their own behalf.

THE REPAIR FINISHES THE STOPPED WRITER'S DELETE TOO, and that is what keeps the
two-live-token bound a property of the chain rather than of an uninterrupted
run. A completed commit discards the predecessor of the token it closed; a
writer that stopped after its close never reached that discard, and every later
commit discards only the predecessor of the token IT closed, so the stranded
record is never swept by the ordinary path. Measured on the live tenant
2026-10-13 against released build v0.194.0: one partial write left THREE live
records at every checkpoint of a 60-transition run. The predecessor is read off
the STALE CACHE rather than re-derived, because that cache is what the stopped
writer observed its own head through, so what it still names as the latest
closed token is exactly the record that writer owed a delete for.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro.commands._plan_epoch_chain_head import (
    ChainHead,
    epic_chain_cache,
    walk_chain_head,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_findings import (
    ChainFinding,
    missing_tracking_finding,
    partial_write_finding,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_payload import parse_payload
from livespec_orchestrator_beads_fabro.commands._plan_epoch_projection import (
    read_progress_events,
    write_chain_cache,
    write_progress_event,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_tokens import (
    discard_token,
    token_reading,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient
    from livespec_orchestrator_beads_fabro.commands._plan_epoch_projection import ChainCache
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "PLAN_RECONCILE_ACTOR",
    "authorized_head",
    "reconcile_projections",
    "verify_projections",
]

# The reserved author literal the reconciler signs its own re-projection with,
# computed here rather than accepted from a caller.
PLAN_RECONCILE_ACTOR = "plan-epoch-reconcile"


def verify_projections(*, config: StoreConfig, epic_id: str) -> ChainFinding | None:
    """Report how one epic's projections disagree with its chain, or None."""
    client = make_beads_client(config=config)
    graded = _graded_chain(client=client, epic_id=epic_id)
    if isinstance(graded, ChainFinding):
        return graded
    return graded[2]


def authorized_head(*, config: StoreConfig, epic_id: str) -> ChainHead | ChainFinding:
    """Return the head a dispatch may act on, or the finding that withholds it.

    One call rather than a convention, because "check the projection first" is
    a rule every caller would otherwise have to remember — and a caller that
    forgot would still get a perfectly good head.
    """
    client = make_beads_client(config=config)
    graded = _graded_chain(client=client, epic_id=epic_id)
    if isinstance(graded, ChainFinding):
        return graded
    _, head, finding = graded
    return head if finding is None else finding


def reconcile_projections(
    *,
    config: StoreConfig,
    epic_id: str,
    now: str,
) -> ChainFinding | None:
    """Repair one epic's projections from its chain; report what was reconciled.

    The finding is RETURNED rather than swallowed, because the caller owes the
    partial write a report either way: a repair performed in silence leaves no
    record that a writer stopped mid-transition.
    """
    client = make_beads_client(config=config)
    graded = _graded_chain(client=client, epic_id=epic_id)
    if isinstance(graded, ChainFinding):
        return graded
    cache, head, finding = graded
    if finding is None:
        return None
    _restore_missing_event(client=client, epic_id=epic_id, head=head, now=now)
    write_chain_cache(
        client=client,
        epic_id=epic_id,
        latest_closed=head.latest_closed_token_id,
        current=head.current_token_id,
    )
    _discard_superseded_predecessor(client=client, cache=cache, head=head)
    return finding


def _discard_superseded_predecessor(
    *,
    client: BeadsClient,
    cache: ChainCache,
    head: ChainHead,
) -> None:
    """Delete the predecessor the stopped writer never reached its discard for.

    Runs AFTER both projections, exactly where a completed commit performs the
    same delete: the record is only superseded once the state that replaced it
    is the state a reader will find, and deleting it first would widen the
    window in which a crash leaves the chain shorter than its projections.

    The candidate is the token the STALE cache still names as the latest
    closed, which is what the stopped writer read its own head through — so it
    is that writer's own owed delete rather than a record this reconciler
    chose. It is discarded only when the walk has moved PAST it, because a
    cache that already names the current latest closed describes a partial
    write of some other shape (the event alone), where nothing was stranded
    and the named token is still the one every reader starts from. The discard
    tolerates an absent record for the reason `discard_token` exists: a
    concurrent reconciler may have finished the same delete, and failing a
    completed repair over a record that is already gone would turn a benign
    outcome into a refusal.
    """
    predecessor = cache.latest_closed
    if predecessor is None or predecessor == head.latest_closed_token_id:
        return
    discard_token(client=client, token_id=predecessor)


def _graded_chain(
    *,
    client: BeadsClient,
    epic_id: str,
) -> tuple[ChainCache, ChainHead, ChainFinding | None] | ChainFinding:
    """Walk the chain and grade the projections against it, in that order.

    The order is fail-closed: an epic that names no chain, or whose chain
    cannot be walked, has no authority to grade a projection against, and
    grading first would report a cache disagreement as the finding when the
    chain itself is what cannot be read.
    """
    cache = epic_chain_cache(client=client, epic_id=epic_id)
    if cache is None:
        return missing_tracking_finding(epic_id=epic_id)
    head = walk_chain_head(client=client, epic_id=epic_id, cache=cache)
    if isinstance(head, ChainFinding):
        return head
    stale_cache = cache.current != head.current_token_id or (
        cache.latest_closed != head.latest_closed_token_id
    )
    if stale_cache:
        return (
            cache,
            head,
            partial_write_finding(
                epic_id=epic_id,
                detail=(
                    f"the chain holds epoch {head.epoch} at token {head.current_token_id}, "
                    f"while the cache names current {cache.current} "
                    f"and latest closed {cache.latest_closed}"
                ),
            ),
        )
    if _event_is_missing(client=client, epic_id=epic_id, head=head):
        return (
            cache,
            head,
            partial_write_finding(
                epic_id=epic_id,
                detail=(
                    f"the chain holds epoch {head.epoch} committed by operation "
                    f"{head.winning_operation_id}, which no progress event records"
                ),
            ),
        )
    return (cache, head, None)


def _event_is_missing(*, client: BeadsClient, epic_id: str, head: ChainHead) -> bool:
    """Report whether the latest committed transition has no progress event.

    A genesis-only chain has committed nothing, so it owes no event; answering
    otherwise would report every unused chain as a partial write.
    """
    winner = head.winning_operation_id
    if winner is None:
        return False
    return all(
        event.operation_id != winner
        for event in read_progress_events(client=client, epic_id=epic_id)
    )


def _restore_missing_event(
    *,
    client: BeadsClient,
    epic_id: str,
    head: ChainHead,
    now: str,
) -> None:
    """Re-project the latest committed transition's event, if it is absent.

    Reads the payload back off the closed token rather than taking it from the
    head, because the head carries the authority a transition RESULTED IN while
    the event owes the transition ITSELF — its operation id, its two links and
    its event kind. A payload that cannot be read is left alone: the walk that
    produced this head already proved it parses, so an unreadable one here is a
    chain that changed underneath the repair, and inventing the event would be
    worse than leaving the partial write reported.
    """
    closed = head.latest_closed_token_id
    if closed is None or not _event_is_missing(client=client, epic_id=epic_id, head=head):
        return
    reading = token_reading(client=client, token_id=closed)
    payload = None if reading.close_reason is None else parse_payload(text=reading.close_reason)
    if payload is None:
        return
    write_progress_event(
        client=client,
        epic_id=epic_id,
        payload=payload,
        author=PLAN_RECONCILE_ACTOR,
        now=now,
    )
