"""A close whose READ-BACK failed is an unknown outcome, not a loss.

`token_reading` collapses every unreadable `bd show` into
`present=False, close_reason=None`, so a writer whose close WON but whose
read-back failed sees the same `close_reason != rendered` comparison a genuine
loser sees. Treating that as a loss deletes the candidate token the writer's
OWN COMMITTED PAYLOAD names as `next_token_id`, which breaks the chain
permanently: every later walk reaches that id and reports the chain unreadable.

The two cases here are a pair, and the second is what gives the first meaning.
A guard that returned the unknown-outcome finding for EVERY unadmitted close
would satisfy the first case while retiring the ordinary loser's candidate
cleanup, so the readable loss is asserted beside it as a positive control.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands import _plan_epoch_findings
from livespec_orchestrator_beads_fabro.commands._plan_epoch_chain import (
    ChainHead,
    CommittedTransition,
    StaleEpochRefusal,
    TransitionRequest,
    commit_transition,
    read_chain_head,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_findings import ChainFinding
from livespec_orchestrator_beads_fabro.commands._plan_epoch_payload import AuthorityState
from livespec_orchestrator_beads_fabro.commands._plan_epoch_projection import (
    chain_cache_metadata,
    read_chain_cache,
    read_progress_events,
)
from livespec_orchestrator_beads_fabro.errors import BeadsCommandError
from livespec_orchestrator_beads_fabro.types import StoreConfig

if TYPE_CHECKING:
    import pytest

_EPIC_ID = "bd-ib-relay1"
_NOW = "2026-10-12T09:00:00Z"

# Spelled as a literal and bound to the exported name by one `getattr`
# assertion below, because this module's Red predates the constant it binds and
# a Red's test bytes are fixed across its Red-to-Green pair.
_CLOSE_OUTCOME_UNKNOWN = "plan-epoch-chain: close-outcome-unknown"


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


def _authority(*, result: str) -> AuthorityState:
    return AuthorityState(
        required_result={"repo": "livespec-orchestrator-beads-fabro", "file": result},
        original_deadline="2026-10-19T09:00:00Z",
        max_handoffs=4,
        consumed_handoffs=1,
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


def _commit_whose_read_back_fails(
    *,
    monkeypatch: pytest.MonkeyPatch,
    operation_id: str,
) -> object:
    """Commit one transition whose close lands and whose read-back then fails.

    The head is read BEFORE the failure is installed, deliberately. Inside the
    window a writer reads the observed token exactly twice — the stale check it
    performs before closing anything, then the read-back after the close — so
    letting the first through and failing the second is what leaves the close
    ITSELF admitted by the server exactly as it would be in an ordinary win.
    Covering the stale check instead refuses the writer before any close is
    attempted, which proves nothing about a read-back.
    """
    head = _head()
    fake = _fake()
    show = fake.show_issue
    reads = 0

    def _fail_the_read_back(*, issue_id: str) -> dict[str, Any]:
        nonlocal reads
        reads += 1
        if reads > 1:
            raise BeadsCommandError(
                command=f"bd show {issue_id} --json",
                exit_code=1,
                stderr="Error 2013: Lost connection to MySQL server during query",
            )
        return show(issue_id=issue_id)

    monkeypatch.setattr(fake, "show_issue", _fail_the_read_back)
    outcome = commit_transition(
        config=_config(),
        epic_id=_EPIC_ID,
        request=_request(operation_id=operation_id, head=head, result="unknown.md"),
    )
    monkeypatch.setattr(fake, "show_issue", show)
    return outcome


def test_a_close_whose_read_back_failed_keeps_its_candidate_and_reports_the_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The close LANDED; only the reading of it failed.

    So the transition is durable in the closed token and its candidate is the
    successor that token's own payload names. Deleting that candidate — which
    is what the `close_reason != rendered` comparison alone leads to, since an
    unreadable record reports no close reason at all — would leave the chain
    naming a token that no longer exists, and no later walk could repair it.

    Nothing is projected, because the writer never learned that it had won.
    That is an ordinary diagnosable partial write, and the chain still walks
    forward to the new epoch on its own.
    """
    genesis = _seed_chain()
    finding = _commit_whose_read_back_fails(
        monkeypatch=monkeypatch,
        operation_id="op-unknown",
    )

    assert isinstance(finding, ChainFinding)
    assert finding.code == _CLOSE_OUTCOME_UNKNOWN
    assert getattr(_plan_epoch_findings, "CLOSE_OUTCOME_UNKNOWN", None) == _CLOSE_OUTCOME_UNKNOWN
    # The candidate SURVIVES. It is still the only other live token, so the
    # closed genesis plus that candidate are the two records left standing.
    live = _fake().no_history_issue_ids()
    assert len(live) == 2
    assert genesis in live
    candidate = next(token for token in live if token != genesis)
    # The finding names all three things an operator needs to act: the token
    # that was closed, the operation that closed it, and the candidate left
    # standing on purpose.
    assert genesis in finding.detail
    assert "op-unknown" in finding.detail
    assert candidate in finding.detail
    assert finding.remedy != ""
    # The chain walks forward on its own, to the epoch this very operation
    # committed — which is only possible because the candidate was kept.
    settled = _head()
    assert settled.epoch == 1
    assert settled.winning_operation_id == "op-unknown"
    assert settled.current_token_id == candidate
    assert settled.latest_closed_token_id == genesis
    # NOTHING was projected: no progress event, and the cache still names the
    # chain as it stood before the close.
    assert read_progress_events(client=_fake(), epic_id=_EPIC_ID) == ()
    cache = read_chain_cache(metadata=_epic_metadata())
    assert cache is not None
    assert cache.latest_closed is None
    assert cache.current == genesis


def test_an_ordinary_readable_loss_still_discards_its_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The positive control for the case above.

    Here the loser's read-back SUCCEEDS and reports the winner's reason, so the
    outcome is known: this writer lost, its candidate is linked to nothing, and
    it takes that candidate with it. A guard that reported the unknown-outcome
    finding for every unadmitted close would satisfy the first case while
    leaking a token record on every lost race.
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
    # Two tokens live: the closed genesis and the WINNER's candidate. The
    # loser's own candidate is gone.
    live = _fake().no_history_issue_ids()
    assert len(live) == 2
    assert genesis in live
    settled = _head()
    assert settled.current_token_id in live
    assert settled.winning_operation_id == "op-winner"


def _epic_metadata() -> dict[str, Any]:
    metadata = _fake().show_issue(issue_id=_EPIC_ID)["metadata"]
    assert isinstance(metadata, dict)
    return metadata
