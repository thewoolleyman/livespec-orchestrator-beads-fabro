"""The `driver-dispatch` door under the claim-token cutover: its journal and its race.

`driver-dispatch:<id>` moves a host-only `ready` item to `active` and journals
the dispatch. Its eligibility rule excludes a race with the Dispatcher, which
refuses exactly the host-only set. It does not exclude a race with another
operator verb: a `move` valve can be pressed on the same `ready` item. So while
`dispatcher.claim_tokens` is `true` the door is a claim writer like the valves
(`SPECIFICATION/contracts.md`, "Claim tokens"): it writes only after winning the
item's current token.

What is particular to this door is the journal record, and that is what these
cases bind. The record says a dispatch happened. A press that loses the token
has dispatched nothing, so it must leave no record, and a press that wins must
leave exactly one. Each race runs the REAL second writer to completion at the
instant the first closes the token, so both have read the same open token.
The last two cases are the same pair without overlap: one press decided on the
`ready` item, the other finished, and the first then wrote and journaled nothing.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    CLAIM_TOKEN_METADATA_KEY,
    create_claim_token,
)
from livespec_orchestrator_beads_fabro.commands import _drive_driver_dispatch
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_guard import (
    TRANSITION_OBSERVATIONS,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import InvokerIdentity
from livespec_orchestrator_beads_fabro.commands._drive_policy_valves import move_item
from livespec_orchestrator_beads_fabro.commands.drive import run_action
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-claimdoor"
_DISPATCH = f"driver-dispatch:{_ITEM_ID}"
_MOVE = f"move:{_ITEM_ID}:backlog"
_ANOTHER_WRITER = "another writer won this token"


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    TRANSITION_OBSERVATIONS.clear()
    yield
    TRANSITION_OBSERVATIONS.clear()
    reset_fake_singleton()


def _config(*, repo_root: Path | None = None) -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
        repo_root=repo_root,
    )


def _repo(*, tmp_path: Path) -> Path:
    """A repository whose committed configuration has cut over to claim tokens."""
    repo = tmp_path / "repo"
    repo.mkdir()
    block = {
        "connection": {
            "tenant": "livespec-impl-beads",
            "prefix": "bd-ib",
            "server_user": "livespec-impl-beads",
            "database": "livespec-impl-beads",
            "bd_path": "bd",
            "fake": True,
        },
        "dispatcher": {"claim_tokens": True},
    }
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": block}), encoding="utf-8"
    )
    return repo


def _seed() -> tuple[FakeBeadsClient, str]:
    """A host-only `ready` item naming an open current token."""
    item = WorkItem(
        id=_ITEM_ID,
        type="task",
        status="ready",
        title="Rebuild the host commit hook",
        description="d",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-06T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        factory_safety="mutates-host-machinery",
    )
    append_work_item(path=_config(), item=item)
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    token = create_claim_token(client=client)
    metadata = dict(client.show_issue(issue_id=_ITEM_ID)["metadata"])
    metadata[CLAIM_TOKEN_METADATA_KEY] = token
    client.update_issue(issue_id=_ITEM_ID, metadata=metadata, names_claim_token=True)
    return client, token


def _press(*, repo: Path, action_id: str) -> dict[str, object]:
    return run_action(
        repo=repo,
        action_id=action_id,
        identity=InvokerIdentity(invoker="human:cw", invoker_source="flag"),
    )


def _dispatches(*, repo: Path) -> list[dict[str, object]]:
    """The driver-dispatch records the journal file holds."""
    path = repo / "tmp" / "fabro-dispatch-journal.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    records = [json.loads(line) for line in lines]
    return [record for record in records if record.get("stage") == "human-valve-driver-dispatch"]


def _won(*, client: FakeBeadsClient, token: str) -> dict[str, str]:
    record = client.show_issue(issue_id=token)
    assert record["status"] == "closed", "no writer contested the item's current token"
    return json.loads(record["close_reason"])


def _race(
    *,
    client: FakeBeadsClient,
    token: str,
    rival: Callable[[], dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> list[dict[str, object]]:
    """Run `rival` to completion at the instant the first writer closes `token`."""
    close = client.close_issue_without_verdict
    finished: list[dict[str, object]] = []
    started: list[str] = []

    def _closing(*, issue_id: str, reason: str) -> None:
        if issue_id == token and not started:
            started.append(issue_id)
            finished.append(rival())
        close(issue_id=issue_id, reason=reason)

    monkeypatch.setattr(client, "close_issue_without_verdict", _closing)
    return finished


def test_a_won_dispatch_is_journaled_once_and_names_the_transition(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    client, token = _seed()

    result = _press(repo=repo, action_id=_DISPATCH)

    won = _won(client=client, token=token)
    record = client.show_issue(issue_id=_ITEM_ID)
    [journaled] = _dispatches(repo=repo)
    assert result["status"] == "green"
    assert (won["writer"], won["intent"]) == ("human-valve", "driver-dispatch")
    assert won["successor"] == record["metadata"][CLAIM_TOKEN_METADATA_KEY]
    assert record["status"] == "active"
    assert (journaled["work_item_id"], journaled["to_status"]) == (_ITEM_ID, "active")


def test_a_dispatch_that_loses_its_token_journals_no_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The record says a dispatch happened, so a press that wrote nothing leaves none."""
    repo = _repo(tmp_path=tmp_path)
    client, token = _seed()
    before = copy.deepcopy(client.show_issue(issue_id=_ITEM_ID))
    close = client.close_issue_without_verdict

    def _raced(*, issue_id: str, reason: str) -> None:
        if issue_id == token:
            close(issue_id=issue_id, reason=_ANOTHER_WRITER)
        close(issue_id=issue_id, reason=reason)

    monkeypatch.setattr(client, "close_issue_without_verdict", _raced)

    result = _press(repo=repo, action_id=_DISPATCH)

    assert (result["status"], result["domain_error"]) == ("failed", "claim-changed")
    assert "journal" not in result
    assert client.show_issue(issue_id=_ITEM_ID) == before
    assert _dispatches(repo=repo) == []


def test_a_move_wins_the_race_and_the_dispatch_is_neither_written_nor_journaled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both read the `ready` item's open token, and the `move` closes it first."""
    repo = _repo(tmp_path=tmp_path)
    client, token = _seed()
    moved = _race(
        client=client,
        token=token,
        rival=lambda: _press(repo=repo, action_id=_MOVE),
        monkeypatch=monkeypatch,
    )

    dispatched = _press(repo=repo, action_id=_DISPATCH)

    won = _won(client=client, token=token)
    record = client.show_issue(issue_id=_ITEM_ID)
    assert [result["status"] for result in moved] == ["green"]
    assert (dispatched["status"], dispatched["domain_error"]) == ("failed", "claim-changed")
    assert (won["writer"], won["intent"]) == ("human-valve", "move:backlog")
    assert won["successor"] == record["metadata"][CLAIM_TOKEN_METADATA_KEY]
    assert record["status"] == "backlog"
    assert _dispatches(repo=repo) == []


def test_the_dispatch_wins_the_race_and_the_move_stands_down(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other way round: the item is `active` and journaled, and the `move` wrote nothing."""
    repo = _repo(tmp_path=tmp_path)
    client, token = _seed()
    dispatched = _race(
        client=client,
        token=token,
        rival=lambda: _press(repo=repo, action_id=_DISPATCH),
        monkeypatch=monkeypatch,
    )

    moved = _press(repo=repo, action_id=_MOVE)

    won = _won(client=client, token=token)
    record = client.show_issue(issue_id=_ITEM_ID)
    assert [result["status"] for result in dispatched] == ["green"]
    assert (moved["status"], moved["domain_error"]) == ("failed", "claim-changed")
    assert (won["writer"], won["intent"]) == ("human-valve", "driver-dispatch")
    assert won["successor"] == record["metadata"][CLAIM_TOKEN_METADATA_KEY]
    assert record["status"] == "active"
    assert len(_dispatches(repo=repo)) == 1


def _first_writer_stands(*, client: FakeBeadsClient, token: str) -> dict[str, str]:
    """The reason the first writer won `token` with, its successor still named and open."""
    won = _won(client=client, token=token)
    named = client.show_issue(issue_id=_ITEM_ID)["metadata"][CLAIM_TOKEN_METADATA_KEY]
    assert won["successor"] == named
    assert client.show_issue(issue_id=named)["status"] != "closed"
    return won


def test_a_move_decided_before_the_dispatch_finished_writes_nothing_after_it(
    tmp_path: Path,
) -> None:
    """No overlap: the move read the `ready` item, the door opened, then the move wrote."""
    repo = _repo(tmp_path=tmp_path)
    client, token = _seed()
    as_the_valve_read_it = materialize_work_items(records=read_work_items(path=_config()))[_ITEM_ID]
    dispatched = _press(repo=repo, action_id=_DISPATCH)

    moved = move_item(
        config=_config(repo_root=repo),
        item=as_the_valve_read_it,
        aid=_MOVE,
        target_status="backlog",
    )

    won = _first_writer_stands(client=client, token=token)
    assert dispatched["status"] == "green"
    assert (moved["status"], moved["domain_error"]) == ("failed", "claim-changed")
    assert won["intent"] == "driver-dispatch"
    assert client.show_issue(issue_id=_ITEM_ID)["status"] == "active"
    assert len(_dispatches(repo=repo)) == 1


def test_a_dispatch_decided_before_a_move_finished_writes_and_journals_nothing_after_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other way round: the door found the item eligible, then the move took it away.

    The door resolves its driver session after its eligibility check and before
    its write, so the move is run to completion from there.
    """
    repo = _repo(tmp_path=tmp_path)
    client, token = _seed()
    resolve = _drive_driver_dispatch.driver_session_reference
    moved: list[dict[str, object]] = []

    def _move_then_resolve(**session: object) -> object:
        moved.append(_press(repo=repo, action_id=_MOVE))
        return resolve(**session)

    monkeypatch.setattr(_drive_driver_dispatch, "driver_session_reference", _move_then_resolve)

    dispatched = _press(repo=repo, action_id=_DISPATCH)

    won = _first_writer_stands(client=client, token=token)
    assert [press["status"] for press in moved] == ["green"]
    assert (dispatched["status"], dispatched["domain_error"]) == ("failed", "claim-changed")
    assert won["intent"] == "move:backlog"
    assert client.show_issue(issue_id=_ITEM_ID)["status"] == "backlog"
    assert _dispatches(repo=repo) == []
