"""A retried operation recovers its original event instead of transitioning again.

`contracts.md` section "Required result, budget and progress epoch": "retried
calls with the same operation identity MUST recover the original event rather
than duplicate handoffs or extend a deadline." The hazard is specific. A retry
is indistinguishable from a fresh call at the surface — same caller, same
operation id, same intent — so the chain has to recognise it, and the two
places it can be recognised from carry different evidence: the bounded receipt
ring in the authority the writer already holds, and the epic's progress events,
which are the only record of the transition ITSELF.

The two source literals are spelled out here rather than imported, because this
module's Red predates the constants it binds and a Red's test bytes are fixed
across its Red-to-Green pair. `test_the_module_names_both_recovery_sources`
is what ties the literals back to the names the module exports.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands import _plan_epoch_chain
from livespec_orchestrator_beads_fabro.commands._plan_epoch_chain import (
    COMMITTED,
    ChainHead,
    CommittedTransition,
    TransitionRequest,
    commit_transition,
    read_chain_head,
    recover_committed_operation,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_findings import (
    RECEIPT_WITHOUT_EVENT,
    ChainFinding,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_payload import (
    RECEIPT_RING_SIZE,
    AuthorityState,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_projection import (
    PLAN_PROGRESS_PREFIX,
    chain_cache_metadata,
    read_progress_events,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_tokens import create_token
from livespec_orchestrator_beads_fabro.types import StoreConfig

if TYPE_CHECKING:
    import pytest

_EPIC_ID = "bd-ib-relay1"
_DEADLINE = "2026-10-19T09:00:00Z"
_NOW = "2026-10-12T09:00:00Z"
_RECOVERED_FROM_RING = "recovered-from-receipt-ring"
_RECOVERED_FROM_EVENT = "recovered-from-progress-event"


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


def _seed_chain() -> None:
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
    genesis = create_token(client=fake)
    fake.update_issue(
        issue_id=_EPIC_ID,
        metadata=chain_cache_metadata(
            existing_metadata={"rank": "a0"},
            latest_closed=None,
            current=genesis,
        ),
    )


def _head() -> ChainHead:
    head = read_chain_head(config=_config(), epic_id=_EPIC_ID)
    assert isinstance(head, ChainHead)
    return head


def _request(*, operation_id: str, head: ChainHead, consumed: int) -> TransitionRequest:
    return TransitionRequest(
        operation_id=operation_id,
        observed_head=head,
        authority=AuthorityState(
            required_result={"repo": "r", "file": "f.md"},
            original_deadline=_DEADLINE,
            max_handoffs=12,
            consumed_handoffs=consumed,
        ),
        event_kind="handoff",
        author="relay-session",
        now=_NOW,
    )


def _commit(*, operation_id: str, head: ChainHead, consumed: int = 1) -> object:
    return commit_transition(
        config=_config(),
        epic_id=_EPIC_ID,
        request=_request(operation_id=operation_id, head=head, consumed=consumed),
    )


def test_the_module_names_both_recovery_sources() -> None:
    """Each source is DIFFERENT evidence, so each is reported under its own name.

    A caller told only "recovered" cannot tell a receipt the authority it holds
    already accounts for from an event found by scanning an epic's history —
    and those two say different things about how far behind the caller is.
    """
    assert getattr(_plan_epoch_chain, "RECOVERED_FROM_RECEIPT_RING", None) == _RECOVERED_FROM_RING
    assert getattr(_plan_epoch_chain, "RECOVERED_FROM_PROGRESS_EVENT", None) == (
        _RECOVERED_FROM_EVENT
    )
    assert _RECOVERED_FROM_RING != _RECOVERED_FROM_EVENT != COMMITTED


def test_a_retry_from_the_same_observed_head_returns_the_original_event() -> None:
    """This is the shape a crashed or timed-out writer actually retries in.

    It never learned its close was admitted, so it comes back with the head it
    read BEFORE committing. Nothing about that request distinguishes it from a
    genuine stale writer except the operation id — which is exactly why the
    operation id is what the chain keys on.
    """
    _seed_chain()
    first = _commit(operation_id="op-1", head=_head())
    assert isinstance(first, CommittedTransition)
    assert first.source == COMMITTED
    stale_head = ChainHead(
        current_token_id=first.payload.prior_token_id,
        latest_closed_token_id=None,
        epoch=0,
    )
    live_before = _fake().no_history_issue_ids()

    retried = _commit(operation_id="op-1", head=stale_head)

    assert isinstance(retried, CommittedTransition)
    assert retried.payload == first.payload
    assert retried.source == _RECOVERED_FROM_EVENT
    # No second transition: the epoch, the live token set and the event count
    # are all exactly as the first commit left them.
    assert _head().epoch == 1
    assert _fake().no_history_issue_ids() == live_before
    assert len(read_progress_events(client=_fake(), epic_id=_EPIC_ID)) == 1


def test_a_retry_against_a_fresh_head_is_recognised_from_the_receipt_ring() -> None:
    """The ring is the evidence the writer already holds.

    A writer that re-read the chain carries the authority its own transition
    committed, and that authority names its own operation. Without the ring
    check this request looks like brand-new work at a current epoch — the one
    shape that would commit a duplicate rather than be refused as stale.
    """
    _seed_chain()
    first = _commit(operation_id="op-1", head=_head())
    assert isinstance(first, CommittedTransition)
    fresh = _head()
    assert [receipt.operation_id for receipt in fresh.authority.receipts] == ["op-1"]

    retried = _commit(operation_id="op-1", head=fresh)

    assert isinstance(retried, CommittedTransition)
    assert retried.payload == first.payload
    assert retried.source == _RECOVERED_FROM_RING
    assert _head().epoch == 1


def test_a_retry_older_than_the_ring_is_still_recovered_from_the_progress_events() -> None:
    """The ring is bounded, so the events are what make an old retry recoverable.

    After enough transitions the ring no longer names the operation, and a
    chain that keyed ONLY on the ring would read the retry as new work.
    """
    _seed_chain()
    first = _commit(operation_id="op-old", head=_head())
    assert isinstance(first, CommittedTransition)
    for index in range(RECEIPT_RING_SIZE + 1):
        later = _commit(operation_id=f"op-{index}", head=_head(), consumed=index + 2)
        assert isinstance(later, CommittedTransition)
    settled = _head()
    assert "op-old" not in [receipt.operation_id for receipt in settled.authority.receipts]
    epoch_before = settled.epoch

    retried = _commit(operation_id="op-old", head=settled)

    assert isinstance(retried, CommittedTransition)
    assert retried.payload == first.payload
    assert retried.source == _RECOVERED_FROM_EVENT
    assert _head().epoch == epoch_before


def test_a_retry_never_moves_the_original_deadline_or_the_consumed_count() -> None:
    """A retry is not an accepted handoff, so neither limit may move.

    The retry here asks for a HIGHER consumed count than the committed
    transition recorded. A chain that re-applied the request would consume a
    handoff unit for work that was already accounted for.
    """
    _seed_chain()
    first = _commit(operation_id="op-1", head=_head(), consumed=1)
    assert isinstance(first, CommittedTransition)

    retried = _commit(operation_id="op-1", head=_head(), consumed=9)

    assert isinstance(retried, CommittedTransition)
    assert retried.payload.authority.original_deadline == _DEADLINE
    assert retried.payload.authority.consumed_handoffs == 1
    settled = _head()
    assert settled.authority.original_deadline == _DEADLINE
    assert settled.authority.consumed_handoffs == 1


def test_the_public_scan_answers_the_retry_question_without_transitioning() -> None:
    """A caller has to be able to ask BEFORE it decides what to commit.

    `commit_transition`'s own guard is the chain's last word, but a caller that
    refuses the write before reaching it never gets the recovery the clause
    owes — which is how the retry of a budget-exhausting handoff came to be
    refused as expired. Both answers are asserted from one chain: `None` before
    the operation has committed is what makes the recovery afterwards evidence
    about the operation rather than about the function always answering.
    """
    _seed_chain()
    head = _head()

    assert (
        recover_committed_operation(
            config=_config(),
            epic_id=_EPIC_ID,
            operation_id="op-asked",
            observed_head=head,
        )
        is None
    )
    first = _commit(operation_id="op-asked", head=head)
    assert isinstance(first, CommittedTransition)
    live_before = _fake().no_history_issue_ids()

    recovered = recover_committed_operation(
        config=_config(),
        epic_id=_EPIC_ID,
        operation_id="op-asked",
        observed_head=_head(),
    )

    assert isinstance(recovered, CommittedTransition)
    assert recovered.payload == first.payload
    assert recovered.source == _RECOVERED_FROM_RING
    # Asking changes nothing: the epoch, the live token set and the event count
    # are all exactly as the one commit left them.
    assert _head().epoch == 1
    assert _fake().no_history_issue_ids() == live_before
    assert len(read_progress_events(client=_fake(), epic_id=_EPIC_ID)) == 1


def test_a_receipt_whose_event_cannot_be_read_is_reported_not_reinvented(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ring says it committed; the event that is owed cannot be read.

    Committing afresh would duplicate a handoff the ring already accounts for,
    and synthesizing the event would answer the retry with a transition nobody
    recorded. Both are worse than saying so. The damaged payload line here is
    what a truncated or hand-edited comment leaves behind — and a ledger
    comment can never be repaired, so this state is permanent once it happens.
    """
    _seed_chain()
    first = _commit(operation_id="op-1", head=_head())
    assert isinstance(first, CommittedTransition)
    fresh = _head()
    fake = _fake()

    def _damaged(*, issue_id: str) -> list[dict[str, Any]]:
        _ = issue_id
        return [{"text": f"{PLAN_PROGRESS_PREFIX}\n\noperation: op-1\npayload: truncated"}]

    monkeypatch.setattr(fake, "list_comments", _damaged)
    outcome = _commit(operation_id="op-1", head=fresh)

    assert isinstance(outcome, ChainFinding)
    assert outcome.code == RECEIPT_WITHOUT_EVENT
    assert "op-1" in outcome.detail
    assert _head().epoch == 1
