"""Concurrent plan-authority transitions serialize on the server's own close.

The exclusion under test is NOT in this plugin: it is `bd close`'s
`UPDATE … SET status='closed', close_reason=? WHERE id=? AND status!='closed'`,
measured over 20 trials of 4 concurrent closers in relay research note 005,
where exactly one reason won every time and the exit code identified the winner
in neither direction. `FakeBeadsClient` models that statement, so these tests
exercise the real decision rather than a convenient one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

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
    read_chain_head,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_payload import AuthorityState
from livespec_orchestrator_beads_fabro.commands._plan_epoch_projection import (
    chain_cache_metadata,
    read_progress_events,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

if TYPE_CHECKING:
    import pytest

_EPIC_ID = "bd-ib-relay1"
_NOW = "2026-10-12T09:00:00Z"


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _fake() -> FakeBeadsClient:
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    return client


def _seed_chain() -> str:
    """Seed one epic whose chain holds nothing but its genesis token."""
    reset_fake_singleton()
    fake = _fake()
    _ = fake.create_issue(
        draft=IssueDraft(
            issue_id=_EPIC_ID,
            issue_type="epic",
            title="plan",
            description="Plan anchor for plan/relay-delivery-and-progress-deadline.",
            assignee=None,
            created_at="2026-10-12T08:00:00Z",
            metadata={"rank": "a0", "plan_slug": "relay-delivery-and-progress-deadline"},
        )
    )
    genesis = fake.create_no_history_issue(title="token", description="single-use")
    fake.update_issue(
        issue_id=_EPIC_ID,
        metadata=chain_cache_metadata(
            existing_metadata=_epic_metadata(),
            latest_closed=None,
            current=genesis,
        ),
    )
    return genesis


def _authority(*, result: str, consumed: int = 1) -> AuthorityState:
    return AuthorityState(
        required_result={"repo": "livespec-orchestrator-beads-fabro", "file": result},
        original_deadline="2026-10-19T09:00:00Z",
        max_handoffs=4,
        consumed_handoffs=consumed,
        last_recovery_attempt=None,
    )


def _request(*, operation_id: str, head: ChainHead, result: str) -> TransitionRequest:
    return TransitionRequest(
        operation_id=operation_id,
        observed_head=head,
        authority=_authority(result=result),
        event_kind="handoff",
        author="relay-session",
        now=_NOW,
    )


def _head() -> ChainHead:
    head = read_chain_head(config=_config(), epic_id=_EPIC_ID)
    assert isinstance(head, ChainHead)
    return head


def test_one_of_two_writers_racing_from_one_epoch_commits_and_the_other_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both writers read the same open token; the server admits exactly one.

    The interleaving is exact rather than approximate. The loser is released
    first and the winner's whole transition is injected at the one instant that
    reproduces a genuine race: AFTER the loser has read the token and found it
    open, and BEFORE the loser's own close reaches the server. So the loser
    passes its own stale check and still loses, which is the only arm that
    exercises the server's conditional close rather than this plugin's
    pre-check.
    """
    genesis = _seed_chain()
    shared_head = _head()
    fake = _fake()
    create = fake.create_no_history_issue
    winner: list[object] = []

    def _create_and_let_the_winner_through(*, title: str, description: str) -> str:
        monkeypatch.setattr(fake, "create_no_history_issue", create)
        winner.append(
            commit_transition(
                config=_config(),
                epic_id=_EPIC_ID,
                request=_request(operation_id="op-winner", head=shared_head, result="won.md"),
            )
        )
        return create(title=title, description=description)

    monkeypatch.setattr(fake, "create_no_history_issue", _create_and_let_the_winner_through)
    loser = commit_transition(
        config=_config(),
        epic_id=_EPIC_ID,
        request=_request(operation_id="op-loser", head=shared_head, result="lost.md"),
    )

    assert isinstance(winner[0], CommittedTransition)
    assert isinstance(loser, StaleEpochRefusal)
    assert loser.winning_operation_id == "op-winner"
    assert loser.attempted_operation_id == "op-loser"
    # The refusal names the winner it READ, which is the only honest source:
    # the close's exit code identifies the winner in neither direction.
    assert "op-winner" in loser.detail
    # No authority changed on the loser's behalf, and no second transition of
    # the genesis token exists: one closed token, carrying one reason.
    closed = fake.show_issue(issue_id=genesis)
    assert closed["status"] == "closed"
    reason = closed["close_reason"]
    assert isinstance(reason, str)
    assert "op-winner" in reason
    assert "op-loser" not in reason
    settled = _head()
    assert settled.epoch == 1
    assert settled.authority.required_result == _authority(result="won.md").required_result
    # The loser deleted the candidate token it never linked, so only the
    # closed token and the winner's open token stay live.
    assert len(fake.no_history_issue_ids()) == 2
    # Exactly one progress event was projected: the winner's.
    events = read_progress_events(client=fake, epic_id=_EPIC_ID)
    assert [event.operation_id for event in events] == ["op-winner"]


def test_a_stale_writer_is_refused_before_it_creates_or_closes_anything() -> None:
    """The ordinary stale writer never reaches the server's close at all.

    Its observed token is ALREADY closed when it reads it, so the refusal is
    established from that record's own close reason — before a candidate token
    is created and before any close is attempted.
    """
    genesis = _seed_chain()
    stale_head = _head()
    committed = commit_transition(
        config=_config(),
        epic_id=_EPIC_ID,
        request=_request(operation_id="op-first", head=stale_head, result="first.md"),
    )
    assert isinstance(committed, CommittedTransition)
    live_before = _fake().no_history_issue_ids()

    refusal = commit_transition(
        config=_config(),
        epic_id=_EPIC_ID,
        request=_request(operation_id="op-stale", head=stale_head, result="stale.md"),
    )

    assert isinstance(refusal, StaleEpochRefusal)
    assert refusal.winning_operation_id == "op-first"
    assert refusal.observed_epoch == 0
    assert _fake().no_history_issue_ids() == live_before
    assert _head().epoch == 1
    assert _fake().show_issue(issue_id=genesis)["status"] == "closed"


def test_a_committed_transition_links_its_predecessor_and_its_successor() -> None:
    """The payload carries BOTH links, which is what makes the chain walkable.

    `prior_token_id` is what a reader checks every payload against, so two
    closed tokens claiming one predecessor are reportable as a fork rather
    than silently followed. `next_token_id` is committed in the SAME statement
    as the transition, so the identity of the next token is never a second
    write that can be lost.
    """
    genesis = _seed_chain()
    committed = commit_transition(
        config=_config(),
        epic_id=_EPIC_ID,
        request=_request(operation_id="op-one", head=_head(), result="one.md"),
    )

    assert isinstance(committed, CommittedTransition)
    assert committed.payload.prior_token_id == genesis
    assert committed.payload.prior_epoch == 0
    assert committed.payload.new_epoch == 1
    settled = _head()
    assert settled.current_token_id == committed.payload.next_token_id
    assert settled.latest_closed_token_id == genesis
    assert settled.winning_operation_id == "op-one"
    assert _epic_metadata()["plan_slug"] == "relay-delivery-and-progress-deadline"


def _epic_metadata() -> dict[str, Any]:
    metadata = _fake().show_issue(issue_id=_EPIC_ID)["metadata"]
    assert isinstance(metadata, dict)
    return metadata
