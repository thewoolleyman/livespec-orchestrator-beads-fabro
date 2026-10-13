"""The chain states the three reconciliation verbs must each tell apart.

These are the states a stopped writer cannot produce on its own — a chain that
owes no event at all, a cache that is current while the event is gone, a chain
that cannot be walked, and a chain that changes underneath the repair. Each one
reaches a different arm, and each arm's wrong answer is a plausible one: a
genesis chain reported as a partial write, an unreadable chain reported as a
stale cache, or an event invented for a transition whose record vanished.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands import _plan_epoch_reconcile
from livespec_orchestrator_beads_fabro.commands._plan_epoch_chain import ChainHead
from livespec_orchestrator_beads_fabro.commands._plan_epoch_findings import (
    CHAIN_UNREADABLE,
    PARTIAL_WRITE,
    ChainFinding,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_payload import (
    AuthorityState,
    TransitionPayload,
    render_payload,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_projection import (
    chain_cache_metadata,
    read_progress_events,
    write_chain_cache,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_reconcile import (
    authorized_head,
    reconcile_projections,
    verify_projections,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_tokens import (
    TokenReading,
    attempt_close,
    create_token,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

if TYPE_CHECKING:
    import pytest

_EPIC_ID = "bd-ib-relay1"
_NOW = "2026-10-12T09:00:00Z"
_RECONCILED_AT = "2026-10-12T10:00:00Z"


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


def _seed_epic() -> FakeBeadsClient:
    reset_fake_singleton()
    fake = _fake()
    _ = fake.create_issue(
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
    return fake


def _seed_chain() -> str:
    fake = _seed_epic()
    genesis = create_token(client=fake)
    fake.update_issue(
        issue_id=_EPIC_ID,
        metadata=chain_cache_metadata(
            existing_metadata={"rank": "a0"},
            latest_closed=None,
            current=genesis,
        ),
    )
    return genesis


def _authority() -> AuthorityState:
    return AuthorityState(
        required_result={"repo": "r", "file": "f.md"},
        original_deadline="2026-10-19T09:00:00Z",
        max_handoffs=4,
        consumed_handoffs=1,
    )


def test_a_genesis_only_chain_owes_no_progress_event() -> None:
    """A chain that has committed nothing has no event to be missing.

    Reporting one would make every freshly created plan a partial write, and
    would withhold its first dispatch on a repair with nothing to repair.
    """
    _ = _seed_chain()

    assert verify_projections(config=_config(), epic_id=_EPIC_ID) is None
    assert reconcile_projections(config=_config(), epic_id=_EPIC_ID, now=_RECONCILED_AT) is None
    assert isinstance(authorized_head(config=_config(), epic_id=_EPIC_ID), ChainHead)
    assert _fake().list_comments(issue_id=_EPIC_ID) == []


def test_a_current_cache_with_a_missing_event_is_still_a_partial_write() -> None:
    """The cache arm cannot stand in for the event arm.

    A cache written while the event was lost agrees with the chain perfectly,
    so a combined check would call this epic healthy and dispatch against an
    obligation history that records nothing.
    """
    genesis = _seed_chain()
    fake = _fake()
    candidate = create_token(client=fake)
    attempt_close(
        client=fake,
        token_id=genesis,
        reason=render_payload(
            payload=TransitionPayload(
                operation_id="op-eventless",
                prior_epoch=0,
                new_epoch=1,
                prior_token_id=genesis,
                next_token_id=candidate,
                event_kind="handoff",
                authority=_authority(),
            )
        ),
    )
    write_chain_cache(client=fake, epic_id=_EPIC_ID, latest_closed=genesis, current=candidate)

    finding = verify_projections(config=_config(), epic_id=_EPIC_ID)

    assert isinstance(finding, ChainFinding)
    assert finding.code == PARTIAL_WRITE
    assert "op-eventless" in finding.detail
    assert "no progress event" in finding.detail
    reconciled = reconcile_projections(config=_config(), epic_id=_EPIC_ID, now=_RECONCILED_AT)
    assert isinstance(reconciled, ChainFinding)
    events = read_progress_events(client=_fake(), epic_id=_EPIC_ID)
    assert [event.operation_id for event in events] == ["op-eventless"]
    assert verify_projections(config=_config(), epic_id=_EPIC_ID) is None


def test_an_unreadable_chain_is_reported_as_unreadable_by_all_three_verbs() -> None:
    """A chain that cannot be walked has no authority to grade a cache against.

    So the walk is attempted FIRST: grading the projections before it would
    report a cache disagreement when what actually failed was the chain read,
    and the two have entirely different remedies.
    """
    _ = _seed_epic()
    write_chain_cache(client=_fake(), epic_id=_EPIC_ID, latest_closed=None, current="wisp-gone")

    reported = verify_projections(config=_config(), epic_id=_EPIC_ID)
    withheld = authorized_head(config=_config(), epic_id=_EPIC_ID)
    attempted = reconcile_projections(config=_config(), epic_id=_EPIC_ID, now=_RECONCILED_AT)

    for outcome in (reported, withheld, attempted):
        assert isinstance(outcome, ChainFinding)
        assert outcome.code == CHAIN_UNREADABLE
    assert _fake().list_comments(issue_id=_EPIC_ID) == []


def test_a_chain_that_changes_under_the_repair_writes_no_invented_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The payload parsed during the walk is unreadable by the time it is re-projected.

    That can only mean the chain moved underneath the repair, and the walk
    already proved the payload parsed. Re-projecting from anything else would
    publish an event for a transition whose record this reconciler can no
    longer read, so the partial write stays reported and nothing is written.
    """
    genesis = _seed_chain()
    fake = _fake()
    candidate = create_token(client=fake)
    attempt_close(
        client=fake,
        token_id=genesis,
        reason=render_payload(
            payload=TransitionPayload(
                operation_id="op-eventless",
                prior_epoch=0,
                new_epoch=1,
                prior_token_id=genesis,
                next_token_id=candidate,
                event_kind="handoff",
                authority=_authority(),
            )
        ),
    )
    write_chain_cache(client=fake, epic_id=_EPIC_ID, latest_closed=genesis, current=candidate)
    graded = verify_projections(config=_config(), epic_id=_EPIC_ID)
    assert isinstance(graded, ChainFinding)
    assert graded.code == PARTIAL_WRITE

    def _unreadable(*, client: object, token_id: str) -> TokenReading:
        _ = (client, token_id)
        return TokenReading(present=True, closed=True, close_reason="no longer a payload")

    monkeypatch.setattr(_plan_epoch_reconcile, "token_reading", _unreadable)
    reconciled = reconcile_projections(config=_config(), epic_id=_EPIC_ID, now=_RECONCILED_AT)

    assert isinstance(reconciled, ChainFinding)
    assert reconciled.code == PARTIAL_WRITE
    assert read_progress_events(client=_fake(), epic_id=_EPIC_ID) == ()
