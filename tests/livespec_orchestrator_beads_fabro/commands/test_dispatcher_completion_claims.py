"""The completion valve's three claim-changing writes, one value of the key at a time.

`CompletionClaim` is how `_dispatcher_completion` makes its ledger writes: the
`active -> acceptance` completion, the hold that precedes a close, and the
non-convergence bounce to `backlog`.

With `dispatcher.claim_tokens` false or unset each is the valve's own store
writer, called with the arguments the valve always passed, and a close is
preceded by no write at all. With the key true each lands only after winning
the item's current claim token, and a write that loses it changes nothing.

Each guarded write is also bound to what the valve decided on: the item's
status and assignee as the valve was handed them, and a claim stamp that names
no other run. A write whose decision no longer holds is refused without
contesting the token at all.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    CLAIM_TOKEN_METADATA_KEY,
    ClaimStamp,
    create_claim_token,
    record_claim_stamp,
)
from livespec_orchestrator_beads_fabro.commands import _dispatcher_completion_claims
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_guard import (
    TRANSITION_OBSERVATIONS,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_completion_claims import (
    CompletionClaim,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-completing"
_RUN_ID = "01COMPLETINGRUN"
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


def _repo(*, tmp_path: Path, claim_tokens: bool) -> Path:
    if claim_tokens:
        _ = (tmp_path / ".livespec.jsonc").write_text(
            '{"livespec-orchestrator-beads-fabro": {"dispatcher": {"claim_tokens": true}}}',
            encoding="utf-8",
        )
    return tmp_path


class _Journal:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def __call__(self, **kwargs: object) -> None:
        self.calls.append(kwargs)


def _item() -> WorkItem:
    """The dispatched item as the valve is handed it: `active`, assigned `fabro`."""
    return WorkItem(
        id=_ITEM_ID,
        type="task",
        status="active",
        title="A dispatched slice",
        description="Implement the slice.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-11-06T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _outcome() -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=_ITEM_ID,
        status="green",
        stage="done",
        pr_number=11,
        merge_sha="feed01",
        detail="merged",
        fabro_run_id=_RUN_ID,
    )


def _claim(*, repo: Path, journal: _Journal) -> CompletionClaim:
    return CompletionClaim(
        repo=repo, path=_config(), item=_item(), outcome=_outcome(), journal=journal
    )


def _stamp(*, run_id: str) -> ClaimStamp:
    return ClaimStamp(
        dispatch_id="01DISPATCH",
        dispatching_host="owning-host",
        run_id=run_id,
        factory_name="hp",
        factory_server=None,
    )


def _seed(*, run_id: str = _RUN_ID) -> tuple[FakeBeadsClient, str]:
    """The item in the tenant, stamped with `run_id`, naming an open current token."""
    append_work_item(path=_config(), item=_item())
    record_claim_stamp(path=_config(), work_item_id=_ITEM_ID, stamp=_stamp(run_id=run_id))
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    token = create_claim_token(client=client)
    metadata = dict(client.show_issue(issue_id=_ITEM_ID)["metadata"])
    metadata[CLAIM_TOKEN_METADATA_KEY] = token
    client.update_issue(issue_id=_ITEM_ID, metadata=metadata, names_claim_token=True)
    return client, token


def _snapshot(*, client: FakeBeadsClient) -> dict[str, object]:
    return copy.deepcopy(client.show_issue(issue_id=_ITEM_ID))


def _won_intent(*, client: FakeBeadsClient, token: str) -> object:
    """The intent `token` was won with, once the item names that win's successor."""
    won = json.loads(client.show_issue(issue_id=token)["close_reason"])
    named = client.show_issue(issue_id=_ITEM_ID)["metadata"][CLAIM_TOKEN_METADATA_KEY]
    assert (won["writer"], won["successor"]) == ("dispatcher-terminal", named)
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


def test_disabled_writes_are_the_valves_own_writers_and_a_close_is_preceded_by_none(
    tmp_path: Path,
) -> None:
    client, token = _seed()
    before = _snapshot(client=client)
    journal = _Journal()
    claim = _claim(repo=_repo(tmp_path=tmp_path, claim_tokens=False), journal=journal)
    complete = _Recorder()
    bounce = _Recorder()

    refusals = (
        claim.complete(write=complete),
        claim.hold_for_close(intent="close-completed"),
        claim.bounce(write=bounce),
    )

    assert refusals == (None, None, None)
    assert complete.calls == [{"path": _config(), "item_id": _ITEM_ID, "status": "acceptance"}]
    assert bounce.calls == [{"path": _config(), "item_id": _ITEM_ID, "status": "backlog"}]
    assert _snapshot(client=client) == before
    assert client.show_issue(issue_id=token)["status"] != "closed"
    assert journal.records == []


def test_an_enabled_completion_wins_the_token_and_reconciles_the_runs_it_disowned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, token = _seed()
    reconciled = _Recorder()
    monkeypatch.setattr(
        _dispatcher_completion_claims, "reconcile_after_lifecycle_write", reconciled
    )
    claim = _claim(repo=_repo(tmp_path=tmp_path, claim_tokens=True), journal=_Journal())

    refusal = claim.complete(write=lambda **_: pytest.fail("the unguarded writer ran"))

    assert refusal is None
    assert client.show_issue(issue_id=_ITEM_ID)["status"] == "acceptance"
    assert _won_intent(client=client, token=token) == "complete"
    assert reconciled.calls == [{"path": _config(), "item_id": _ITEM_ID, "status": "acceptance"}]


def test_an_enabled_hold_wins_the_token_and_leaves_the_status_for_the_close(
    tmp_path: Path,
) -> None:
    client, token = _seed()
    claim = _claim(repo=_repo(tmp_path=tmp_path, claim_tokens=True), journal=_Journal())

    client.update_issue(issue_id=_ITEM_ID, status="acceptance")

    refusal = claim.hold_for_close(intent="close-completed")

    assert refusal is None
    assert client.show_issue(issue_id=_ITEM_ID)["status"] == "acceptance"
    assert _won_intent(client=client, token=token) == "close-completed"


def test_an_enabled_bounce_wins_the_token_and_returns_the_item_to_backlog(
    tmp_path: Path,
) -> None:
    client, token = _seed()
    claim = _claim(repo=_repo(tmp_path=tmp_path, claim_tokens=True), journal=_Journal())

    refusal = claim.bounce(write=lambda **_: pytest.fail("the unguarded writer ran"))

    assert refusal is None
    assert client.show_issue(issue_id=_ITEM_ID)["status"] == "backlog"
    assert _won_intent(client=client, token=token) == "non-convergence-bounce"


@pytest.mark.parametrize("write", ["complete", "hold", "bounce"])
def test_an_enabled_write_that_loses_the_token_writes_nothing_and_journals_the_refusal(
    write: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, token = _seed()
    if write == "hold":
        client.update_issue(issue_id=_ITEM_ID, status="acceptance")
    before = _snapshot(client=client)
    _lose_the_token(client=client, token=token, monkeypatch=monkeypatch)
    journal = _Journal()
    claim = _claim(repo=_repo(tmp_path=tmp_path, claim_tokens=True), journal=journal)
    writes = {
        "complete": lambda: claim.complete(write=lambda **_: pytest.fail("unguarded")),
        "hold": lambda: claim.hold_for_close(intent="close-completed"),
        "bounce": lambda: claim.bounce(write=lambda **_: pytest.fail("unguarded")),
    }

    refusal = writes[write]()

    assert refusal == "claim-changed"
    assert _snapshot(client=client) == before
    assert [(record["stage"], record["reason"]) for record in journal.records] == [
        ("claim-write-refused", "claim-changed")
    ]


def _run(*, claim: CompletionClaim, write: str) -> str | None:
    if write == "complete":
        return claim.complete(write=lambda **_: pytest.fail("unguarded"))
    if write == "hold":
        return claim.hold_for_close(intent="close-completed")
    return claim.bounce(write=lambda **_: pytest.fail("unguarded"))


@pytest.mark.parametrize(
    ("write", "moved_to"),
    [("complete", "blocked"), ("bounce", "ready"), ("hold", "active")],
)
def test_a_write_whose_item_another_writer_already_moved_is_refused_without_a_contest(
    write: str, moved_to: str, tmp_path: Path
) -> None:
    """The valve decided on one status; the record now rests at another."""
    client, token = _seed()
    client.update_issue(issue_id=_ITEM_ID, status=moved_to)
    before = _snapshot(client=client)
    journal = _Journal()
    claim = _claim(repo=_repo(tmp_path=tmp_path, claim_tokens=True), journal=journal)

    refusal = _run(claim=claim, write=write)

    assert refusal == "claim-changed"
    assert _snapshot(client=client) == before
    # Refused on the decision, before the token was contested: it is still open.
    assert client.show_issue(issue_id=token)["status"] != "closed"
    assert [record["reason"] for record in journal.records] == ["claim-changed"]


def test_a_completion_of_a_claim_another_run_now_holds_is_refused_without_a_contest(
    tmp_path: Path,
) -> None:
    """Same status, same assignee, a different run: a newer dispatch owns the claim."""
    client, token = _seed(run_id="01ANOTHERRUN")
    before = _snapshot(client=client)
    claim = _claim(repo=_repo(tmp_path=tmp_path, claim_tokens=True), journal=_Journal())

    refusal = claim.complete(write=lambda **_: pytest.fail("unguarded"))

    assert refusal == "claim-changed"
    assert _snapshot(client=client) == before
    assert client.show_issue(issue_id=token)["status"] != "closed"
