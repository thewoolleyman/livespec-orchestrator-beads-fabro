"""The canonical payload one plan-authority epoch transition commits.

PURE. A plan epic's authority is a chain of single-use token records, and a
transition is the close of the CURRENT open token through the public
`bd close <token> --reason <payload>`. This module is that payload: the
operation identity, the epoch it moved from and to, the link back to the token
it closed, the link forward to the writer's candidate next token, and the FULL
resulting authority state.

TWO PROPERTIES AN EDITOR MUST NOT INVERT.

The state is FULL and never a DELTA. The close statement that commits a
transition is the same statement that excludes every other writer, so whatever
the payload omits has no second write to arrive in; and the predecessor of the
latest closed token is DELETED after each transition, so the records a
delta-replay would need are gone. Measured over 60 transitions on one
disposable chain (relay research note 006): payload bytes went 300 to 474 and
then stayed flat once the receipt ring filled, with write time, read time and
live record count all constant in the number of transitions.

The receipt ring is BOUNDED, which is what makes "full state" and "constant
size" compatible. It carries the most recent `RECEIPT_RING_SIZE` operation
receipts so a retried operation can be recognised as already committed. A
retry older than the ring is necessarily against a long-superseded epoch and
is refused as stale instead.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, cast

from livespec_orchestrator_beads_fabro.effects import JsonParseFailure, parse_json

__all__: list[str] = [
    "RECEIPT_RING_SIZE",
    "AuthorityState",
    "OperationReceipt",
    "TransitionPayload",
    "carrying_receipts",
    "parse_payload",
    "render_payload",
    "with_receipt",
]

# The most recent operation receipts one payload carries. Eight is the width
# relay research note 006 measured the flat payload size against.
RECEIPT_RING_SIZE = 8

_OPERATION_ID = "operation_id"
_PRIOR_EPOCH = "prior_epoch"
_NEW_EPOCH = "new_epoch"
_PRIOR_TOKEN_ID = "prior_token_id"  # noqa: S105 - a payload field NAME, not a secret
_NEXT_TOKEN_ID = "next_token_id"  # noqa: S105 - a payload field NAME, not a secret
_EVENT_KIND = "event_kind"
_AUTHORITY = "authority"
_RECEIPTS = "receipts"
_EPOCH = "epoch"
_RECORDED_AT = "recorded_at"
_REQUIRED_RESULT = "required_result"
_ORIGINAL_DEADLINE = "original_deadline"
_MAX_HANDOFFS = "max_handoffs"
_CONSUMED_HANDOFFS = "consumed_handoffs"
_LAST_RECOVERY_ATTEMPT = "last_recovery_attempt"


@dataclass(frozen=True, kw_only=True)
class OperationReceipt:
    """One committed operation's receipt, as the bounded ring carries it."""

    operation_id: str
    epoch: int
    recorded_at: str


@dataclass(frozen=True, kw_only=True)
class AuthorityState:
    """The whole authority a plan epic's chain holds after one transition.

    `original_deadline` is the FIRST deadline the obligation was given, carried
    forward unchanged by every later transition; nothing here recomputes it.
    `consumed_handoffs` counts accepted handoffs against `max_handoffs`.
    `last_recovery_attempt` carries the typed causal-recovery attempt, whose
    own bounded deadline never replaces the original one.
    """

    required_result: object = None
    original_deadline: str | None = None
    max_handoffs: int | None = None
    consumed_handoffs: int = 0
    last_recovery_attempt: object = None
    receipts: tuple[OperationReceipt, ...] = ()


@dataclass(frozen=True, kw_only=True)
class TransitionPayload:
    """One transition, as the closed token's `close_reason` carries it.

    `event_kind` is here rather than only in the progress comment it renders.
    The comment is a PROJECTION and can be lost; this payload is the lossless
    record, so a reconciler rebuilding the comment from the chain restores the
    kind that was committed instead of choosing one.
    """

    operation_id: str
    prior_epoch: int
    new_epoch: int
    prior_token_id: str
    next_token_id: str
    event_kind: str
    authority: AuthorityState


def with_receipt(*, state: AuthorityState, receipt: OperationReceipt) -> AuthorityState:
    """Append one receipt to the ring, dropping the oldest beyond the bound."""
    return AuthorityState(
        required_result=state.required_result,
        original_deadline=state.original_deadline,
        max_handoffs=state.max_handoffs,
        consumed_handoffs=state.consumed_handoffs,
        last_recovery_attempt=state.last_recovery_attempt,
        receipts=(*state.receipts, receipt)[-RECEIPT_RING_SIZE:],
    )


def carrying_receipts(
    *,
    state: AuthorityState,
    receipts: tuple[OperationReceipt, ...],
) -> AuthorityState:
    """Return a writer's authority fields over the CHAIN's receipt ring.

    The ring is chain history and no writer supplies it. A transition that
    committed the caller's own `receipts` would erase the receipts that make
    another operation's retry recognisable — measured on this module's first
    build, where a chain of 24 transitions held ONE receipt because each
    writer arrived with an empty ring.
    """
    return AuthorityState(
        required_result=state.required_result,
        original_deadline=state.original_deadline,
        max_handoffs=state.max_handoffs,
        consumed_handoffs=state.consumed_handoffs,
        last_recovery_attempt=state.last_recovery_attempt,
        receipts=receipts,
    )


def render_payload(*, payload: TransitionPayload) -> str:
    """Render one payload as CANONICAL JSON (sorted keys, no padding).

    Canonical because the winner is established by comparing the `close_reason`
    read back against the text this writer sent: two renders of one payload
    have to be byte-identical, or a writer would read its own win as a loss.
    """
    return json.dumps(_payload_object(payload=payload), sort_keys=True, separators=(",", ":"))


def parse_payload(*, text: str) -> TransitionPayload | None:
    """Read one payload, or None when the text is not one.

    FAIL CLOSED on every partial read. A half-parsed payload reads as a
    transition whose links and epochs are whatever happened to parse, and a
    reader walking the chain on those values follows a link nobody wrote.
    """
    parsed = parse_json(text=text)
    if isinstance(parsed, JsonParseFailure) or not isinstance(parsed, dict):
        return None
    fields = cast("dict[str, Any]", parsed)
    operation_id = fields.get(_OPERATION_ID)
    prior_token_id = fields.get(_PRIOR_TOKEN_ID)
    next_token_id = fields.get(_NEXT_TOKEN_ID)
    event_kind = fields.get(_EVENT_KIND)
    epochs = _parse_epochs(fields=fields)
    authority = _parse_authority(value=fields.get(_AUTHORITY))
    if (
        not isinstance(operation_id, str)
        or not isinstance(prior_token_id, str)
        or not isinstance(next_token_id, str)
        or not isinstance(event_kind, str)
        or epochs is None
        or authority is None
    ):
        return None
    prior_epoch, new_epoch = epochs
    return TransitionPayload(
        operation_id=operation_id,
        prior_epoch=prior_epoch,
        new_epoch=new_epoch,
        prior_token_id=prior_token_id,
        next_token_id=next_token_id,
        event_kind=event_kind,
        authority=authority,
    )


def _payload_object(*, payload: TransitionPayload) -> dict[str, Any]:
    state = payload.authority
    return {
        _OPERATION_ID: payload.operation_id,
        _PRIOR_EPOCH: payload.prior_epoch,
        _NEW_EPOCH: payload.new_epoch,
        _PRIOR_TOKEN_ID: payload.prior_token_id,
        _NEXT_TOKEN_ID: payload.next_token_id,
        _EVENT_KIND: payload.event_kind,
        _AUTHORITY: {
            _REQUIRED_RESULT: state.required_result,
            _ORIGINAL_DEADLINE: state.original_deadline,
            _MAX_HANDOFFS: state.max_handoffs,
            _CONSUMED_HANDOFFS: state.consumed_handoffs,
            _LAST_RECOVERY_ATTEMPT: state.last_recovery_attempt,
            _RECEIPTS: [
                {
                    _OPERATION_ID: receipt.operation_id,
                    _EPOCH: receipt.epoch,
                    _RECORDED_AT: receipt.recorded_at,
                }
                for receipt in state.receipts
            ],
        },
    }


def _parse_epochs(*, fields: dict[str, Any]) -> tuple[int, int] | None:
    prior_epoch = fields.get(_PRIOR_EPOCH)
    new_epoch = fields.get(_NEW_EPOCH)
    if not _is_epoch(value=prior_epoch) or not _is_epoch(value=new_epoch):
        return None
    return (cast("int", prior_epoch), cast("int", new_epoch))


def _is_epoch(*, value: object) -> bool:
    """An epoch is a plain int; `bool` is rejected because it subclasses `int`."""
    return isinstance(value, int) and not isinstance(value, bool)


def _parse_authority(*, value: object) -> AuthorityState | None:
    if not isinstance(value, dict):
        return None
    fields = cast("dict[str, Any]", value)
    consumed = fields.get(_CONSUMED_HANDOFFS)
    deadline = fields.get(_ORIGINAL_DEADLINE)
    maximum = fields.get(_MAX_HANDOFFS)
    receipts = _parse_receipts(value=fields.get(_RECEIPTS))
    if (
        not _is_epoch(value=consumed)
        or not isinstance(deadline, str | None)
        or not (maximum is None or _is_epoch(value=maximum))
        or receipts is None
    ):
        return None
    return AuthorityState(
        required_result=fields.get(_REQUIRED_RESULT),
        original_deadline=deadline,
        max_handoffs=cast("int | None", maximum),
        consumed_handoffs=cast("int", consumed),
        last_recovery_attempt=fields.get(_LAST_RECOVERY_ATTEMPT),
        receipts=receipts,
    )


def _parse_receipts(*, value: object) -> tuple[OperationReceipt, ...] | None:
    if not isinstance(value, list):
        return None
    receipts: list[OperationReceipt] = []
    for entry in cast("list[Any]", value):
        receipt = _parse_receipt(value=entry)
        if receipt is None:
            return None
        receipts.append(receipt)
    return tuple(receipts)


def _parse_receipt(*, value: object) -> OperationReceipt | None:
    if not isinstance(value, dict):
        return None
    fields = cast("dict[str, Any]", value)
    operation_id = fields.get(_OPERATION_ID)
    epoch = fields.get(_EPOCH)
    recorded_at = fields.get(_RECORDED_AT)
    if (
        not isinstance(operation_id, str)
        or not _is_epoch(value=epoch)
        or not isinstance(recorded_at, str)
    ):
        return None
    return OperationReceipt(
        operation_id=operation_id,
        epoch=cast("int", epoch),
        recorded_at=recorded_at,
    )
