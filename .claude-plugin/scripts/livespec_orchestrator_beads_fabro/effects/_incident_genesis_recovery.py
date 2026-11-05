"""Exact-retry recovery for incident genesis, with no second root and no blind write.

A retry establishes the committed, confirmed-absent or still-unknown status of
its operation from retained records before any effect: a published root is
recovered through the chain reader and its retained fence; a close that won but
never published is completed; another operation's root, or changed bytes under
the same operation, are refused by name.
"""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-dzbwaq
from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._incident_authority_types import AuthorityRefusal
from livespec_orchestrator_beads_fabro._incident_genesis import (
    GenesisFence,
    GenesisReceipt,
    GenesisRequest,
    decode_genesis_fence,
    genesis_comment,
    request_digest,
)
from livespec_orchestrator_beads_fabro.effects._incident_authority_reader import read_authority
from livespec_orchestrator_beads_fabro.effects._incident_genesis_fence import published_fence

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient

__all__: list[str] = ["complete_won_close", "genesis_receipt", "recover_genesis"]

OPERATION_CONFLICT = "incident-operation-conflict"
ROOT_EXISTS = "incident-genesis-root-exists"
TRANSITION_PENDING = "incident-genesis-claim-transition-pending"


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


def recover_genesis(
    *, client: BeadsClient, request: GenesisRequest
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
    return genesis_receipt(client=client, request=request, fence=fence, recovered=True)


def complete_won_close(
    *, client: BeadsClient, request: GenesisRequest, reason: object
) -> GenesisReceipt | AuthorityRefusal:
    """Our own earlier close stands unpublished: publish its root, write nothing else."""
    fence = decode_genesis_fence(reason=reason)
    attempt = request.attempt
    if fence is None or fence.operation_id != attempt.operation_id:
        return _refuse(code=TRANSITION_PENDING, detail=attempt.item_id)
    if fence.request_digest != request_digest(request=request):
        return _refuse(code=OPERATION_CONFLICT, detail=attempt.operation_id)
    client.add_comment(
        issue_id=attempt.item_id,
        body=genesis_comment(
            repository=attempt.repository,
            item_id=attempt.item_id,
            root_token_id=fence.root_token_id,
            claim_token_id=fence.expected_claim,
        ),
    )
    return genesis_receipt(client=client, request=request, fence=fence, recovered=True)
