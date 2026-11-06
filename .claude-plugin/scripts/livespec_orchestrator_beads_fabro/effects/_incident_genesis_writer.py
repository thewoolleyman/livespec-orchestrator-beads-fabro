"""First incident authority publication through the claim-token conditional close.

The exclusion is the item's CURRENT dispatch claim token: closing it is the one
server-enforced compare-and-swap every claim-changing writer serializes on once
`dispatcher.claim_tokens` is committed true. Genesis mints its root privately,
then closes that token with a transition reason naming the root, the successor
claim token, the request digest and the prior claim row. Only a read-back of
that reason decides the winner; the exit status never does. A loser writes
nothing to the item and discards its own candidates.

Winning that close IS the factory fence. The one item write made inside the
protocol's lease moves the item to `active` under the incident owner, replaces
the factory's dispatch stamp with the incident holder's, and retains the prior
status, assignee and whole stamp beside the unobserved cancellation: a queued
admission, a late run stamp, a terminal write or a stranded-claim recovery for
the old generation finds its decision no longer holds and answers
`claim-changed`. No factory run is reported cancelled; that result is retained
as unobserved.
"""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-dzbwaq
from __future__ import annotations

import json
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, cast

from livespec_orchestrator_beads_fabro._incident_authority_payload import (
    TOKEN_TITLE,
    TRANSITION_MARKER,
    attempt_record,
)
from livespec_orchestrator_beads_fabro._incident_authority_types import AuthorityRefusal
from livespec_orchestrator_beads_fabro._incident_entry import prior_claim, takeover_metadata
from livespec_orchestrator_beads_fabro._incident_genesis import (
    GenesisReceipt,
    GenesisRequest,
    capability_unavailable,
    claim_successor,
    genesis_comment,
    genesis_fence,
    genesis_fence_reason,
)
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    CLAIM_TOKEN_METADATA_KEY,
    create_claim_token,
)
from livespec_orchestrator_beads_fabro._store_statuses import beads_status_for
from livespec_orchestrator_beads_fabro.commands._plan_epoch_tokens import (
    attempt_close,
    token_reading,
)
from livespec_orchestrator_beads_fabro.effects._incident_genesis_recovery import (
    Observations,
    complete_won_close,
    genesis_receipt,
    recover_genesis,
)
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsCredentialMissingError,
    BeadsMappingError,
    BeadsTenantMissingError,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient, BeadsRecord

__all__: list[str] = ["publish_genesis"]

_LEASE_SECONDS = 120.0
_CLAIM_ABSENT = "incident-genesis-claim-token-missing"
_ACTIVE = "active"


def _refuse(*, code: str, detail: str) -> AuthorityRefusal:
    return AuthorityRefusal(code=code, detail=detail)


def _metadata_of(*, record: BeadsRecord) -> dict[str, Any]:
    raw = record.get("metadata")
    return dict(cast("dict[str, Any]", raw)) if isinstance(raw, dict) else {}


def _current_token(*, record: BeadsRecord) -> str | None:
    value = _metadata_of(record=record).get(CLAIM_TOKEN_METADATA_KEY)
    return value if isinstance(value, str) and value.strip() else None


def _expected_claim(*, request: GenesisRequest, item: BeadsRecord) -> str | AuthorityRefusal:
    """The exact current claim token the request named, or the named reason it is not."""
    item_id = request.attempt.item_id
    if item.get("id") != item_id:
        return _refuse(code="incident-authority-item-mismatch", detail=item_id)
    token = _current_token(record=item)
    if token is None:
        return _refuse(code=_CLAIM_ABSENT, detail=item_id)
    if token != request.expected_claim:
        return _refuse(code="incident-genesis-claim-mismatch", detail=item_id)
    return token


def _discard(
    *, client: BeadsClient, principal: str, root: str, current: str, successor: str
) -> None:
    client.delete_issue(issue_id=root)
    client.delete_issue(issue_id=current)
    attempt_close(
        client=client,
        token_id=successor,
        reason=json.dumps(
            {"kind": "claim-token-discard", "writer": principal},
            separators=(",", ":"),
            sort_keys=True,
        ),
    )


def _fence(
    *,
    client: BeadsClient,
    request: GenesisRequest,
    item: BeadsRecord,
    token: str,
    clock: Callable[[], float],
) -> GenesisReceipt | AuthorityRefusal:
    attempt = request.attempt
    prior = prior_claim(record=item)
    root = client.create_no_history_issue(
        title=TOKEN_TITLE,
        description="Retained immutable incident authority root. Not a work item.",
    )
    current = client.create_no_history_issue(
        title=TOKEN_TITLE, description="Open incident authority successor. Not a work item."
    )
    successor = create_claim_token(client=client)
    transition = {
        "schema": 1,
        "repository": attempt.repository,
        "item_id": attempt.item_id,
        "prior_token_id": root,
        "next_token_id": current,
        "attempt": attempt_record(attempt=attempt),
    }
    # The root is unpublished, so nobody can race this close; the fence below is the race.
    client.close_issue_without_verdict(
        issue_id=root,
        reason=TRANSITION_MARKER + json.dumps(transition, sort_keys=True, separators=(",", ":")),
    )
    started = clock()
    fence = genesis_fence(
        request=request, root_token_id=root, successor=successor, prior_claim=prior
    )
    reason = genesis_fence_reason(fence=fence, closed_at=datetime.now(timezone.utc).isoformat())
    attempt_close(client=client, token_id=token, reason=reason)
    verdict = token_reading(client=client, token_id=token)
    if verdict.close_reason is None:
        # Nothing observable decided the close: keep every candidate for an exact retry.
        return _refuse(code="incident-genesis-outcome-unknown", detail=token)
    if verdict.close_reason != reason:
        _discard(
            client=client,
            principal=request.principal,
            root=root,
            current=current,
            successor=successor,
        )
        return _refuse(code="incident-genesis-lost-race", detail=token)
    if clock() - started >= _LEASE_SECONDS:
        return _refuse(code="incident-genesis-lease-expired", detail=successor)
    client.add_comment(
        issue_id=attempt.item_id,
        body=genesis_comment(
            repository=attempt.repository,
            item_id=attempt.item_id,
            root_token_id=root,
            claim_token_id=token,
        ),
    )
    # The winner's one write: host ownership, the holder stamp, the retained
    # prior claim and the successor token land together or not at all.
    metadata = _metadata_of(record=item) | takeover_metadata(
        operation_id=attempt.operation_id,
        generation=attempt.generation,
        owner=attempt.owner,
        principal=request.principal,
        root_token_id=root,
        prior=prior,
    )
    metadata[CLAIM_TOKEN_METADATA_KEY] = successor
    client.update_issue(
        issue_id=attempt.item_id,
        status=beads_status_for(status=_ACTIVE),
        assignee=attempt.owner,
        metadata=metadata,
        names_claim_token=True,
    )
    return genesis_receipt(client=client, request=request, fence=fence, recovered=False)


def _publish(
    *,
    client: BeadsClient,
    request: GenesisRequest,
    clock: Callable[[], float],
    observations: Observations | None,
) -> GenesisReceipt | AuthorityRefusal:
    recovered = recover_genesis(
        client=client, request=request, clock=clock, observations=observations
    )
    if recovered is not None:
        return recovered
    item = client.show_issue(issue_id=request.attempt.item_id)
    token = _expected_claim(request=request, item=item)
    if isinstance(token, AuthorityRefusal):
        return token
    standing = token_reading(client=client, token_id=token)
    if not standing.present:
        return _refuse(code="incident-genesis-claim-unobservable", detail=token)
    if not standing.closed:
        return _fence(client=client, request=request, item=item, token=token, clock=clock)
    if claim_successor(reason=standing.close_reason) is None:
        # A closed token naming no successor is a discarded one: the item names no open token.
        return _refuse(code=_CLAIM_ABSENT, detail=request.attempt.item_id)
    return complete_won_close(
        client=client,
        request=request,
        reason=standing.close_reason,
        clock=clock,
        observations=observations,
    )


def publish_genesis(
    *,
    client: BeadsClient,
    request: GenesisRequest,
    claim_tokens: bool,
    clock: Callable[[], float] = time.monotonic,
    observations: Observations | None = None,
) -> GenesisReceipt | AuthorityRefusal:
    """Publish one first root and take host ownership, recover an exact retry, or refuse.

    `observations` is this writer's record of first sightings of an unapplied
    claim transition, as `change_claim` keeps it; `None` is the process's own.
    """
    if not claim_tokens:
        return capability_unavailable(request=request)
    try:
        return _publish(client=client, request=request, clock=clock, observations=observations)
    except (
        BeadsCommandError,
        BeadsConnectionError,
        BeadsCredentialMissingError,
        BeadsMappingError,
        BeadsTenantMissingError,
    ) as exc:
        # Candidates are kept: deleting them after a failed read-back could sever
        # a close that did win. An exact retry recovers or refuses by name.
        return _refuse(code="incident-genesis-unavailable", detail=str(exc))
