"""The canonical transition payload round-trips, and every partial read fails closed."""

from __future__ import annotations

import json
from dataclasses import fields

from livespec_orchestrator_beads_fabro.commands._plan_epoch_payload import (
    RECEIPT_RING_SIZE,
    AuthorityState,
    OperationReceipt,
    TransitionPayload,
    parse_payload,
    render_payload,
    with_receipt,
)


def _payload(**overrides: object) -> TransitionPayload:
    base: dict[str, object] = {
        "operation_id": "op-1",
        "prior_epoch": 3,
        "new_epoch": 4,
        "prior_token_id": "wisp-3",
        "next_token_id": "wisp-4",
        "event_kind": "handoff",
        "authority": AuthorityState(
            required_result={"repo": "r", "file": "f.md"},
            original_deadline="2026-10-19T09:00:00Z",
            max_handoffs=4,
            consumed_handoffs=2,
            last_recovery_attempt={"attempt_id": "a-1"},
            receipts=(
                OperationReceipt(operation_id="op-0", epoch=3, recorded_at="2026-10-12T08:00:00Z"),
            ),
        ),
    }
    base.update(overrides)
    return TransitionPayload(**base)  # type: ignore[arg-type]


def test_a_rendered_payload_round_trips_through_the_parse() -> None:
    payload = _payload()

    assert parse_payload(text=render_payload(payload=payload)) == payload


def test_the_render_is_canonical_so_two_writers_produce_the_same_bytes() -> None:
    """Byte equality is the whole winner test, so the render must be stable.

    The winner compares the `close_reason` it read back against the text it
    sent. Sorted keys and no padding make that comparison a statement about
    WHICH transition stands rather than about how a dict happened to iterate.
    """
    rendered = render_payload(payload=_payload())

    assert rendered == render_payload(payload=_payload())
    assert " " not in rendered
    assert list(json.loads(rendered)) == sorted(json.loads(rendered))


def test_the_receipt_ring_keeps_the_newest_entries_and_drops_the_rest() -> None:
    state = AuthorityState()
    for index in range(RECEIPT_RING_SIZE + 3):
        state = with_receipt(
            state=state,
            receipt=OperationReceipt(
                operation_id=f"op-{index}",
                epoch=index,
                recorded_at="2026-10-12T09:00:00Z",
            ),
        )

    assert len(state.receipts) == RECEIPT_RING_SIZE
    assert state.receipts[-1].operation_id == f"op-{RECEIPT_RING_SIZE + 2}"
    assert state.receipts[0].operation_id == "op-3"


def test_with_receipt_carries_every_other_authority_field_forward() -> None:
    """A ring push is NOT a chance to recompute the obligation.

    The original deadline and the consumed count survive a receipt push
    untouched, because routine activity must not reset either limit.
    """
    before = _payload().authority
    after = with_receipt(
        state=before,
        receipt=OperationReceipt(operation_id="op-9", epoch=9, recorded_at="t"),
    )

    assert after.required_result == before.required_result
    assert after.original_deadline == before.original_deadline
    assert after.max_handoffs == before.max_handoffs
    assert after.consumed_handoffs == before.consumed_handoffs
    assert after.last_recovery_attempt == before.last_recovery_attempt


def test_an_absent_max_handoffs_and_deadline_still_parse() -> None:
    """A `human` or `none` pointer carries explicit nulls, not a missing budget."""
    payload = _payload(authority=AuthorityState())

    assert parse_payload(text=render_payload(payload=payload)) == payload


def test_every_unreadable_payload_parses_to_none() -> None:
    """Each case omits or mistypes ONE field, so no case passes for another's reason."""
    whole = json.loads(render_payload(payload=_payload()))
    cases: list[str] = [
        "not json at all",
        json.dumps([whole]),
        json.dumps({**whole, "operation_id": 7}),
        json.dumps({**whole, "prior_token_id": None}),
        json.dumps({**whole, "next_token_id": 4}),
        json.dumps({**whole, "prior_epoch": "3"}),
        json.dumps({**whole, "new_epoch": True}),
        json.dumps({**whole, "authority": "not an object"}),
        json.dumps({**whole, "authority": {**whole["authority"], "consumed_handoffs": "2"}}),
        json.dumps({**whole, "authority": {**whole["authority"], "original_deadline": 3}}),
        json.dumps({**whole, "authority": {**whole["authority"], "max_handoffs": "4"}}),
        json.dumps({**whole, "authority": {**whole["authority"], "receipts": {}}}),
        json.dumps({**whole, "authority": {**whole["authority"], "receipts": ["not an object"]}}),
        json.dumps({**whole, "authority": {**whole["authority"], "receipts": [{"epoch": 1}]}}),
        json.dumps(
            {
                **whole,
                "authority": {
                    **whole["authority"],
                    "receipts": [{"operation_id": "op-0", "epoch": "3", "recorded_at": "t"}],
                },
            }
        ),
        json.dumps(
            {
                **whole,
                "authority": {
                    **whole["authority"],
                    "receipts": [{"operation_id": "op-0", "epoch": 3, "recorded_at": 9}],
                },
            }
        ),
    ]

    assert [parse_payload(text=case) for case in cases] == [None] * len(cases)


def test_the_payload_carries_the_event_kind_so_a_reconciler_can_restore_it() -> None:
    """The event kind belongs to the CHAIN, not only to the comment it renders.

    `contracts.md` requires the progress comment to hold the event kind, and
    that comment is the projection that can be lost. If the kind lived only
    there, a reconciler rebuilding the event from the closed token's payload
    could not restore it, and would publish an event whose kind it had chosen.
    """
    field_names = {field.name for field in fields(TransitionPayload)}
    assert (
        "event_kind" in field_names
    ), "the transition payload must carry the event kind the progress comment renders"
    payload = _payload(event_kind="supervisor-handoff")

    recovered = parse_payload(text=render_payload(payload=payload))

    assert recovered == payload
    assert recovered is not None
    assert recovered.event_kind == "supervisor-handoff"


def test_a_payload_whose_event_kind_is_not_text_fails_closed() -> None:
    whole = json.loads(render_payload(payload=_payload()))

    assert parse_payload(text=json.dumps({**whole, "event_kind": 7})) is None
    assert (
        parse_payload(text=json.dumps({key: whole[key] for key in whole if key != "event_kind"}))
        is None
    )
