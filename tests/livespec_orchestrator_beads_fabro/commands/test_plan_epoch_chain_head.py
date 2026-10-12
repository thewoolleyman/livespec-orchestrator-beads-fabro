"""Walking a plan epic's token chain forward to the authority it actually holds."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_chain_head import (
    ChainHead,
    epic_chain_cache,
    read_chain_head,
    walk_chain_head,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_findings import (
    CHAIN_FORK,
    CHAIN_UNREADABLE,
    MISSING_TRACKING,
    ChainFinding,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_payload import (
    AuthorityState,
    TransitionPayload,
    render_payload,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_projection import (
    ChainCache,
    write_chain_cache,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_tokens import (
    attempt_close,
    create_token,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

if TYPE_CHECKING:
    import pytest

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


def _authority(*, consumed: int) -> AuthorityState:
    return AuthorityState(
        required_result={"repo": "r", "file": "f.md"},
        original_deadline="2026-10-19T09:00:00Z",
        max_handoffs=4,
        consumed_handoffs=consumed,
    )


def _close_with(
    *,
    fake: FakeBeadsClient,
    token_id: str,
    operation_id: str,
    prior_epoch: int,
    next_token_id: str,
    prior_token_id: str | None = None,
) -> None:
    attempt_close(
        client=fake,
        token_id=token_id,
        reason=render_payload(
            payload=TransitionPayload(
                operation_id=operation_id,
                prior_epoch=prior_epoch,
                new_epoch=prior_epoch + 1,
                prior_token_id=token_id if prior_token_id is None else prior_token_id,
                next_token_id=next_token_id,
                authority=_authority(consumed=prior_epoch + 1),
            )
        ),
    )


def test_an_epic_naming_no_chain_reports_the_missing_tracking_finding() -> None:
    _ = _fresh_fake()

    finding = read_chain_head(config=_config(), epic_id=_EPIC_ID)

    assert isinstance(finding, ChainFinding)
    assert finding.code == MISSING_TRACKING


def test_an_epic_with_no_metadata_at_all_names_no_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A never-written epic OMITS the key entirely, not an empty object.

    Beads records are `omitempty`-sparse, so indexing `metadata` would raise on
    exactly the epic the migration has not reached yet.
    """
    fake = _fresh_fake()

    def _sparse_show(*, issue_id: str) -> dict[str, Any]:
        return {"id": issue_id}

    monkeypatch.setattr(fake, "show_issue", _sparse_show)

    assert epic_chain_cache(client=fake, epic_id=_EPIC_ID) is None


def test_a_genesis_only_chain_reads_as_epoch_zero_with_no_authority() -> None:
    fake = _fresh_fake()
    genesis = create_token(client=fake)
    write_chain_cache(client=fake, epic_id=_EPIC_ID, latest_closed=None, current=genesis)

    head = read_chain_head(config=_config(), epic_id=_EPIC_ID)

    assert head == ChainHead(
        current_token_id=genesis,
        latest_closed_token_id=None,
        epoch=0,
        authority=AuthorityState(),
        winning_operation_id=None,
    )


def test_the_walk_starts_at_the_latest_closed_token_so_authority_is_never_lost() -> None:
    """Starting at the OPEN token would report every live chain at epoch 0.

    The authority a transition commits lives in the CLOSED token's payload, so
    a walk beginning at the current token reports a confident, plausible
    epoch-0 answer that no other surface contradicts.
    """
    fake = _fresh_fake()
    closed = create_token(client=fake)
    current = create_token(client=fake)
    _close_with(
        fake=fake,
        token_id=closed,
        operation_id="op-3",
        prior_epoch=2,
        next_token_id=current,
    )
    write_chain_cache(client=fake, epic_id=_EPIC_ID, latest_closed=closed, current=current)

    head = read_chain_head(config=_config(), epic_id=_EPIC_ID)

    assert isinstance(head, ChainHead)
    assert head.epoch == 3
    assert head.current_token_id == current
    assert head.latest_closed_token_id == closed
    assert head.winning_operation_id == "op-3"
    assert head.authority.consumed_handoffs == 3


def test_a_lagging_cache_is_walked_forward_rather_than_trusted() -> None:
    """A lost cache write makes the projection LAG, never the transition.

    The cache here still names the first closed token as current, two
    transitions behind; the walk follows each payload's own next-token link and
    arrives at the same head one read later.
    """
    fake = _fresh_fake()
    first = create_token(client=fake)
    second = create_token(client=fake)
    third = create_token(client=fake)
    _close_with(fake=fake, token_id=first, operation_id="op-1", prior_epoch=0, next_token_id=second)
    _close_with(fake=fake, token_id=second, operation_id="op-2", prior_epoch=1, next_token_id=third)
    write_chain_cache(client=fake, epic_id=_EPIC_ID, latest_closed=first, current=second)

    head = read_chain_head(config=_config(), epic_id=_EPIC_ID)

    assert isinstance(head, ChainHead)
    assert head.current_token_id == third
    assert head.latest_closed_token_id == second
    assert head.epoch == 2
    assert head.winning_operation_id == "op-2"


def test_a_cache_naming_a_vanished_token_reports_an_unreadable_chain() -> None:
    """An unreadable chain is never collapsed into an absent one.

    The two support opposite conclusions: an absent chain hands authority to
    the legacy pointer, while an unreadable one must stop a dispatch.
    """
    fake = _fresh_fake()
    write_chain_cache(client=fake, epic_id=_EPIC_ID, latest_closed=None, current="wisp-gone")

    finding = read_chain_head(config=_config(), epic_id=_EPIC_ID)

    assert isinstance(finding, ChainFinding)
    assert finding.code == CHAIN_UNREADABLE
    assert "wisp-gone" in finding.detail


def test_a_closed_token_carrying_no_readable_payload_is_unreadable() -> None:
    fake = _fresh_fake()
    token = create_token(client=fake)
    attempt_close(client=fake, token_id=token, reason="not a payload")

    finding = walk_chain_head(
        client=fake,
        epic_id=_EPIC_ID,
        cache=ChainCache(latest_closed=token, current=token),
    )

    assert isinstance(finding, ChainFinding)
    assert finding.code == CHAIN_UNREADABLE
    assert "no readable transition payload" in finding.detail


def test_a_payload_claiming_a_predecessor_it_was_not_reached_from_is_a_fork() -> None:
    """Two transitions from one epoch is the condition the chain makes impossible.

    So a payload whose own prior link does not name the token it closed is
    reported rather than followed: a reader that picked a branch would be
    announcing a repair it had invented.
    """
    fake = _fresh_fake()
    token = create_token(client=fake)
    successor = create_token(client=fake)
    elsewhere = "wisp-somewhere-else"
    _close_with(
        fake=fake,
        token_id=token,
        operation_id="op-1",
        prior_epoch=0,
        next_token_id=successor,
        prior_token_id=elsewhere,
    )

    finding = walk_chain_head(
        client=fake,
        epic_id=_EPIC_ID,
        cache=ChainCache(latest_closed=token, current=successor),
    )

    assert isinstance(finding, ChainFinding)
    assert finding.code == CHAIN_FORK
    assert elsewhere in finding.detail


def test_a_chain_that_never_reaches_an_open_token_is_reported_not_looped() -> None:
    """A self-linking closed token would otherwise walk forever."""
    fake = _fresh_fake()
    token = create_token(client=fake)
    _close_with(fake=fake, token_id=token, operation_id="op-1", prior_epoch=0, next_token_id=token)

    finding = walk_chain_head(
        client=fake,
        epic_id=_EPIC_ID,
        cache=ChainCache(latest_closed=token, current=token),
    )

    assert isinstance(finding, ChainFinding)
    assert finding.code == CHAIN_UNREADABLE
    assert "bound" in finding.detail
