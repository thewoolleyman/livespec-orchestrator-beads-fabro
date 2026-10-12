"""The two refusals a committing writer can reach with no winner to name.

Both are kept apart from the ordinary loss, where the winning operation IS
readable, because `winning_operation_id` is never a guess: naming the wrong
operation as the winner sends an operator to reconcile against a transition
that never happened.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_chain import (
    ChainHead,
    CommittedTransition,
    StaleEpochRefusal,
    TransitionRequest,
    commit_transition,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_findings import (
    RECEIPT_WITHOUT_EVENT,
    ChainFinding,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_payload import (
    AuthorityState,
    OperationReceipt,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_tokens import (
    attempt_close,
    create_token,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

_EPIC_ID = "bd-ib-relay1"


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _fresh_fake() -> FakeBeadsClient:
    reset_fake_singleton()
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=_EPIC_ID,
            issue_type="epic",
            title="plan",
            description="anchor",
            assignee=None,
            created_at="2026-10-12T08:00:00Z",
            metadata={"rank": "a0"},
        )
    )
    return client


def _request(*, token_id: str) -> TransitionRequest:
    return TransitionRequest(
        operation_id="op-mine",
        observed_head=ChainHead(
            current_token_id=token_id,
            latest_closed_token_id=None,
            epoch=0,
            authority=AuthorityState(),
            winning_operation_id=None,
        ),
        authority=AuthorityState(original_deadline="2026-10-19T09:00:00Z", max_handoffs=4),
        event_kind="handoff",
        author="relay-session",
        now="2026-10-12T09:00:00Z",
    )


def _refusal(*, observed: str) -> StaleEpochRefusal | CommittedTransition | ChainFinding:
    return commit_transition(
        config=_config(),
        epic_id=_EPIC_ID,
        request=_request(token_id=observed),
    )


def test_a_writer_whose_observed_token_has_been_deleted_is_refused_naming_no_winner() -> None:
    """The predecessor delete removes superseded tokens, so this is reachable.

    A writer that read a head and then slept past two transitions finds its
    token gone rather than closed. That says the chain moved on; it does NOT
    say which operation moved it, so no winner is named.
    """
    _ = _fresh_fake()
    deleted = "wisp-deleted"

    refusal = _refusal(observed=deleted)

    assert isinstance(refusal, StaleEpochRefusal)
    assert refusal.winning_operation_id is None
    assert refusal.attempted_operation_id == "op-mine"
    assert "no longer present" in refusal.detail


def test_a_token_closed_with_text_that_is_not_a_transition_names_no_winner() -> None:
    """A close reason nobody can parse is an unreadable winner, not an absent one."""
    fake = _fresh_fake()
    token = create_token(client=fake)
    attempt_close(client=fake, token_id=token, reason="closed by hand")

    refusal = _refusal(observed=token)

    assert isinstance(refusal, StaleEpochRefusal)
    assert refusal.winning_operation_id is None
    assert "carries no readable transition" in refusal.detail
    assert fake.no_history_issue_ids() == (token,)


def test_a_ring_receipt_with_no_progress_event_at_all_is_reported() -> None:
    """The ring is proof the transition happened, so a fresh commit is forbidden.

    This is the sibling of a DAMAGED event: there the comment exists and its
    payload line is unreadable, here no comment for the operation exists at
    all. Both mean the chain holds a transition whose record cannot be
    returned, and both must refuse to duplicate the handoff the ring accounts
    for rather than commit again.
    """
    fake = _fresh_fake()
    token = create_token(client=fake)
    request = _request(token_id=token)
    with_ring = TransitionRequest(
        operation_id=request.operation_id,
        observed_head=ChainHead(
            current_token_id=token,
            latest_closed_token_id=None,
            epoch=1,
            authority=AuthorityState(
                receipts=(
                    OperationReceipt(
                        operation_id=request.operation_id,
                        epoch=1,
                        recorded_at="2026-10-12T08:30:00Z",
                    ),
                ),
            ),
        ),
        authority=request.authority,
        event_kind=request.event_kind,
        author=request.author,
        now=request.now,
    )

    outcome = commit_transition(config=_config(), epic_id=_EPIC_ID, request=with_ring)

    assert isinstance(outcome, ChainFinding)
    assert outcome.code == RECEIPT_WITHOUT_EVENT
    assert fake.list_comments(issue_id=_EPIC_ID) == []
    # Nothing was created or closed: the refusal lands before any write.
    assert fake.no_history_issue_ids() == (token,)
