"""Admission's size-decomposition route to `backlog`, one value of the key at a time.

An oversized item is refused at a dispatch entry and routed to `backlog`. That
route changes the item's status and admission makes it, so it is a
claim-changing write (`SPECIFICATION/contracts.md`, "Claim tokens").

- `dispatcher.claim_tokens` false or unset, or a store configuration naming no
  repository: the store route is called exactly as its caller always called
  it. These cases record the call and assert its keyword arguments.
- true, won: the item lands at `backlog` under the won token, in a write that
  sends the status and the successor and nothing else; the reason comment
  follows.
- true, lost: nothing is written to the item and no comment claims a route
  that never happened. The dispatch entry still refuses the item, at a stage
  of its own.

The two entry points that make the route, the dispatch-entry size gate and the
groom door, are driven here as well, against the in-memory tenant.
"""

from __future__ import annotations

import copy
import json
from dataclasses import replace
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
from livespec_orchestrator_beads_fabro._store_factory_size_gate import (
    route_factory_size_decomposition,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_guard import (
    TRANSITION_OBSERVATIONS,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_size_gate import (
    route_factory_size_dispatch_entry,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_groom_door import (
    GROOM_DOOR_SIZE_DECOMPOSITION,
    GroomDoorRefusal,
    groom_dispatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_size_route import (
    SIZE_DECOMPOSITION_CLAIM_REFUSED_STAGE,
    SIZE_DECOMPOSITION_STAGE,
    route_size_decomposition,
    routed_size_refusal,
)
from livespec_orchestrator_beads_fabro.store import append_work_item, read_work_item_comments
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem, WorkItemStatus

_ITEM_ID = "bd-oversized"
_GROOM_VARIANT = "groom-cut"
_GROOM_DIR = ".fabro/workflows/groom-cut"
_CEILING = 2
_REASON = "adopted assertion-count ceiling 2; the item states 3"
_ANOTHER_WRITER = "another writer won this token"
_REFUSED_STAGE = "claim-write-refused"


@pytest.fixture(autouse=True)
def _fresh_tenant() -> object:
    reset_fake_singleton()
    TRANSITION_OBSERVATIONS.clear()
    yield
    TRANSITION_OBSERVATIONS.clear()
    reset_fake_singleton()


def _repo(*, tmp_path: Path, claim_tokens: bool) -> Path:
    """A target adopting a ceiling of two assertions and registering a groom variant."""
    target = tmp_path / _GROOM_DIR
    target.mkdir(parents=True)
    _ = (target / "workflow.toml").write_text(
        '[workflow]\ngraph = "workflow.fabro"\n\n[run.inputs]\nworkflow_kind = "groom"\n',
        encoding="utf-8",
    )
    dispatcher: dict[str, object] = {
        "adopted_assertion_count_ceiling": _CEILING,
        "workflows": {_GROOM_VARIANT: _GROOM_DIR},
    }
    if claim_tokens:
        dispatcher["claim_tokens"] = True
    _ = (tmp_path / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {
                        "tenant": "livespec-impl-beads",
                        "prefix": "livespec-impl-beads",
                        "server_user": "livespec-impl-beads",
                        "database": "livespec-impl-beads",
                        "bd_path": "bd",
                        "fake": True,
                    },
                    "dispatcher": dispatcher,
                }
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


def _config(*, repo: Path | None) -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
        repo_root=repo,
    )


def _journal(*, repo: Path) -> JournalFile:
    path = repo / "journal.jsonl"
    _ = path.write_text("", encoding="utf-8")
    return JournalFile(path=path)


def _stages(*, journal: JournalFile) -> list[object]:
    return [
        json.loads(line).get("stage")
        for line in journal.path.read_text(encoding="utf-8").splitlines()
    ]


def _oversized(*, status: WorkItemStatus = "ready") -> WorkItem:
    """An item stating three assertions, one more than the adopted ceiling."""
    bullets = "\n".join(f"- The product satisfies assertion {index}." for index in range(3))
    return WorkItem(
        id=_ITEM_ID,
        type="feature",
        status=status,
        title="An item above the adopted ceiling",
        description=(
            "## Definition of Done\n\n"
            f"{bullets}\n\n"
            "References: ## Scenario 153 — An adopted assertion ceiling requires "
            "an attributed exception without waiving other gates\n"
        ),
        origin="freeform",
        gap_id=None,
        rank="a4",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-06T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        spec_commitment_hint=None,
        admission_policy="auto",
    )


def _seed(*, item: WorkItem, repo: Path | None) -> tuple[FakeBeadsClient, str]:
    """File the item and give it an open current token."""
    config = _config(repo=repo)
    append_work_item(path=config, item=item)
    client = make_beads_client(config=config)
    assert isinstance(client, FakeBeadsClient)
    token = create_claim_token(client=client)
    metadata = dict(client.show_issue(issue_id=_ITEM_ID)["metadata"])
    metadata[CLAIM_TOKEN_METADATA_KEY] = token
    client.update_issue(issue_id=_ITEM_ID, metadata=metadata)
    return client, token


def _snapshot(*, client: FakeBeadsClient) -> dict[str, object]:
    return copy.deepcopy(client.show_issue(issue_id=_ITEM_ID))


def _comments(*, repo: Path | None) -> list[str]:
    return [
        comment.text
        for comment in read_work_item_comments(path=_config(repo=repo), work_item_id=_ITEM_ID)
    ]


def _won(*, client: FakeBeadsClient, token: str) -> tuple[object, object, bool]:
    """The writer and intent `token` was won with, and whether the item names its successor."""
    reason = json.loads(client.show_issue(issue_id=token)["close_reason"])
    named = client.show_issue(issue_id=_ITEM_ID)["metadata"][CLAIM_TOKEN_METADATA_KEY]
    return reason["writer"], reason["intent"], reason["successor"] == named


def _lose_the_token(
    *, client: FakeBeadsClient, token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    close = client.close_issue_without_verdict

    def _raced(*, issue_id: str, reason: str) -> None:
        if issue_id == token:
            close(issue_id=issue_id, reason=_ANOTHER_WRITER)
        close(issue_id=issue_id, reason=reason)

    monkeypatch.setattr(client, "close_issue_without_verdict", _raced)


class _Recorder:
    """The store route, recording the keyword arguments of each call."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def __call__(self, **kwargs: object) -> None:
        self.calls.append(kwargs)


def _route(*, repo: Path | None, config_repo: Path | None, journal: JournalFile) -> str | None:
    return route_size_decomposition(
        repo=repo,
        path=_config(repo=config_repo),
        work_item_id=_ITEM_ID,
        status="ready",
        reason=_REASON,
        journal=journal,
        route=route_factory_size_decomposition,
    )


@pytest.mark.parametrize("names_a_repository", [True, False])
def test_a_disabled_route_is_the_store_route_called_as_its_caller_always_called_it(
    *, names_a_repository: bool, tmp_path: Path
) -> None:
    """Key unset, or no repository to read a key from: the one call master makes."""
    repo = _repo(tmp_path=tmp_path, claim_tokens=False)
    route = _Recorder()

    refusal = route_size_decomposition(
        repo=repo if names_a_repository else None,
        path=_config(repo=repo),
        work_item_id=_ITEM_ID,
        status="ready",
        reason=_REASON,
        journal=_journal(repo=repo),
        route=route,
    )

    assert refusal is None
    assert route.calls == [
        {"path": _config(repo=repo), "work_item_id": _ITEM_ID, "reason": _REASON}
    ]


def test_a_disabled_route_writes_backlog_and_the_reason_without_touching_any_token(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path, claim_tokens=False)
    client, token = _seed(item=_oversized(), repo=repo)

    refusal = _route(repo=repo, config_repo=repo, journal=_journal(repo=repo))

    record = client.show_issue(issue_id=_ITEM_ID)
    assert refusal is None
    assert record["status"] == "backlog"
    assert _comments(repo=repo) == [_REASON]
    assert record["metadata"][CLAIM_TOKEN_METADATA_KEY] == token
    assert client.show_issue(issue_id=token)["status"] != "closed"


def test_an_enabled_route_lands_backlog_and_the_successor_in_one_write_then_comments(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path, claim_tokens=True)
    client, token = _seed(item=_oversized(), repo=repo)
    before = _snapshot(client=client)

    refusal = _route(repo=repo, config_repo=repo, journal=_journal(repo=repo))

    after = _snapshot(client=client)
    assert refusal is None
    assert _won(client=client, token=token) == ("dispatcher-admission", "size-decomposition", True)
    assert _comments(repo=repo) == [_REASON]
    # The token-carrying write sent the status and the successor, and nothing else.
    assert after["status"] == "backlog"
    after["status"] = before["status"]
    after["metadata"][CLAIM_TOKEN_METADATA_KEY] = token
    assert after == before


def test_an_enabled_route_that_loses_the_token_writes_nothing_and_comments_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path, claim_tokens=True)
    client, token = _seed(item=_oversized(), repo=repo)
    before = _snapshot(client=client)
    _lose_the_token(client=client, token=token, monkeypatch=monkeypatch)
    journal = _journal(repo=repo)

    refusal = _route(repo=repo, config_repo=repo, journal=journal)

    assert refusal == "claim-changed"
    assert _snapshot(client=client) == before
    assert _comments(repo=repo) == []
    assert _stages(journal=journal) == [_REFUSED_STAGE]


def test_a_routed_entry_refusal_reports_the_route_at_the_size_decomposition_stage(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path, claim_tokens=True)
    item = _oversized()
    client, _ = _seed(item=item, repo=repo)
    journal = _journal(repo=repo)

    outcome = routed_size_refusal(
        path=_config(repo=repo),
        item=item,
        reason=_REASON,
        journal=journal,
        route=route_factory_size_decomposition,
    )

    assert (outcome.status, outcome.stage, outcome.detail) == (
        "failed",
        SIZE_DECOMPOSITION_STAGE,
        _REASON,
    )
    assert client.show_issue(issue_id=_ITEM_ID)["status"] == "backlog"
    assert _stages(journal=journal) == ["outcome"]


def test_the_dispatch_entry_gate_routes_an_oversized_item_under_the_won_token(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path, claim_tokens=True)
    item = _oversized()
    client, token = _seed(item=item, repo=repo)

    refused = route_factory_size_dispatch_entry(
        adopted_ceiling=_CEILING,
        path_factory=lambda: _config(repo=repo),
        items=(item,),
        journal=_journal(repo=repo),
    )

    assert [(outcome.work_item_id, outcome.stage) for outcome in refused] == [
        (_ITEM_ID, SIZE_DECOMPOSITION_STAGE)
    ]
    assert client.show_issue(issue_id=_ITEM_ID)["status"] == "backlog"
    assert _won(client=client, token=token) == ("dispatcher-admission", "size-decomposition", True)
    assert len(_comments(repo=repo)) == 1


def test_the_dispatch_entry_gate_that_loses_the_token_refuses_without_routing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The item is still oversized, so it is still refused; it is just not moved."""
    repo = _repo(tmp_path=tmp_path, claim_tokens=True)
    item = _oversized()
    client, token = _seed(item=item, repo=repo)
    before = _snapshot(client=client)
    _lose_the_token(client=client, token=token, monkeypatch=monkeypatch)
    journal = _journal(repo=repo)

    refused = route_factory_size_dispatch_entry(
        adopted_ceiling=_CEILING,
        path_factory=lambda: _config(repo=repo),
        items=(item,),
        journal=journal,
    )

    [outcome] = refused
    assert (outcome.status, outcome.stage) == ("failed", SIZE_DECOMPOSITION_CLAIM_REFUSED_STAGE)
    assert "claim-changed" in outcome.detail
    assert _snapshot(client=client) == before
    assert _comments(repo=repo) == []
    assert _stages(journal=journal) == [_REFUSED_STAGE, "outcome"]


def test_the_groom_door_routes_an_oversized_item_under_the_won_token(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path, claim_tokens=True)
    item = _oversized(status="backlog")
    client, token = _seed(item=item, repo=repo)

    door = groom_dispatch(repo=repo, item=item, variant=_GROOM_VARIANT, journal=_journal(repo=repo))

    assert isinstance(door, GroomDoorRefusal)
    assert door.cause == GROOM_DOOR_SIZE_DECOMPOSITION
    assert "claim-token" not in door.detail
    assert client.show_issue(issue_id=_ITEM_ID)["status"] == "backlog"
    assert _won(client=client, token=token) == ("dispatcher-admission", "size-decomposition", True)
    assert _comments(repo=repo) == [door.detail]


def test_the_groom_door_that_loses_the_token_refuses_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path, claim_tokens=True)
    item = _oversized(status="backlog")
    client, token = _seed(item=item, repo=repo)
    before = _snapshot(client=client)
    _lose_the_token(client=client, token=token, monkeypatch=monkeypatch)
    journal = _journal(repo=repo)

    door = groom_dispatch(repo=repo, item=item, variant=_GROOM_VARIANT, journal=journal)

    assert isinstance(door, GroomDoorRefusal)
    assert door.cause == GROOM_DOOR_SIZE_DECOMPOSITION
    assert "claim-changed" in door.detail
    assert _snapshot(client=client) == before
    assert _comments(repo=repo) == []
    assert _REFUSED_STAGE in _stages(journal=journal)


def test_a_disabled_groom_door_still_routes_an_oversized_item_as_it_always_did(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path, claim_tokens=False)
    item = replace(_oversized(), status="backlog")
    client, token = _seed(item=item, repo=repo)

    door = groom_dispatch(repo=repo, item=item, variant=_GROOM_VARIANT, journal=_journal(repo=repo))

    assert isinstance(door, GroomDoorRefusal)
    assert _comments(repo=repo) == [door.detail]
    assert client.show_issue(issue_id=token)["status"] != "closed"


def test_an_enabled_route_of_an_item_another_writer_already_moved_is_refused_uncontested(
    tmp_path: Path,
) -> None:
    """The gate judged a `ready` item; one that has since been admitted is not its to move."""
    repo = _repo(tmp_path=tmp_path, claim_tokens=True)
    client, token = _seed(item=_oversized(), repo=repo)
    client.update_issue(issue_id=_ITEM_ID, status="active", assignee="fabro")
    before = _snapshot(client=client)
    journal = _journal(repo=repo)

    refusal = _route(repo=repo, config_repo=repo, journal=journal)

    assert refusal == "claim-changed"
    assert _snapshot(client=client) == before
    assert _comments(repo=repo) == []
    assert client.show_issue(issue_id=token)["status"] != "closed"
    assert _stages(journal=journal) == [_REFUSED_STAGE]


def test_two_dispatch_entry_gates_deciding_on_one_read_route_the_item_exactly_once(
    tmp_path: Path,
) -> None:
    """Sequential, not racing: the second gate finds the item already at `backlog`."""
    repo = _repo(tmp_path=tmp_path, claim_tokens=True)
    item = _oversized()
    client, token = _seed(item=item, repo=repo)
    journal = _journal(repo=repo)

    stages = [
        route_factory_size_dispatch_entry(
            adopted_ceiling=_CEILING,
            path_factory=lambda: _config(repo=repo),
            items=(item,),
            journal=journal,
        )[0].stage
        for _ in range(2)
    ]

    first_successor = json.loads(client.show_issue(issue_id=token)["close_reason"])["successor"]
    record = client.show_issue(issue_id=_ITEM_ID)
    assert stages == [SIZE_DECOMPOSITION_STAGE, SIZE_DECOMPOSITION_CLAIM_REFUSED_STAGE]
    assert record["status"] == "backlog"
    assert record["metadata"][CLAIM_TOKEN_METADATA_KEY] == first_successor
    assert client.show_issue(issue_id=first_successor)["status"] != "closed"
    assert len(_comments(repo=repo)) == 1
