"""What a token-guarded Dispatcher claim write sends, and what it answers.

`_dispatcher_claim_guard` rebuilds the store's two claim writers on top of
`change_claim`, because the claim-token protocol allows a winner exactly one
ledger write. These cases pin the two halves of that:

- a write that WINS carries everything the store writer carries (the status,
  the assignee, the label removals, the ready-dwell instant, any overlay) and
  names the successor token in that same write;
- a write that does NOT win answers the protocol's own outcome name and leaves
  the item exactly as it was.

Every case runs against the in-memory tenant, so the assertions are about what
the tenant holds afterwards and never about which client call was made.
"""

from __future__ import annotations

import copy
import json

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    CLAIM_TOKEN_METADATA_KEY,
    ClaimRow,
    ClaimStamp,
    claim_row_from_record,
    claim_stamp_metadata,
    create_claim_token,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_guard import (
    TRANSITION_OBSERVATIONS,
    Decided,
    claimed_by_run,
    guarded_blocked_write,
    guarded_hold,
    guarded_metadata_write,
    guarded_status_write,
    guarded_write,
    held,
    learning_run,
    same_claim_row,
    status_is,
    terminal_claim,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-guarded"
_WRITER = "dispatcher-terminal"
_ANOTHER_WRITER = "another writer won this token"


@pytest.fixture(autouse=True)
def _fresh_tenant() -> object:
    reset_fake_singleton()
    TRANSITION_OBSERVATIONS.clear()
    yield
    TRANSITION_OBSERVATIONS.clear()
    reset_fake_singleton()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _claim(
    *,
    labels: tuple[str, ...] = (),
    metadata: dict[str, object] | None = None,
    name_a_token: bool = True,
) -> tuple[FakeBeadsClient, str]:
    """An `active` item assigned `fabro` that names an open current token.

    `name_a_token=False` builds the same item naming NO token. A metadata
    write merges, so a later write cannot take the name away again.
    """
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=_ITEM_ID,
            issue_type="task",
            title="A dispatched slice",
            description="Implement the slice.",
            assignee="fabro",
            created_at="2026-11-06T00:00:00Z",
        )
    )
    token = create_claim_token(client=client)
    named = {CLAIM_TOKEN_METADATA_KEY: token} if name_a_token else {}
    client.update_issue(
        issue_id=_ITEM_ID,
        status="active",
        add_labels=list(labels),
        metadata={**(metadata or {}), **named},
        names_claim_token=True,
    )
    return client, token


def _snapshot(*, client: FakeBeadsClient) -> dict[str, object]:
    return copy.deepcopy(client.show_issue(issue_id=_ITEM_ID))


def _successor_won_from(*, client: FakeBeadsClient, token: str) -> str:
    """The successor the item now names, checked against the won token's reason."""
    successor = client.show_issue(issue_id=_ITEM_ID)["metadata"][CLAIM_TOKEN_METADATA_KEY]
    won = json.loads(client.show_issue(issue_id=token)["close_reason"])
    assert (won["writer"], won["successor"]) == (_WRITER, successor)
    assert client.show_issue(issue_id=successor)["status"] != "closed"
    return won["intent"]


def _lose_the_token(
    *, client: FakeBeadsClient, token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    close = client.close_issue_without_verdict

    def _raced(*, issue_id: str, reason: str) -> None:
        if issue_id == token:
            close(issue_id=issue_id, reason=_ANOTHER_WRITER)
        close(issue_id=issue_id, reason=reason)

    monkeypatch.setattr(client, "close_issue_without_verdict", _raced)


def test_a_won_status_write_lands_status_assignee_overlay_and_successor_together() -> None:
    client, token = _claim(labels=("blocked-reason:needs-human",), metadata={"rank": "a0"})

    refusal = guarded_status_write(
        path=_config(),
        item_id=_ITEM_ID,
        status="active",
        intent="admit",
        writer=_WRITER,
        assignee="someone",
        metadata={"dispatch_claim": {"dispatch_id": "01D"}},
    )

    record = client.show_issue(issue_id=_ITEM_ID)
    assert refusal is None
    assert (record["status"], record["assignee"]) == ("active", "someone")
    assert record["metadata"]["dispatch_claim"] == {"dispatch_id": "01D"}
    # The overlay is merged over what the item already carried, never instead of it.
    assert record["metadata"]["rank"] == "a0"
    # A status other than `blocked` clears the blocked-reason in the same write.
    assert "blocked-reason:needs-human" not in record["labels"]
    assert _successor_won_from(client=client, token=token) == "admit"


def test_a_won_release_to_ready_clears_the_claim_and_stamps_the_ready_instant() -> None:
    client, token = _claim(labels=("rework:pending",))

    refusal = guarded_status_write(
        path=_config(),
        item_id=_ITEM_ID,
        status="ready",
        intent="stall-release",
        writer=_WRITER,
        clear_assignee=True,
    )

    record = client.show_issue(issue_id=_ITEM_ID)
    assert refusal is None
    assert (record["status"], record["assignee"]) == ("ready", None)
    assert isinstance(record["metadata"]["ready_since"], str)
    # Leaving `active` clears the rework marker in the same write.
    assert "rework:pending" not in record["labels"]
    assert _successor_won_from(client=client, token=token) == "stall-release"


def test_a_won_blocked_rest_replaces_the_reason_and_the_admission_label_in_one_write() -> None:
    client, token = _claim(
        labels=("blocked-reason:infra-external", "admission:auto", "rework:pending")
    )

    refusal = guarded_blocked_write(
        path=_config(),
        item_id=_ITEM_ID,
        blocked_reason="needs-human",
        intent="needs-human-block",
        writer=_WRITER,
        admission_policy="manual",
        metadata={"acceptance_failed_ai_passes": 3},
    )

    record = client.show_issue(issue_id=_ITEM_ID)
    assert refusal is None
    assert record["status"] == "blocked"
    assert sorted(record["labels"]) == ["admission:manual", "blocked-reason:needs-human"]
    assert record["metadata"]["acceptance_failed_ai_passes"] == 3
    assert _successor_won_from(client=client, token=token) == "needs-human-block"


def test_a_blocked_rest_keeps_a_label_it_is_writing_that_the_item_already_carries() -> None:
    """Additions and removals are disjoint, so a re-written label survives its own write."""
    client, _ = _claim(labels=("blocked-reason:needs-human", "admission:manual"))

    refusal = guarded_blocked_write(
        path=_config(),
        item_id=_ITEM_ID,
        blocked_reason="needs-human",
        intent="stall-repeat-rest",
        writer=_WRITER,
        admission_policy="manual",
    )

    assert refusal is None
    assert sorted(client.show_issue(issue_id=_ITEM_ID)["labels"]) == [
        "admission:manual",
        "blocked-reason:needs-human",
    ]


def test_a_blocked_rest_with_no_admission_policy_leaves_the_admission_label_alone() -> None:
    client, _ = _claim(labels=("admission:auto",))

    refusal = guarded_blocked_write(
        path=_config(),
        item_id=_ITEM_ID,
        blocked_reason="needs-human",
        intent="absent-run-repeated-rest",
        writer=_WRITER,
    )

    assert refusal is None
    assert sorted(client.show_issue(issue_id=_ITEM_ID)["labels"]) == [
        "admission:auto",
        "blocked-reason:needs-human",
    ]


def test_a_won_hold_names_the_successor_and_changes_nothing_else() -> None:
    client, token = _claim(labels=("admission:auto",), metadata={"rank": "a0"})
    before = _snapshot(client=client)

    refusal = guarded_hold(
        path=_config(), item_id=_ITEM_ID, intent="close-completed", writer=_WRITER
    )

    after = _snapshot(client=client)
    assert refusal is None
    assert _successor_won_from(client=client, token=token) == "close-completed"
    after["metadata"][CLAIM_TOKEN_METADATA_KEY] = token
    assert after == before


def test_a_won_metadata_write_lands_its_overlay_and_the_successor_and_nothing_else() -> None:
    """A run stamp's keys are an overlay: no other key, label or field is re-sent."""
    client, token = _claim(labels=("admission:auto",), metadata={"rank": "a0"})
    before = _snapshot(client=client)

    refusal = guarded_metadata_write(
        path=_config(),
        item_id=_ITEM_ID,
        intent="run-stamp",
        writer=_WRITER,
        metadata={"dispatch_fabro_run_id": "01RUN"},
    )

    after = _snapshot(client=client)
    assert refusal is None
    assert after["metadata"]["dispatch_fabro_run_id"] == "01RUN"
    assert _successor_won_from(client=client, token=token) == "run-stamp"
    del after["metadata"]["dispatch_fabro_run_id"]
    after["metadata"][CLAIM_TOKEN_METADATA_KEY] = token
    assert after == before


@pytest.mark.parametrize("write", ["status", "blocked", "hold", "metadata"])
def test_a_write_that_loses_the_token_reports_claim_changed_and_writes_nothing(
    write: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, token = _claim(labels=("admission:auto",))
    before = _snapshot(client=client)
    _lose_the_token(client=client, token=token, monkeypatch=monkeypatch)

    refusal = _guarded_write(write=write)

    assert refusal == "claim-changed"
    assert _snapshot(client=client) == before
    # The loser discarded its own successor: no token is left open but none.
    assert [
        token_id
        for token_id in client.no_history_issue_ids()
        if client.show_issue(issue_id=token_id)["status"] != "closed"
    ] == []


def _guarded_write(*, write: str) -> str | None:
    if write == "status":
        return guarded_status_write(
            path=_config(), item_id=_ITEM_ID, status="ready", intent="release", writer=_WRITER
        )
    if write == "blocked":
        return guarded_blocked_write(
            path=_config(),
            item_id=_ITEM_ID,
            blocked_reason="needs-human",
            intent="rest",
            writer=_WRITER,
        )
    if write == "hold":
        return guarded_hold(path=_config(), item_id=_ITEM_ID, intent="close", writer=_WRITER)
    return guarded_metadata_write(
        path=_config(),
        item_id=_ITEM_ID,
        intent="run-stamp",
        writer=_WRITER,
        metadata={"dispatch_fabro_run_id": "01RUN"},
    )


def test_an_item_naming_no_token_is_refused_as_claim_token_missing() -> None:
    client, _ = _claim(metadata={"rank": "a0"}, name_a_token=False)
    before = _snapshot(client=client)

    refusal = guarded_status_write(
        path=_config(), item_id=_ITEM_ID, status="ready", intent="release", writer=_WRITER
    )

    assert refusal == "claim-token-missing"
    assert _snapshot(client=client) == before


def test_an_unapplied_transition_is_reported_pending_and_its_first_sighting_is_kept() -> None:
    """A crashed winner's transition is waited out, measured from this process's sighting."""
    client, token = _claim()
    stranded_successor = create_claim_token(client=client)
    client.close_issue_without_verdict(
        issue_id=token,
        reason=json.dumps(
            {"kind": "claim-token-transition", "writer": "crashed", "successor": stranded_successor}
        ),
    )
    before = _snapshot(client=client)

    refusal = guarded_hold(path=_config(), item_id=_ITEM_ID, intent="close", writer=_WRITER)

    assert refusal == "claim-transition-pending"
    assert _snapshot(client=client) == before
    assert list(TRANSITION_OBSERVATIONS) == [(_ITEM_ID, token, stranded_successor)]


def test_the_public_primitive_sends_exactly_the_fields_it_is_given_and_the_successor() -> None:
    """`guarded_write` adds nothing of its own: no label is cleared, no instant stamped."""
    client, token = _claim(labels=("rework:pending", "blocked-reason:needs-human"))

    refusal = guarded_write(
        path=_config(),
        item_id=_ITEM_ID,
        writer=_WRITER,
        intent="size-decomposition",
        status="ready",
    )

    record = client.show_issue(issue_id=_ITEM_ID)
    assert refusal is None
    assert (record["status"], record["assignee"]) == ("ready", "fabro")
    assert sorted(record["labels"]) == ["blocked-reason:needs-human", "rework:pending"]
    assert "ready_since" not in record["metadata"]
    assert _successor_won_from(client=client, token=token) == "size-decomposition"


def _record(
    *,
    status: str = "active",
    assignee: str | None = "fabro",
    stamp: ClaimStamp | None = None,
) -> dict[str, object]:
    """An issue record as the ledger returns it, carrying the given claim stamp."""
    metadata = {} if stamp is None else claim_stamp_metadata(stamp=stamp)
    return {"id": _ITEM_ID, "status": status, "assignee": assignee, "metadata": metadata}


def _stamp(*, run_id: str | None, dispatch_id: str | None = "01DISPATCH") -> ClaimStamp:
    return ClaimStamp(
        dispatch_id=dispatch_id,
        dispatching_host="owning-host",
        run_id=run_id,
        factory_name="hp",
        factory_server=None,
    )


def test_status_is_compares_the_stored_spelling_of_the_status() -> None:
    assert status_is(status="ready")(_record(status="ready")) is True
    assert status_is(status="ready")(_record(status="active")) is False
    # A livespec `done` is stored `closed`, so that is what the predicate looks for.
    assert status_is(status="done")(_record(status="closed")) is True
    assert status_is(status="done")(_record(status="done")) is False


def test_held_requires_the_status_and_the_assignee_together() -> None:
    assert held(status="active", assignee="fabro")(_record()) is True
    assert held(status="active", assignee="fabro")(_record(status="blocked")) is False
    assert held(status="active", assignee="fabro")(_record(assignee="someone")) is False
    # An unassigned decision matches a record stored with no assignee or an empty one.
    assert held(status="ready", assignee=None)(_record(status="ready", assignee=None)) is True
    assert held(status="ready", assignee=None)(_record(status="ready", assignee="")) is True
    assert held(status="ready", assignee=None)(_record(status="ready")) is False


@pytest.mark.parametrize(
    ("stamp", "strict", "lenient"),
    [
        (_stamp(run_id="01RUN"), True, True),
        (_stamp(run_id="01ANOTHER"), False, False),
        (_stamp(run_id=None), False, True),
        (None, False, True),
    ],
    ids=["this-run", "another-run", "pending", "unstamped"],
)
def test_claimed_by_run_refuses_another_run_and_reads_a_missing_stamp_as_it_is_told(
    *, stamp: ClaimStamp | None, strict: bool, lenient: bool
) -> None:
    """A recovery needs the stamp to NAME its run; a terminal disposition does not."""
    record = _record(stamp=stamp)

    assert claimed_by_run(assignee="fabro", run_id="01RUN")(record) is strict
    assert claimed_by_run(assignee="fabro", run_id="01RUN", unstamped_ok=True)(record) is lenient


def test_claimed_by_run_with_no_run_asks_nothing_of_the_stamp_but_still_asks_who_holds() -> None:
    another = _record(stamp=_stamp(run_id="01ANOTHER"))

    assert claimed_by_run(assignee="fabro", run_id=None)(another) is True
    assert claimed_by_run(assignee="fabro", run_id=None)(_record(assignee=None)) is False
    assert claimed_by_run(assignee="fabro", run_id=None, status="acceptance")(another) is False


def _work_item(*, status: str, assignee: str | None) -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="task",
        status=status,
        title="A dispatched slice",
        description="Implement the slice.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=assignee,
        depends_on=(),
        captured_at="2026-11-06T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def test_terminal_claim_is_the_item_as_handed_under_a_stamp_naming_no_other_run() -> None:
    decided = terminal_claim(item=_work_item(status="active", assignee="fabro"), run_id="01RUN")

    assert decided(_record(stamp=_stamp(run_id="01RUN"))) is True
    assert decided(_record(stamp=None)) is True
    assert decided(_record(stamp=_stamp(run_id="01ANOTHER"))) is False
    assert decided(_record(status="ready", assignee=None)) is False


@pytest.mark.parametrize(
    ("stamp", "dispatch_id", "expected"),
    [
        (None, "01DISPATCH", True),
        (_stamp(run_id="01RUN", dispatch_id="01OTHER"), "01DISPATCH", True),
        (_stamp(run_id=None), "01DISPATCH", True),
        (_stamp(run_id="01OLDRUN"), "01DISPATCH", True),
        (_stamp(run_id=None, dispatch_id="01OTHER"), "01DISPATCH", False),
        (_stamp(run_id=None, dispatch_id="01OTHER"), None, True),
        (_stamp(run_id=None, dispatch_id=None), "01DISPATCH", True),
        (_stamp(run_id="01OLDRUN", dispatch_id="01OTHER"), None, False),
    ],
    ids=[
        "unstamped",
        "this-run-already",
        "own-pending-stamp",
        "own-dispatch-moving-to-a-new-run",
        "another-dispatch-pending",
        "pending-and-own-dispatch-unknown",
        "pending-and-stamped-dispatch-unknown",
        "another-run-and-own-dispatch-unknown",
    ],
)
def test_learning_run_accepts_only_a_claim_nothing_says_belongs_to_another_dispatch(
    *, stamp: ClaimStamp | None, dispatch_id: str | None, expected: bool
) -> None:
    decided = learning_run(dispatch_id=dispatch_id, run_id="01RUN")

    assert decided(_record(stamp=stamp)) is expected


def test_learning_run_refuses_an_item_that_is_no_longer_active() -> None:
    decided = learning_run(dispatch_id="01DISPATCH", run_id="01RUN")

    assert decided(_record(status="ready", stamp=_stamp(run_id=None))) is False


def test_same_claim_row_requires_an_active_row_identical_to_the_one_read() -> None:
    record = _record(stamp=_stamp(run_id=None))
    row = claim_row_from_record(record=record)

    assert same_claim_row(row=row)(record) is True
    assert same_claim_row(row=row)(_record(stamp=_stamp(run_id="01RUN"))) is False
    assert same_claim_row(row=row)(_record(assignee="someone", stamp=_stamp(run_id=None))) is False
    # A row that was not an `active` claim when it was read is never one to stamp.
    ready = ClaimRow(status="ready", assignee="fabro", stamp=row.stamp)
    assert same_claim_row(row=ready)(_record(status="ready", stamp=_stamp(run_id=None))) is False


def _never(_record: dict[str, object]) -> bool:
    return False


_SHAPED_WRITES: dict[str, object] = {
    "status": lambda decided: guarded_status_write(
        path=_config(),
        item_id=_ITEM_ID,
        status="ready",
        intent="release",
        writer=_WRITER,
        still_as_decided=decided,
    ),
    "blocked": lambda decided: guarded_blocked_write(
        path=_config(),
        item_id=_ITEM_ID,
        blocked_reason="needs-human",
        intent="rest",
        writer=_WRITER,
        still_as_decided=decided,
    ),
    "hold": lambda decided: guarded_hold(
        path=_config(), item_id=_ITEM_ID, intent="close", writer=_WRITER, still_as_decided=decided
    ),
    "metadata": lambda decided: guarded_metadata_write(
        path=_config(),
        item_id=_ITEM_ID,
        intent="run-stamp",
        writer=_WRITER,
        metadata={"dispatch_fabro_run_id": "01RUN"},
        still_as_decided=decided,
    ),
    "primitive": lambda decided: guarded_write(
        path=_config(),
        item_id=_ITEM_ID,
        writer=_WRITER,
        intent="size-decomposition",
        status="backlog",
        still_as_decided=decided,
    ),
}


@pytest.mark.parametrize("write", sorted(_SHAPED_WRITES))
def test_every_guarded_write_refuses_uncontested_when_its_decision_no_longer_holds(
    write: str,
) -> None:
    """`still_as_decided` reaches `change_claim` from each helper, under that name."""
    client, token = _claim(labels=("admission:auto",))
    before = _snapshot(client=client)

    refusal = _SHAPED_WRITES[write](_never)

    assert refusal == "claim-changed"
    assert _snapshot(client=client) == before
    # Nothing was contested: the token is open and no successor was minted.
    assert client.no_history_issue_ids() == (token,)
    assert client.show_issue(issue_id=token)["status"] != "closed"


@pytest.mark.parametrize("write", sorted(_SHAPED_WRITES))
def test_every_guarded_write_lands_when_its_decision_still_holds(write: str) -> None:
    client, token = _claim()
    decided: Decided = claimed_by_run(assignee="fabro", run_id=None)

    refusal = _SHAPED_WRITES[write](decided)

    assert refusal is None
    assert client.show_issue(issue_id=token)["status"] == "closed"
