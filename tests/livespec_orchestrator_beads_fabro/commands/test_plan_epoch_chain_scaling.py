"""A long-lived chain holds at most two live tokens and a constant-size payload.

This is the property that makes the design usable on a plan epic that lives for
weeks. Research note 006 measured it over 60 transitions on one disposable
chain against the live tenant — write time, read time, payload bytes and live
record count all constant in the number of transitions — and it holds only
because of two rules this module pins: every payload carries the FULL state
rather than a delta with a bounded receipt ring, and the predecessor of the
latest closed token is DELETED after each transition.

The two rules are also what make each other possible, which is why they are
asserted together. Deleting old tokens is only safe because no reader ever
needs them; carrying full state is only affordable because the receipt ring is
bounded.
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
    TransitionRequest,
    commit_transition,
    read_chain_head,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_payload import (
    RECEIPT_RING_SIZE,
    AuthorityState,
    render_payload,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_projection import (
    chain_cache_metadata,
    read_progress_events,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_tokens import create_token
from livespec_orchestrator_beads_fabro.types import StoreConfig

_EPIC_ID = "bd-ib-relay1"
_NOW = "2026-10-12T09:00:00Z"
_DEADLINE = "2026-10-19T09:00:00Z"
# Enough transitions to fill the receipt ring twice over.
_TRANSITIONS = 24
_MAX_LIVE_TOKENS = 2
# The first transition whose WHOLE receipt ring is two decimal digits wide.
# Measured rather than chosen: at transition N the ring holds epochs
# N - RECEIPT_RING_SIZE + 1 .. N, so every entry is two digits from N = 17 on.
# The decimal width of the epoch counter is the ONE quantity that does grow,
# logarithmically, and a window straddling a digit boundary would report that
# as unbounded growth.
_DIGIT_STABLE_FROM = 17


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
    return genesis


def _head() -> ChainHead:
    head = read_chain_head(config=_config(), epic_id=_EPIC_ID)
    assert isinstance(head, ChainHead)
    return head


def _commit(*, index: int) -> CommittedTransition:
    """Commit one transition under a FIXED-WIDTH operation id.

    Fixed width is what makes the payload-size comparison a statement about
    the chain rather than about how many digits an index happens to have.
    """
    committed = commit_transition(
        config=_config(),
        epic_id=_EPIC_ID,
        request=TransitionRequest(
            operation_id=f"op-{index:04d}",
            observed_head=_head(),
            authority=AuthorityState(
                required_result={"repo": "r", "file": "f.md"},
                original_deadline=_DEADLINE,
                max_handoffs=99,
                consumed_handoffs=1,
            ),
            event_kind="handoff",
            author="relay-session",
            now=_NOW,
        ),
    )
    assert isinstance(committed, CommittedTransition)
    return committed


def test_a_long_lived_chain_never_holds_more_than_two_live_token_records() -> None:
    """Measured at EVERY step, not only at the end.

    A chain that accumulated tokens and swept them at the close would pass an
    end-state assertion while holding an unbounded set in between, which is
    the shape that fills a tenant.
    """
    genesis = _seed_chain()
    live_counts: list[int] = []
    committed: list[CommittedTransition] = []

    for index in range(1, _TRANSITIONS + 1):
        committed.append(_commit(index=index))
        live_counts.append(len(_fake().no_history_issue_ids()))

    assert max(live_counts) <= _MAX_LIVE_TOKENS
    # And the two that remain are exactly the latest closed token and the
    # current open one — not two arbitrary survivors.
    head = _head()
    assert head.latest_closed_token_id is not None
    assert sorted(_fake().no_history_issue_ids()) == sorted(
        [head.latest_closed_token_id, head.current_token_id]
    )
    assert genesis not in _fake().no_history_issue_ids()
    assert head.epoch == _TRANSITIONS


def test_the_authority_payload_stops_growing_once_the_receipt_ring_fills() -> None:
    """Constant size is what "full state, never a delta" is affordable on.

    The ring is bounded, every other authority field is fixed-shape, and the
    payload carries nothing from the work item — no description, no criteria,
    no comments — so a larger plan does not make a larger token.

    The comparison is taken over the transitions whose ring entries are ALL
    two decimal digits wide. That is the honest claim: the payload is constant
    in the number of transitions, apart from the logarithmic width of the
    counters it prints, and a window straddling a digit boundary would read
    that widening as unbounded growth.
    """
    _seed_chain()
    sizes: dict[int, int] = {}

    for index in range(1, _TRANSITIONS + 1):
        committed = _commit(index=index)
        sizes[index] = len(render_payload(payload=committed.payload).encode("utf-8"))

    stable = [index for index in sizes if index >= _DIGIT_STABLE_FROM]
    assert len(stable) >= RECEIPT_RING_SIZE
    assert len({sizes[index] for index in stable}) == 1
    # The growing prefix is real and BOUNDED: the ring filling is what the
    # early growth is, and once full the payload stops responding to length.
    assert sizes[1] < sizes[_DIGIT_STABLE_FROM]
    # Across the digit boundary the only growth is decimal WIDENING, and the
    # payload prints a bounded number of counters: the two epochs, one epoch
    # per ring entry, and the two token ids. One decade crossing can add at
    # most that many bytes — a bound that does not grow with the number of
    # transitions, which is the claim being made.
    widenable_counters = 2 + RECEIPT_RING_SIZE + 2
    assert sizes[_TRANSITIONS] - sizes[RECEIPT_RING_SIZE + 1] <= widenable_counters
    # Every transition is still recorded: the bound is on LIVE TOKENS, not on
    # the obligation history.
    events = read_progress_events(client=_fake(), epic_id=_EPIC_ID)
    assert len(events) == _TRANSITIONS


def test_the_receipt_ring_holds_the_newest_transitions_of_a_long_chain() -> None:
    """The ring is a window on the chain, so the newest entries are the ones kept."""
    _seed_chain()
    for index in range(1, _TRANSITIONS + 1):
        _ = _commit(index=index)

    receipts = _head().authority.receipts

    assert len(receipts) == RECEIPT_RING_SIZE
    assert [receipt.operation_id for receipt in receipts] == [
        f"op-{index:04d}" for index in range(_TRANSITIONS - RECEIPT_RING_SIZE + 1, _TRANSITIONS + 1)
    ]
