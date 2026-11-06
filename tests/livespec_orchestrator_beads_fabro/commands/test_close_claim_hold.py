"""The hold a session-performed close takes: a no-op before the cutover, a typed refusal after."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro._store_dispatch_claim import CLAIM_TOKEN_METADATA_KEY
from livespec_orchestrator_beads_fabro.commands._close_claim_hold import hold_before_close
from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_guard import (
    TRANSITION_OBSERVATIONS,
)
from livespec_orchestrator_beads_fabro.errors import ClaimWriteRefusedError
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-holdbeforeclose"
_ANOTHER_WRITER = "another writer won this token"
_CONNECTION = {"prefix": "bd-ib", "fake": True}


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    TRANSITION_OBSERVATIONS.clear()
    yield
    TRANSITION_OBSERVATIONS.clear()
    reset_fake_singleton()


def _config(*, tmp_path: Path, claim_tokens: object) -> StoreConfig:
    repo = tmp_path / "repo"
    repo.mkdir()
    # `None` commits no key at all, which the writer reads as `false`.
    dispatcher = {} if claim_tokens is None else {"claim_tokens": claim_tokens}
    block = {"connection": _CONNECTION, "dispatcher": dispatcher}
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": block}), encoding="utf-8"
    )
    return resolve_store_config(cwd=repo, work_items_arg=None)


def _file(*, config: StoreConfig) -> FakeBeadsClient:
    append_work_item(
        path=config,
        item=WorkItem(
            id=_ITEM_ID,
            type="task",
            status="ready",
            title="An item a session closes",
            description="Close it.",
            origin="freeform",
            gap_id=None,
            rank="a0",
            assignee=None,
            depends_on=(),
            captured_at="2026-11-06T00:00:00Z",
            resolution=None,
            reason=None,
            audit=None,
            superseded_by=None,
        ),
    )
    client = make_beads_client(config=config)
    assert isinstance(client, FakeBeadsClient)
    return client


def _named(*, client: FakeBeadsClient) -> str | None:
    metadata = client.show_issue(issue_id=_ITEM_ID)["metadata"]
    return metadata.get(CLAIM_TOKEN_METADATA_KEY)


def test_a_hold_that_wins_names_the_successor_and_changes_nothing_else(tmp_path: Path) -> None:
    config = _config(tmp_path=tmp_path, claim_tokens=True)
    client = _file(config=config)
    token = _named(client=client)
    assert token is not None

    hold_before_close(path=config, item_id=_ITEM_ID, intent="close-it", status="ready")

    reason = json.loads(client.show_issue(issue_id=token)["close_reason"])
    assert (reason["writer"], reason["intent"]) == ("human-valve", "close-it")
    assert reason["successor"] == _named(client=client)
    assert client.show_issue(issue_id=_ITEM_ID)["status"] == "ready"


def test_a_hold_that_loses_raises_the_typed_refusal_naming_the_outcome(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path=tmp_path, claim_tokens=True)
    client = _file(config=config)
    token = _named(client=client)
    close = client.close_issue_without_verdict

    def _raced(*, issue_id: str, reason: str) -> None:
        if issue_id == token:
            close(issue_id=issue_id, reason=_ANOTHER_WRITER)
        close(issue_id=issue_id, reason=reason)

    monkeypatch.setattr(client, "close_issue_without_verdict", _raced)

    with pytest.raises(ClaimWriteRefusedError) as refused:
        hold_before_close(path=config, item_id=_ITEM_ID, intent="close-it", status="ready")

    assert (refused.value.item_id, refused.value.outcome) == (_ITEM_ID, "claim-changed")
    assert str(refused.value) == refused.value.detail
    assert refused.value.detail == (
        "human-valve (close-it) refused: the claim-token protocol reported claim-changed; "
        f"the status and claim of {_ITEM_ID} were not written."
    )
    assert _named(client=client) == token


def test_a_hold_bound_to_a_status_the_item_left_refuses_as_claim_changed(tmp_path: Path) -> None:
    config = _config(tmp_path=tmp_path, claim_tokens=True)
    client = _file(config=config)
    token = _named(client=client)

    with pytest.raises(ClaimWriteRefusedError) as refused:
        hold_before_close(path=config, item_id=_ITEM_ID, intent="close-it", status="backlog")

    assert refused.value.outcome == "claim-changed"
    assert client.show_issue(issue_id=token or "")["status"] != "closed"


@pytest.mark.parametrize("claim_tokens", [False, None])
def test_a_hold_before_the_cutover_writes_nothing(tmp_path: Path, claim_tokens: object) -> None:
    config = _config(tmp_path=tmp_path, claim_tokens=claim_tokens)
    client = _file(config=config)
    before = client.show_issue(issue_id=_ITEM_ID)

    hold_before_close(
        path=config, item_id=_ITEM_ID, intent="close-it", status="ready", repo=config.repo_root
    )

    assert client.show_issue(issue_id=_ITEM_ID) == before
    assert _named(client=client) is None
