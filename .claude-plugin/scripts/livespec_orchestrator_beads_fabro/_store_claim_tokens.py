"""Server-mediated compare-and-swap protocol for dispatch claim writes."""

from __future__ import annotations

import time
from collections.abc import Callable, MutableMapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from livespec_orchestrator_beads_fabro._beads_client_metadata import CLAIM_TOKEN_METADATA_KEY
from livespec_orchestrator_beads_fabro._store_claim_token_chain import (
    discard_claim_token,
    is_discard_reason,
    successor_named_by,
    transition_reason,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_tokens import (
    attempt_close,
    token_reading,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient, BeadsRecord

__all__: list[str] = [
    "CLAIM_TOKEN_METADATA_KEY",
    "TRANSITION_WAIT_SECONDS",
    "ClaimChangeResult",
    "change_claim",
    "create_claim_token",
]

_CLAIM_TOKEN_LABEL = "claim-token"  # noqa: S105 - record label
_LEASE_SECONDS = 120.0
# Public because a one-shot writer waits this long itself before its one retry.
TRANSITION_WAIT_SECONDS = 180.0


@dataclass(frozen=True, kw_only=True)
class ClaimChangeResult:
    """The guarded write's observable protocol outcome."""

    outcome: str
    successor_token_id: str | None = None


@dataclass(frozen=True, kw_only=True)
class _Takeover:
    """The token a writer may now contest, the item read with it, and the hops followed.

    `followed` is empty when the token is the one the item names. Otherwise it
    lists, in order, every stranded successor the writer took over to reach it.
    """

    token_id: str
    record: BeadsRecord
    followed: tuple[str, ...]


def create_claim_token(*, client: BeadsClient) -> str:
    """Mint an open, server-assigned successor record labelled ``claim-token``."""
    token_id = client.create_no_history_issue(
        title="livespec dispatch claim token",
        description="Single-use dispatch-claim token; never a work item.",
    )
    client.update_issue(issue_id=token_id, add_labels=[_CLAIM_TOKEN_LABEL])
    return token_id


def change_claim(  # noqa: PLR0911, PLR0913
    *,
    client: BeadsClient,
    work_item_id: str,
    writer: str,
    intent: str,
    claim_tokens: bool,
    status: str | None = None,
    assignee: str | None = None,
    clear_assignee: bool = False,
    add_labels: list[str] | None = None,
    remove_labels: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    clock: Callable[[], float] = time.monotonic,
    transition_observations: MutableMapping[tuple[str, str, str], float] | None = None,
    still_as_decided: Callable[[BeadsRecord], bool] | None = None,
) -> ClaimChangeResult:
    """Write an item only after the caller owns its current claim token.

    `still_as_decided` binds the write to the caller's DECISION. The token is
    read here, later than the caller's own read of the item, so winning it
    excludes a writer racing on that one token and nothing more: a writer that
    decided on an earlier read and writes after another writer finished would
    win the successor that writer named. The predicate states what the decision
    rested on. It is asked of the item record read with the token, before a
    successor is created or the token closed, and a `False` answer writes
    nothing, closes nothing and reports `claim-changed`. A takeover asks it
    again of the record its write is finally based on. `None` asks nothing, and
    it is ignored while claim tokens are off.
    """
    update = _update_arguments(
        work_item_id=work_item_id,
        status=status,
        assignee=assignee,
        clear_assignee=clear_assignee,
        add_labels=add_labels,
        remove_labels=remove_labels,
        metadata=metadata,
    )
    if not claim_tokens:
        client.update_issue(**update)
        return ClaimChangeResult(outcome="applied")

    record = client.show_issue(issue_id=work_item_id)
    named = _current_token(record=record)
    if named is None:
        return ClaimChangeResult(outcome="claim-token-missing")
    takeover = _takeover_token(
        client=client,
        work_item_id=work_item_id,
        named=named,
        clock=clock,
        observations=transition_observations if transition_observations is not None else {},
    )
    if isinstance(takeover, ClaimChangeResult):
        return takeover
    record = takeover.record
    if still_as_decided is not None and not still_as_decided(record):
        return ClaimChangeResult(outcome="claim-changed")

    successor = create_claim_token(client=client)
    started = clock()
    close_reason = transition_reason(writer=writer, intent=intent, successor=successor)
    attempt_close(client=client, token_id=takeover.token_id, reason=close_reason)
    verdict = token_reading(client=client, token_id=takeover.token_id)
    if verdict.close_reason != close_reason:
        discard_claim_token(client=client, token_id=successor, writer=writer)
        return ClaimChangeResult(
            outcome="claim-unobservable" if verdict.close_reason is None else "claim-changed"
        )
    if clock() - started >= _LEASE_SECONDS:
        return ClaimChangeResult(outcome="claim-lease-expired", successor_token_id=successor)
    if takeover.followed:
        record = _stand_down_if_original_writer_landed(
            client=client,
            work_item_id=work_item_id,
            named=named,
            followed=takeover.followed,
            successor=successor,
            writer=writer,
            still_as_decided=still_as_decided,
        )
        if record is None:
            return ClaimChangeResult(outcome="claim-changed")

    update["metadata"] = _with_successor(record=record, metadata=metadata, successor=successor)
    client.update_issue(**update, names_claim_token=True)
    return ClaimChangeResult(outcome="applied", successor_token_id=successor)


def _takeover_token(
    *,
    client: BeadsClient,
    work_item_id: str,
    named: str,
    clock: Callable[[], float],
    observations: MutableMapping[tuple[str, str, str], float],
) -> _Takeover | ClaimChangeResult:
    """Follow the item's chain of unapplied transitions to its first open token.

    Each hop is a stranded transition of its own, observed for the takeover
    wait before the writer treats its successor as current (step 5 applies to
    the successor as it applied to the token the item names), so a chain of
    two closed tokens costs two waits and a writer that follows one hop only
    would contest a token it can never close. A chain that ends in a token
    the protocol discarded has no open token to win: the item has no current
    token, and the writer reports `claim-token-missing` as it would for an
    item naming none.
    """
    token_id = named
    followed: list[str] = []
    while True:
        reading = token_reading(client=client, token_id=token_id)
        record = client.show_issue(issue_id=work_item_id)
        if not reading.closed:
            return _Takeover(token_id=token_id, record=record, followed=tuple(followed))
        successor = successor_named_by(reason=reading.close_reason)
        if successor is None:
            discarded = is_discard_reason(reason=reading.close_reason)
            return ClaimChangeResult(
                outcome="claim-token-missing" if discarded else "claim-unobservable"
            )
        first_seen = observations.setdefault((work_item_id, token_id, successor), clock())
        if clock() - first_seen < TRANSITION_WAIT_SECONDS:
            return ClaimChangeResult(outcome="claim-transition-pending")
        if _current_token(record=record) != named:
            return ClaimChangeResult(outcome="claim-changed")
        reread = token_reading(client=client, token_id=token_id)
        if not reread.closed or successor_named_by(reason=reread.close_reason) != successor:
            return ClaimChangeResult(outcome="claim-changed")
        followed.append(successor)
        token_id = successor


def _stand_down_if_original_writer_landed(  # noqa: PLR0913
    *,
    client: BeadsClient,
    work_item_id: str,
    named: str,
    followed: tuple[str, ...],
    successor: str,
    writer: str,
    still_as_decided: Callable[[BeadsRecord], bool] | None,
) -> BeadsRecord | None:
    """Avoid overwriting the delayed item write that made a transition current.

    The record returned is the one the takeover's write is based on, so the
    caller's decision is asked of it too. When the item now names a token the
    takeover followed, the original winner's write has landed; when the item is
    no longer as the caller decided, the caller's change has no place. In both
    the takeover names its own successor in a write that changes nothing else,
    because it won the token the item's chain now ends in and only it can keep
    that chain ending in an open token: discarding the successor would leave a
    chain that ends closed, which no later writer could ever win. An item that
    names a token outside the chain was written by something this protocol does
    not fence; the takeover's successor is then unreachable and is discarded.
    """
    record = client.show_issue(issue_id=work_item_id)
    current = _current_token(record=record)
    if current == named and (still_as_decided is None or still_as_decided(record)):
        return record
    if current == named or current in followed:
        client.update_issue(
            issue_id=work_item_id,
            metadata=_with_successor(record=record, metadata=None, successor=successor),
            names_claim_token=True,
        )
    else:
        discard_claim_token(client=client, token_id=successor, writer=writer)
    return None


def _update_arguments(  # noqa: PLR0913
    *,
    work_item_id: str,
    status: str | None,
    assignee: str | None,
    clear_assignee: bool,
    add_labels: list[str] | None,
    remove_labels: list[str] | None,
    metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "issue_id": work_item_id,
        "status": status,
        "assignee": assignee,
        "clear_assignee": clear_assignee,
        "add_labels": add_labels,
        "remove_labels": remove_labels,
        "metadata": metadata,
    }


def _with_successor(
    *, record: BeadsRecord, metadata: dict[str, Any] | None, successor: str
) -> dict[str, Any]:
    merged = _metadata_of(record=record)
    if metadata is not None:
        merged.update(metadata)
    merged[CLAIM_TOKEN_METADATA_KEY] = successor
    return merged


def _current_token(*, record: BeadsRecord) -> str | None:
    return _text(value=_metadata_of(record=record).get(CLAIM_TOKEN_METADATA_KEY))


def _metadata_of(*, record: BeadsRecord) -> dict[str, Any]:
    raw = record.get("metadata")
    return dict(cast("dict[str, Any]", raw)) if isinstance(raw, dict) else {}


def _text(*, value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() != "" else None
