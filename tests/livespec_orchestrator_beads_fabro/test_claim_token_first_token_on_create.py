"""A work item created after the claim-token cutover names its first claim token.

While `dispatcher.claim_tokens` is committed true every non-closed work item
names exactly one current token (`SPECIFICATION/contracts.md`, "Dispatcher
policy settings", the "Claim tokens" bullet). The migration pass names one on
each item that exists at the cutover. These cases pin the other half: an item
created LATER through the store's creation seam names its own first token in
the creating write, so no claim writer refuses it and no migration pass has to
run again for it.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
)
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    CLAIM_TOKEN_METADATA_KEY,
    change_claim,
)
from livespec_orchestrator_beads_fabro._store_mutations import append_work_item
from livespec_orchestrator_beads_fabro.commands._needs_attention_claim_tokens import (
    claim_token_missing_items,
)
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    LivespecConfigUnreadableError,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem, WorkItemStatus

_CUT_OVER = '{"claim_tokens": true}'
_ROW_PREFIX = "hygiene:claim-token-missing:"


def _config(project_root: Path) -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
        repo_root=project_root,
    )


def _tenant(project_root: Path) -> FakeBeadsClient:
    client = make_beads_client(config=_config(project_root))
    assert isinstance(client, FakeBeadsClient)
    return client


def _commit_dispatcher_block(project_root: Path, *, dispatcher: str) -> None:
    _ = (project_root / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": '
        '{"prefix": "bd", "bd_path": "bd", "fake": true}, "dispatcher": ' + dispatcher + "}}",
        encoding="utf-8",
    )


def _work_item(*, item_id: str, status: WorkItemStatus = "backlog") -> WorkItem:
    return WorkItem(
        id=item_id,
        type="task",
        status=status,
        title=f"{item_id} title",
        description="A work item filed after the cutover.",
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
        spec_commitment_hint=None,
    )


def _token_named_by(client: FakeBeadsClient, *, item_id: str) -> object:
    return client.show_issue(issue_id=item_id)["metadata"].get(CLAIM_TOKEN_METADATA_KEY)


def _open_token_ids(client: FakeBeadsClient) -> list[str]:
    return [
        token_id
        for token_id in client.no_history_issue_ids()
        if client.show_issue(issue_id=token_id)["status"] != "closed"
    ]


def test_item_created_after_cutover_names_exactly_one_open_token(tmp_path: Path) -> None:
    _commit_dispatcher_block(tmp_path, dispatcher=_CUT_OVER)
    client = _tenant(tmp_path)

    append_work_item(path=_config(tmp_path), item=_work_item(item_id="bd-first"))
    append_work_item(path=_config(tmp_path), item=_work_item(item_id="bd-second", status="ready"))

    named = [_token_named_by(client, item_id=item_id) for item_id in ("bd-first", "bd-second")]
    token_labels = [
        client.show_issue(issue_id=token_id).get("labels") for token_id in _open_token_ids(client)
    ]
    statuses = [
        client.show_issue(issue_id=item_id)["status"] for item_id in ("bd-first", "bd-second")
    ]
    assert set(named) == set(_open_token_ids(client))
    assert len(set(named)) == len(named)
    assert token_labels == [["claim-token"], ["claim-token"]]
    assert statuses == ["backlog", "ready"]
    assert client.show_issue(issue_id="bd-first")["metadata"]["rank"] == "a0"


def test_claim_changing_write_on_item_created_after_cutover_wins_its_token(
    tmp_path: Path,
) -> None:
    _commit_dispatcher_block(tmp_path, dispatcher=_CUT_OVER)
    client = _tenant(tmp_path)
    append_work_item(path=_config(tmp_path), item=_work_item(item_id="bd-later", status="ready"))
    first_token = _token_named_by(client, item_id="bd-later")

    result = change_claim(
        client=client,
        work_item_id="bd-later",
        writer="admission",
        intent="move-ready-to-active",
        claim_tokens=True,
        status="active",
        assignee="fabro",
    )

    item = client.show_issue(issue_id="bd-later")
    assert result.outcome == "applied"
    assert (item["status"], item["assignee"]) == ("active", "fabro")
    assert result.successor_token_id is not None
    assert item["metadata"][CLAIM_TOKEN_METADATA_KEY] == result.successor_token_id
    assert _open_token_ids(client) == [result.successor_token_id]
    assert first_token != result.successor_token_id


def test_missing_token_lane_lists_no_item_created_through_the_creation_seam(
    tmp_path: Path,
) -> None:
    _commit_dispatcher_block(tmp_path, dispatcher=_CUT_OVER)
    client = _tenant(tmp_path)
    for status in ("backlog", "ready", "pending-approval", "blocked", "active", "acceptance"):
        append_work_item(
            path=_config(tmp_path),
            item=_work_item(item_id=f"bd-seam-{status}", status=status),
        )
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id="bd-written-around-the-seam",
            issue_type="task",
            title="An item no creation seam wrote",
            description="A work item.",
            assignee=None,
            created_at="2026-11-06T00:00:00Z",
        )
    )

    rows = claim_token_missing_items(project_root=tmp_path, repo="repo", config=_config(tmp_path))

    assert [row.id for row in rows] == [f"{_ROW_PREFIX}bd-written-around-the-seam"]


@pytest.mark.parametrize("dispatcher", ['{"claim_tokens": false}', "{}"])
def test_before_cutover_a_created_item_names_no_token_and_none_is_minted(
    tmp_path: Path,
    dispatcher: str,
) -> None:
    _commit_dispatcher_block(tmp_path, dispatcher=dispatcher)
    client = _tenant(tmp_path)

    append_work_item(path=_config(tmp_path), item=_work_item(item_id="bd-before"))

    assert client.no_history_issue_ids() == ()
    assert client.show_issue(issue_id="bd-before")["metadata"] == {"rank": "a0"}


def test_no_committed_configuration_creates_an_item_naming_no_token(tmp_path: Path) -> None:
    client = _tenant(tmp_path)

    append_work_item(path=_config(tmp_path), item=_work_item(item_id="bd-unconfigured"))
    append_work_item(
        path=replace(_config(tmp_path), repo_root=None),
        item=_work_item(item_id="bd-no-repository"),
    )

    assert client.no_history_issue_ids() == ()
    assert client.show_issue(issue_id="bd-unconfigured")["metadata"] == {"rank": "a0"}
    assert client.show_issue(issue_id="bd-no-repository")["metadata"] == {"rank": "a0"}


def test_item_born_closed_after_cutover_names_no_token(tmp_path: Path) -> None:
    _commit_dispatcher_block(tmp_path, dispatcher=_CUT_OVER)
    client = _tenant(tmp_path)
    born_closed = replace(
        _work_item(item_id="bd-born-closed", status="done"),
        resolution="completed",
        reason="done at birth",
    )

    append_work_item(path=_config(tmp_path), item=born_closed)

    item = client.show_issue(issue_id="bd-born-closed")
    assert item["status"] == "closed"
    assert CLAIM_TOKEN_METADATA_KEY not in item["metadata"]
    assert client.no_history_issue_ids() == ()


def test_failed_create_after_cutover_leaves_no_open_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _commit_dispatcher_block(tmp_path, dispatcher=_CUT_OVER)
    client = _tenant(tmp_path)

    def _refuse(*, draft: IssueDraft) -> str:
        raise BeadsCommandError(command=f"bd create {draft.issue_id}", exit_code=1, stderr="boom")

    monkeypatch.setattr(client, "create_issue", _refuse)

    with pytest.raises(BeadsCommandError, match="bd create bd-refused"):
        append_work_item(path=_config(tmp_path), item=_work_item(item_id="bd-refused"))

    minted = client.no_history_issue_ids()
    assert len(minted) == 1
    assert _open_token_ids(client) == []
    assert client.list_issues() == []


def test_unreadable_setting_refuses_the_create_and_writes_nothing(tmp_path: Path) -> None:
    _commit_dispatcher_block(tmp_path, dispatcher='{"claim_tokens": "yes"}')
    client = _tenant(tmp_path)

    with pytest.raises(LivespecConfigUnreadableError, match="dispatcher.claim_tokens must be"):
        append_work_item(path=_config(tmp_path), item=_work_item(item_id="bd-unreadable"))

    assert client.list_issues() == []
    assert client.no_history_issue_ids() == ()
