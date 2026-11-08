"""Exact-retry recovery for incident genesis, with no second root and no blind write.

A retry establishes the committed, confirmed-absent or still-unknown status of
its operation from retained records before any effect: a published root is
recovered through the chain reader and its retained fence; a close that won but
never published is completed; another operation's root, or changed bytes under
the same operation, are refused by name. A recovered root whose host takeover
never landed on the item is taken over through the claim-token protocol
itself, under the protocol's own transition wait, never by a blind write.
"""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-dzbwaq
from __future__ import annotations

import time
from collections.abc import Callable, MutableMapping
from dataclasses import asdict
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._incident_authority_types import AuthorityRefusal
from livespec_orchestrator_beads_fabro._incident_entry import (
    incident_claim_decided,
    prior_claim,
    takeover_metadata,
)
from livespec_orchestrator_beads_fabro._incident_genesis import (
    GenesisFence,
    GenesisReceipt,
    GenesisRequest,
    decode_genesis_fence,
    genesis_comment,
    request_digest,
)
from livespec_orchestrator_beads_fabro._store_claim_tokens import change_claim
from livespec_orchestrator_beads_fabro._store_statuses import beads_status_for
from livespec_orchestrator_beads_fabro.effects._incident_authority_reader import read_authority
from livespec_orchestrator_beads_fabro.effects._incident_genesis_fence import published_fence

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient

__all__: list[str] = [
    "TRANSITION_OBSERVATIONS",
    "Observations",
    "complete_won_close",
    "genesis_receipt",
    "recover_genesis",
]

OPERATION_CONFLICT = "incident-operation-conflict"
ROOT_EXISTS = "incident-genesis-root-exists"
TRANSITION_PENDING = "incident-genesis-claim-transition-pending"
FENCE_LOST = "incident-genesis-fence-lost"
_ACTIVE = "active"
# This process's first sightings of an unapplied claim transition, as
# `change_claim` keys them; a one-shot entry waits the protocol's wait itself.
TRANSITION_OBSERVATIONS: dict[tuple[str, str, str], float] = {}
Observations = MutableMapping[tuple[str, str, str], float]


def _refuse(*, code: str, detail: str) -> AuthorityRefusal:
    return AuthorityRefusal(code=code, detail=detail)


def _query(*, request: GenesisRequest) -> dict[str, object]:
    return {
        key: value
        for key, value in asdict(request.attempt).items()
        if key in {"attempt_id", "phase", "operation_id", "generation", "owner"}
    }


def genesis_receipt(
    *, client: BeadsClient, request: GenesisRequest, fence: GenesisFence, recovered: bool
) -> GenesisReceipt | AuthorityRefusal:
    """Read the chain back; a receipt is only ever built from a verified reading."""
    attempt = request.attempt
    reading = read_authority(
        client=client,
        repository=attempt.repository,
        item_id=attempt.item_id,
        query=_query(request=request),
        historical=recovered,
    )
    if isinstance(reading, AuthorityRefusal):
        return reading
    return GenesisReceipt(
        request_digest=fence.request_digest,
        root_token_id=fence.root_token_id,
        claim_token_id=fence.expected_claim,
        successor_claim_token_id=fence.successor,
        committed_token_id=reading.committed_token_id,
        current_token_id=reading.current_token_id,
        attempt=reading.attempt,
        recovered=recovered,
    )


def _taken_over(
    *,
    client: BeadsClient,
    request: GenesisRequest,
    fence: GenesisFence,
    clock: Callable[[], float],
    observations: Observations,
) -> AuthorityRefusal | None:
    """A recovered root is usable only once its host takeover is on the item.

    The item still naming the closed token means the winning write was lost:
    the takeover is then made through `change_claim`, which waits out the
    unapplied transition and takes over its successor exactly as any other
    claim writer would, conditioned on the prior claim row the fence retained.
    `None` means the takeover is on the item.
    """
    attempt = request.attempt
    prior = fence.prior_claim
    held = incident_claim_decided(
        operation_id=attempt.operation_id, generation=attempt.generation, owner=attempt.owner
    )
    if held(client.show_issue(issue_id=attempt.item_id)):
        return None
    result = change_claim(
        client=client,
        work_item_id=attempt.item_id,
        writer=request.principal,
        intent="incident-entry-takeover",
        claim_tokens=True,
        status=beads_status_for(status=_ACTIVE),
        assignee=attempt.owner,
        metadata=takeover_metadata(
            operation_id=attempt.operation_id,
            generation=attempt.generation,
            owner=attempt.owner,
            principal=request.principal,
            root_token_id=fence.root_token_id,
            prior=prior,
        ),
        clock=clock,
        transition_observations=observations,
        # The decision rests on the row the fence retained, when it retained one.
        still_as_decided=lambda record: prior is None or prior_claim(record=record) == prior,
    )
    if result.outcome == "applied":
        return None
    if result.outcome == "claim-transition-pending":
        return _refuse(code=TRANSITION_PENDING, detail=attempt.item_id)
    return _refuse(code=FENCE_LOST, detail=f"{attempt.item_id}: {result.outcome}")


def _recovered(
    *,
    client: BeadsClient,
    request: GenesisRequest,
    fence: GenesisFence,
    clock: Callable[[], float],
    observations: Observations,
) -> GenesisReceipt | AuthorityRefusal:
    """The verified receipt of a published root, once its takeover is on the item."""
    receipt = genesis_receipt(client=client, request=request, fence=fence, recovered=True)
    if isinstance(receipt, AuthorityRefusal):
        return receipt
    refusal = _taken_over(
        client=client, request=request, fence=fence, clock=clock, observations=observations
    )
    return receipt if refusal is None else refusal


def recover_genesis(
    *,
    client: BeadsClient,
    request: GenesisRequest,
    clock: Callable[[], float] = time.monotonic,
    observations: Observations | None = None,
) -> GenesisReceipt | AuthorityRefusal | None:
    """An exact retry recovers its receipt; None means no root is published yet."""
    attempt = request.attempt
    reading = read_authority(
        client=client,
        repository=attempt.repository,
        item_id=attempt.item_id,
        query=_query(request=request),
        historical=True,
    )
    if isinstance(reading, AuthorityRefusal):
        if reading.code == "incident-authority-missing":
            return None
        if reading.code == "incident-authority-identity-mismatch":
            return _refuse(code=ROOT_EXISTS, detail=attempt.item_id)
        return reading
    # A generation-1 match is committed on the root itself.
    fence = published_fence(client=client, item_id=attempt.item_id, root=reading.committed_token_id)
    if fence is None:
        return _refuse(code=ROOT_EXISTS, detail=attempt.item_id)
    if reading.attempt != attempt or fence.request_digest != request_digest(request=request):
        return _refuse(code=OPERATION_CONFLICT, detail=attempt.operation_id)
    return _recovered(
        client=client,
        request=request,
        fence=fence,
        clock=clock,
        observations=observations if observations is not None else TRANSITION_OBSERVATIONS,
    )


def complete_won_close(
    *,
    client: BeadsClient,
    request: GenesisRequest,
    reason: object,
    clock: Callable[[], float] = time.monotonic,
    observations: Observations | None = None,
) -> GenesisReceipt | AuthorityRefusal:
    """Our own earlier close stands unpublished: publish its root, then its takeover."""
    fence = decode_genesis_fence(reason=reason)
    attempt = request.attempt
    if fence is None or fence.operation_id != attempt.operation_id:
        return _refuse(code=TRANSITION_PENDING, detail=attempt.item_id)
    if fence.request_digest != request_digest(request=request):
        return _refuse(code=OPERATION_CONFLICT, detail=attempt.operation_id)
    # Reached only while no genesis record names this root (a published one is
    # recovered through the chain reader above), so the comment is never doubled.
    client.add_comment(
        issue_id=attempt.item_id,
        body=genesis_comment(
            repository=attempt.repository,
            item_id=attempt.item_id,
            root_token_id=fence.root_token_id,
            claim_token_id=fence.expected_claim,
        ),
    )
    return _recovered(
        client=client,
        request=request,
        fence=fence,
        clock=clock,
        observations=observations if observations is not None else TRANSITION_OBSERVATIONS,
    )
