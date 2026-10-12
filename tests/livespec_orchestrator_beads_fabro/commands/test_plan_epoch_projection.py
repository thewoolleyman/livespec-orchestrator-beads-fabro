"""The chain's two projections: the metadata cache and the progress-event comment."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, IssueDraft
from livespec_orchestrator_beads_fabro.commands._plan_epoch_payload import (
    AuthorityState,
    OperationReceipt,
    TransitionPayload,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_projection import (
    CHAIN_METADATA_KEY,
    CURRENT_FIELD,
    LATEST_CLOSED_FIELD,
    PLAN_PROGRESS_PREFIX,
    ChainCache,
    chain_cache_metadata,
    progress_event_body,
    read_chain_cache,
    read_progress_events,
    write_chain_cache,
    write_progress_event,
)

if TYPE_CHECKING:
    import pytest

_EPIC_ID = "bd-ib-relay1"


_PRIOR = "wisp-0"
_NEXT = "wisp-1"


def _payload() -> TransitionPayload:
    return TransitionPayload(
        operation_id="op-1",
        prior_epoch=0,
        new_epoch=1,
        prior_token_id=_PRIOR,
        next_token_id=_NEXT,
        authority=AuthorityState(
            required_result={"repo": "r", "file": "f.md"},
            original_deadline="2026-10-19T09:00:00Z",
            max_handoffs=4,
            consumed_handoffs=1,
            receipts=(OperationReceipt(operation_id="op-1", epoch=1, recorded_at="t"),),
        ),
    )


def _seeded_fake() -> FakeBeadsClient:
    fake = FakeBeadsClient()
    _ = fake.create_issue(
        draft=IssueDraft(
            issue_id=_EPIC_ID,
            issue_type="epic",
            title="plan",
            description="anchor",
            assignee=None,
            created_at="2026-10-12T08:00:00Z",
            metadata={"rank": "a0", "plan_slug": "relay-delivery-and-progress-deadline"},
        )
    )
    return fake


def test_the_cache_overlay_carries_both_sub_keys_and_preserves_the_rest() -> None:
    """`bd update --metadata` replaces a nested object WHOLESALE.

    So a write omitting one sub-key destroys the other, and a write that
    dropped the epic's unrelated keys would destroy those. Both directions are
    asserted here because the merge makes them different failures.
    """
    metadata = chain_cache_metadata(
        existing_metadata={"rank": "a0", "plan_slug": "relay"},
        latest_closed="wisp-0",
        current="wisp-1",
    )

    assert metadata["rank"] == "a0"
    assert metadata["plan_slug"] == "relay"
    assert metadata[CHAIN_METADATA_KEY] == {
        LATEST_CLOSED_FIELD: "wisp-0",
        CURRENT_FIELD: "wisp-1",
    }


def test_the_cache_reads_back_including_a_genesis_with_no_closed_token() -> None:
    metadata = chain_cache_metadata(existing_metadata={}, latest_closed=None, current="wisp-0")

    assert read_chain_cache(metadata=metadata) == ChainCache(latest_closed=None, current="wisp-0")


def test_every_unusable_cache_reads_as_naming_no_chain() -> None:
    """An ill-typed cache and an absent one are the same answer to a walk.

    Both mean there is no start point to trust, and inventing one would point
    the walk at a token id nobody wrote.
    """
    cases: list[dict[str, object]] = [
        {},
        {CHAIN_METADATA_KEY: "not an object"},
        {CHAIN_METADATA_KEY: {LATEST_CLOSED_FIELD: None}},
        {CHAIN_METADATA_KEY: {CURRENT_FIELD: ""}},
        {CHAIN_METADATA_KEY: {CURRENT_FIELD: 7}},
        {CHAIN_METADATA_KEY: {CURRENT_FIELD: "wisp-1", LATEST_CLOSED_FIELD: 7}},
    ]

    assert [read_chain_cache(metadata=case) for case in cases] == [None] * len(cases)


def test_writing_the_cache_leaves_the_epics_other_metadata_standing() -> None:
    fake = _seeded_fake()

    write_chain_cache(client=fake, epic_id=_EPIC_ID, latest_closed=None, current="wisp-0")

    metadata = fake.show_issue(issue_id=_EPIC_ID)["metadata"]
    assert isinstance(metadata, dict)
    assert metadata["plan_slug"] == "relay-delivery-and-progress-deadline"
    assert read_chain_cache(metadata=metadata) == ChainCache(latest_closed=None, current="wisp-0")


def test_writing_the_cache_onto_a_metadataless_record_still_works(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Beads records are `omitempty`-sparse: an unwritten epic omits the key.

    Indexing it would raise on exactly the epic that has never been written to,
    which is every epic the migration is about to reach.
    """
    fake = _seeded_fake()
    written: list[dict[str, Any]] = []

    def _sparse_show(*, issue_id: str) -> dict[str, Any]:
        return {"id": issue_id}

    def _record_update(*, issue_id: str, metadata: dict[str, Any] | None = None) -> None:
        _ = issue_id
        assert metadata is not None
        written.append(metadata)

    monkeypatch.setattr(fake, "show_issue", _sparse_show)
    monkeypatch.setattr(fake, "update_issue", _record_update)
    write_chain_cache(client=fake, epic_id=_EPIC_ID, latest_closed="wisp-0", current="wisp-1")

    assert read_chain_cache(metadata=written[0]) == ChainCache(
        latest_closed="wisp-0", current="wisp-1"
    )


def test_a_progress_event_carries_the_readable_lines_and_the_canonical_payload() -> None:
    """The canonical line is what a retry recovers the ORIGINAL event from.

    Prose cannot be parsed back into a transition, so a recovery reading only
    the readable lines would answer the retry with an event nobody committed.
    """
    body = progress_event_body(payload=_payload(), event_kind="handoff", now="t")

    assert "operation: op-1" in body
    assert "event: handoff" in body
    assert "epoch: 0 -> 1" in body
    assert "prior-token: wisp-0" in body
    assert "next-token: wisp-1" in body
    assert "original-deadline: 2026-10-19T09:00:00Z" in body
    assert "max-handoffs: 4" in body
    assert "consumed-handoffs: 1" in body
    assert "payload: {" in body
    # A ledger comment can never be edited or deleted, so it must not carry a
    # template opener: a restored token would rewrite a brief or kill a dispatch.
    assert "{" + "{" not in body
    assert "{%" not in body
    assert "{#" not in body


def test_a_written_progress_event_reads_back_with_its_payload() -> None:
    fake = _seeded_fake()

    write_progress_event(
        client=fake,
        epic_id=_EPIC_ID,
        payload=_payload(),
        event_kind="handoff",
        author="relay-session",
        now="2026-10-12T09:00:00Z",
    )

    events = read_progress_events(client=fake, epic_id=_EPIC_ID)
    assert len(events) == 1
    assert events[0].operation_id == "op-1"
    assert events[0].payload == _payload()
    comment = fake.list_comments(issue_id=_EPIC_ID)[0]["text"]
    assert isinstance(comment, str)
    assert comment.splitlines()[0] == PLAN_PROGRESS_PREFIX
    assert "author: relay-session" in comment


def test_the_event_read_ignores_every_comment_that_is_not_one() -> None:
    """A plan epic's timeline carries handoffs and scope events beside these."""
    fake = _seeded_fake()
    fake.seed_comment(issue_id=_EPIC_ID, text="plan-handoff-entry\nauthor: a\n\nbody")
    fake.seed_comment(issue_id=_EPIC_ID, text=f"{PLAN_PROGRESS_PREFIX}\n\nno operation line")
    write_progress_event(
        client=fake,
        epic_id=_EPIC_ID,
        payload=_payload(),
        event_kind="handoff",
        author="relay-session",
        now="t",
    )

    events = read_progress_events(client=fake, epic_id=_EPIC_ID)

    assert [event.operation_id for event in events] == ["op-1"]


def test_an_event_whose_payload_line_is_unreadable_is_reported_as_payloadless() -> None:
    """Absent and unparseable are kept apart: one is reportable, the other is not there."""
    fake = _seeded_fake()
    fake.seed_comment(
        issue_id=_EPIC_ID,
        text=f"{PLAN_PROGRESS_PREFIX}\n\noperation: op-torn\npayload: not-json",
    )
    fake.seed_comment(
        issue_id=_EPIC_ID,
        text=f"{PLAN_PROGRESS_PREFIX}\n\noperation: op-bare",
    )

    events = read_progress_events(client=fake, epic_id=_EPIC_ID)

    assert [(event.operation_id, event.payload) for event in events] == [
        ("op-torn", None),
        ("op-bare", None),
    ]


def test_a_comment_with_no_text_field_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    """`omitempty` sparseness reaches comment records too."""
    fake = _seeded_fake()

    def _textless(*, issue_id: str) -> list[dict[str, Any]]:
        _ = issue_id
        return [{"author": "a"}]

    monkeypatch.setattr(fake, "list_comments", _textless)

    assert read_progress_events(client=fake, epic_id=_EPIC_ID) == ()


def test_a_label_line_naming_nothing_is_passed_over_rather_than_read_as_empty() -> None:
    """A marker with nothing after its colon records no value.

    Counting it as an empty operation id would attribute a transition to an
    operation nobody named, which is worse than skipping the line.
    """
    fake = _seeded_fake()
    fake.seed_comment(
        issue_id=_EPIC_ID,
        text=f"{PLAN_PROGRESS_PREFIX}\n\noperation: \noperation: op-late",
    )

    events = read_progress_events(client=fake, epic_id=_EPIC_ID)

    assert [event.operation_id for event in events] == ["op-late"]
