"""Reading a plan epic's CURRENT authority by walking its token chain forward.

The epic's `plan_epoch_chain` metadata is a cache, not an authority: it names
where to start, and the walk follows each closed token's own
`next_token_id` link until it reaches an open token. That is what makes a lost
cache write a projection that merely LAGS rather than a lost transition — the
walk reaches the same head either way, one or two reads later.

THREE PROPERTIES AN EDITOR MUST NOT INVERT.

The walk starts at the LATEST CLOSED token when the cache names one, never at
the current token. The authority a transition commits lives in the closed
token's payload, so a walk that began at the open token would report every
long-running chain as sitting at epoch 0 with no required result — a confident,
plausible answer that no surface would contradict.

Every payload's own `prior_token_id` is checked against the token it was read
from, and a mismatch is a FORK that is reported rather than followed. Two
transitions admitted from one epoch is the exact condition the chain exists to
make impossible, so a reader that picked a branch would be reporting a repair
it had invented.

An unreadable step is a FINDING and never an absence. A chain that cannot be
walked and an epic that has no chain support opposite conclusions, and silently
collapsing the first into the second hands a live epic's authority back to its
legacy pointer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro.commands._plan_epoch_findings import (
    ChainFinding,
    chain_fork_finding,
    chain_unreadable_finding,
    missing_tracking_finding,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_payload import (
    AuthorityState,
    parse_payload,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_projection import (
    ChainCache,
    read_chain_cache,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_tokens import token_reading

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "ChainHead",
    "epic_chain_cache",
    "read_chain_head",
    "walk_chain_head",
]

# How many tokens one walk may read before reporting the chain unreadable. The
# cache is at most one transition behind in ordinary operation, and a crashed
# writer leaves it one further behind; a bound this far above that is a
# runaway-loop backstop, not a policy about how far a chain may lag.
_WALK_LIMIT = 64

_METADATA_FIELD = "metadata"


@dataclass(frozen=True, kw_only=True)
class ChainHead:
    """One epic's authority as the chain holds it right now.

    `current_token_id` is the open token a transition must close, and it is
    what a writer carries back into `commit_transition`: the epoch number alone
    could be re-derived by a second reader and would not say WHICH record this
    writer observed. `winning_operation_id` is the operation that committed the
    latest closed transition, which is what a refused writer is told.
    """

    current_token_id: str
    latest_closed_token_id: str | None
    epoch: int
    authority: AuthorityState = field(default_factory=AuthorityState)
    winning_operation_id: str | None = None


def read_chain_head(*, config: StoreConfig, epic_id: str) -> ChainHead | ChainFinding:
    """Read one epic's authority head, or report why it cannot be read."""
    client = make_beads_client(config=config)
    cache = epic_chain_cache(client=client, epic_id=epic_id)
    if cache is None:
        return missing_tracking_finding(epic_id=epic_id)
    return walk_chain_head(client=client, epic_id=epic_id, cache=cache)


def epic_chain_cache(*, client: BeadsClient, epic_id: str) -> ChainCache | None:
    """Read one epic's chain cache, or None when it names no chain."""
    record = client.show_issue(issue_id=epic_id)
    metadata = record.get(_METADATA_FIELD)
    if not isinstance(metadata, dict):
        return None
    return read_chain_cache(metadata=dict(cast("dict[str, Any]", metadata)))


def walk_chain_head(
    *,
    client: BeadsClient,
    epic_id: str,
    cache: ChainCache,
) -> ChainHead | ChainFinding:
    """Walk forward from the cache to the first open token."""
    token_id = cache.latest_closed if cache.latest_closed is not None else cache.current
    latest_closed: str | None = None
    epoch = 0
    authority = AuthorityState()
    winner: str | None = None
    for _ in range(_WALK_LIMIT):
        reading = token_reading(client=client, token_id=token_id)
        if not reading.present:
            return chain_unreadable_finding(
                epic_id=epic_id,
                token_id=token_id,
                detail="the token record could not be read",
            )
        if not reading.closed:
            return ChainHead(
                current_token_id=token_id,
                latest_closed_token_id=latest_closed,
                epoch=epoch,
                authority=authority,
                winning_operation_id=winner,
            )
        payload = None if reading.close_reason is None else parse_payload(text=reading.close_reason)
        if payload is None:
            return chain_unreadable_finding(
                epic_id=epic_id,
                token_id=token_id,
                detail="the closed token carries no readable transition payload",
            )
        if payload.prior_token_id != token_id:
            return chain_fork_finding(
                epic_id=epic_id,
                token_id=token_id,
                claimed_prior=payload.prior_token_id,
                walked_from=token_id,
            )
        latest_closed = token_id
        epoch = payload.new_epoch
        authority = payload.authority
        winner = payload.operation_id
        token_id = payload.next_token_id
    return chain_unreadable_finding(
        epic_id=epic_id,
        token_id=token_id,
        detail=f"the walk reached the {_WALK_LIMIT}-token bound without finding an open token",
    )
