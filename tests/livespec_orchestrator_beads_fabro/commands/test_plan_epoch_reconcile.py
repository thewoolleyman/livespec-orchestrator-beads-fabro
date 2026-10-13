"""A partial write is reported and reconciled before any dispatch is authorized.

`contracts.md` section "Required result, budget and progress epoch": "A partial
write MUST be diagnosable and must not authorize a fresh dispatch until
reconciled." The state is reachable because a transition and its projections
are DIFFERENT writes: the close commits, and the progress event and the
metadata cache are written afterwards. A writer that stops in between leaves a
chain that has moved on and projections that have not.

Each partial write here is produced by performing the transition through the
TOKEN primitives and writing no projection at all, which is what a stopped
writer actually leaves behind.
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
from livespec_orchestrator_beads_fabro.commands._plan_epoch_findings import (
    MISSING_TRACKING,
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
    PLAN_RECONCILE_ACTOR,
    authorized_head,
    reconcile_projections,
    verify_projections,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_tokens import (
    attempt_close,
    create_token,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

_EPIC_ID = "bd-ib-relay1"
_NOW = "2026-10-12T09:00:00Z"
_RECONCILED_AT = "2026-10-12T10:00:00Z"
_DEADLINE = "2026-10-19T09:00:00Z"


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


def _seed_chain() -> None:
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


def _authority(*, consumed: int = 1) -> AuthorityState:
    return AuthorityState(
        required_result={"repo": "r", "file": "f.md"},
        original_deadline=_DEADLINE,
        max_handoffs=4,
        consumed_handoffs=consumed,
    )


def _head() -> ChainHead:
    head = read_chain_head(config=_config(), epic_id=_EPIC_ID)
    assert isinstance(head, ChainHead)
    return head


def _commit_through_the_chain(*, operation_id: str) -> CommittedTransition:
    committed = commit_transition(
        config=_config(),
        epic_id=_EPIC_ID,
        request=TransitionRequest(
            operation_id=operation_id,
            observed_head=_head(),
            authority=_authority(),
            event_kind="handoff",
            author="relay-session",
            now=_NOW,
        ),
    )
    assert isinstance(committed, CommittedTransition)
    return committed


def _commit_and_stop(*, operation_id: str, event_kind: str = "supervisor-handoff") -> str:
    """Commit one transition at the token level and write NO projection.

    This is the stopped writer: the close is durable, the epic still names the
    old token and carries no event for the new transition.
    """
    fake = _fake()
    head = _head()
    candidate = create_token(client=fake)
    attempt_close(
        client=fake,
        token_id=head.current_token_id,
        reason=render_payload(
            payload=TransitionPayload(
                operation_id=operation_id,
                prior_epoch=head.epoch,
                new_epoch=head.epoch + 1,
                prior_token_id=head.current_token_id,
                next_token_id=candidate,
                event_kind=event_kind,
                authority=_authority(consumed=head.epoch + 1),
            )
        ),
    )
    return candidate


def test_a_healthy_chain_reports_nothing_and_reconciles_nothing() -> None:
    """The positive control: these verbs must be SILENT on a chain that agrees.

    Without it, a verifier that reported every chain as a partial write would
    satisfy every other case in this module.
    """
    _seed_chain()
    _ = _commit_through_the_chain(operation_id="op-1")
    events_before = read_progress_events(client=_fake(), epic_id=_EPIC_ID)

    assert verify_projections(config=_config(), epic_id=_EPIC_ID) is None
    assert reconcile_projections(config=_config(), epic_id=_EPIC_ID, now=_RECONCILED_AT) is None
    assert isinstance(authorized_head(config=_config(), epic_id=_EPIC_ID), ChainHead)
    assert read_progress_events(client=_fake(), epic_id=_EPIC_ID) == events_before


def test_a_stopped_writers_partial_write_is_reported_and_withholds_the_dispatch() -> None:
    """The transition is durable and both projections are missing.

    The head still READS correctly — the walk follows the closed token's own
    next link — which is exactly why the disagreement has to be checked
    separately: a reader that only walked would see a healthy epoch and
    authorize a dispatch against projections nobody wrote.
    """
    _seed_chain()
    candidate = _commit_and_stop(operation_id="op-stopped")

    finding = verify_projections(config=_config(), epic_id=_EPIC_ID)

    assert isinstance(finding, ChainFinding)
    assert finding.code == PARTIAL_WRITE
    assert "before authorizing a dispatch" in finding.remedy
    withheld = authorized_head(config=_config(), epic_id=_EPIC_ID)
    assert isinstance(withheld, ChainFinding)
    assert withheld.code == PARTIAL_WRITE
    # The chain itself is intact: the walk reaches the new token at epoch 1.
    assert _head().current_token_id == candidate
    assert _head().epoch == 1


def test_reconciling_restores_both_projections_from_the_chain_itself() -> None:
    """Reconciliation reads the chain and rewrites the projections, never the reverse.

    The re-projected event carries the ORIGINAL payload and its original event
    kind, because the closed token's close reason is the lossless record of the
    transition; a reconciler that re-derived the event from the current
    authority would publish a transition nobody committed. It signs the event
    as itself, because no session identity is the honest author of a record
    that somebody else's dead writer owed.
    """
    _seed_chain()
    candidate = _commit_and_stop(operation_id="op-stopped", event_kind="supervisor-handoff")

    reconciled = reconcile_projections(config=_config(), epic_id=_EPIC_ID, now=_RECONCILED_AT)

    assert isinstance(reconciled, ChainFinding)
    assert reconciled.code == PARTIAL_WRITE
    events = read_progress_events(client=_fake(), epic_id=_EPIC_ID)
    assert [event.operation_id for event in events] == ["op-stopped"]
    payload = events[0].payload
    assert payload is not None
    assert payload.next_token_id == candidate
    assert payload.event_kind == "supervisor-handoff"
    assert payload.authority.original_deadline == _DEADLINE
    comment = _fake().list_comments(issue_id=_EPIC_ID)[0]["text"]
    assert isinstance(comment, str)
    assert f"author: {PLAN_RECONCILE_ACTOR}" in comment
    # And the epic now authorizes a dispatch, reporting nothing further.
    assert verify_projections(config=_config(), epic_id=_EPIC_ID) is None
    assert isinstance(authorized_head(config=_config(), epic_id=_EPIC_ID), ChainHead)


def test_a_cache_that_lags_while_the_event_stands_is_still_a_partial_write() -> None:
    """The two projections fail independently, so each is checked on its own.

    Here the progress event IS on the timeline and only the cache is behind —
    the shape a writer leaves when it stops between its two projection writes.
    """
    _seed_chain()
    first = _commit_through_the_chain(operation_id="op-1")
    stale = first.payload.prior_token_id
    write_chain_cache(client=_fake(), epic_id=_EPIC_ID, latest_closed=None, current=stale)

    finding = verify_projections(config=_config(), epic_id=_EPIC_ID)

    assert isinstance(finding, ChainFinding)
    assert finding.code == PARTIAL_WRITE
    assert stale in finding.detail
    assert reconcile_projections(config=_config(), epic_id=_EPIC_ID, now=_RECONCILED_AT) is not None
    assert verify_projections(config=_config(), epic_id=_EPIC_ID) is None
    # Reconciling the cache did NOT append a second copy of a standing event.
    events = read_progress_events(client=_fake(), epic_id=_EPIC_ID)
    assert [event.operation_id for event in events] == ["op-1"]


def test_reconciling_a_partial_write_also_discards_the_predecessor_it_leaked() -> None:
    """A repaired partial write leaves at most two live tokens, as a commit does.

    The stopped writer's close is durable, so the chain has moved on while the
    token that writer's OWN completed commit would have discarded — the
    predecessor the stale cache still names as the latest closed — stays live.
    Restoring the event and the cache does not retire it, and every LATER
    commit discards only the predecessor of the token IT closed, so one stopped
    writer leaks one record for the rest of the epic's life unless the
    reconciler finishes that delete too.

    Measured on the live tenant 2026-10-13 against released build v0.194.0:
    after one partial write a disposable epic held THREE live token records at
    every checkpoint of a 60-transition run, the chain's own pair plus the
    stranded predecessor.

    The count is read after the reconcile AND after each later commit, because
    a reconciler that deleted the right record but left the ordinary commit
    path broken would satisfy a single end-state reading.
    """
    _seed_chain()
    _ = _commit_through_the_chain(operation_id="op-1")
    leaked = _head().latest_closed_token_id
    _ = _commit_and_stop(operation_id="op-stopped")

    reconciled = reconcile_projections(config=_config(), epic_id=_EPIC_ID, now=_RECONCILED_AT)

    assert isinstance(reconciled, ChainFinding)
    assert leaked is not None
    assert leaked not in _fake().no_history_issue_ids()
    live_counts = [len(_fake().no_history_issue_ids())]
    for index in range(2, 6):
        _ = _commit_through_the_chain(operation_id=f"op-{index}")
        live_counts.append(len(_fake().no_history_issue_ids()))
    assert live_counts == [2, 2, 2, 2, 2]
    # The repair itself is unchanged: the chain still walks to the epoch the
    # stopped writer committed plus the four that followed it.
    assert _head().epoch == 6


def test_an_epic_naming_no_chain_withholds_the_dispatch_with_its_own_finding() -> None:
    """A missing chain is NOT a partial write, and the two remedies differ.

    One is reconciled from the chain; the other needs the sanctioned migration
    to create a genesis token, and reporting either as the other sends an
    operator to the wrong repair.
    """
    _ = _seed_epic()

    withheld = authorized_head(config=_config(), epic_id=_EPIC_ID)
    reported = verify_projections(config=_config(), epic_id=_EPIC_ID)
    attempted = reconcile_projections(config=_config(), epic_id=_EPIC_ID, now=_RECONCILED_AT)

    assert isinstance(withheld, ChainFinding)
    assert withheld.code == MISSING_TRACKING
    assert isinstance(reported, ChainFinding)
    assert reported.code == MISSING_TRACKING
    assert isinstance(attempted, ChainFinding)
    assert attempted.code == MISSING_TRACKING
    assert "migration" in attempted.remedy
    # Nothing was written on the way to that report.
    assert _fake().list_comments(issue_id=_EPIC_ID) == []
    assert _fake().no_history_issue_ids() == ()
