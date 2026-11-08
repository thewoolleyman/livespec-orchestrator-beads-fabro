"""A reflection finding filed after the claim-token cutover names its first token.

While `dispatcher.claim_tokens` is committed true every non-closed work item
names exactly one current token (`SPECIFICATION/contracts.md`, "Dispatcher
policy settings", the "Claim tokens" bullet). The reflector files a finding
with its own create, outside the store's `append_work_item` seam, so these
cases pin that it names a first token in that creating write too. Without it
a reflection item filed after the cutover is refused by every claim writer
with `claim-token-missing` until the migration pass runs again.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
)
from livespec_orchestrator_beads_fabro._store_dispatch_claim import CLAIM_TOKEN_METADATA_KEY
from livespec_orchestrator_beads_fabro.commands._needs_attention_claim_tokens import (
    claim_token_missing_items,
)
from livespec_orchestrator_beads_fabro.commands._reflector_filing_store import file_new
from livespec_orchestrator_beads_fabro.commands._reflector_findings_parse import ReflectorFinding
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    LivespecConfigUnreadableError,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

_CUT_OVER = '{"claim_tokens": true}'
_FINGERPRINT = "deadbeefcafe"


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


def _finding() -> ReflectorFinding:
    return ReflectorFinding(
        category="stage-timeout",
        stage="fabro-run",
        severity="warn",
        subject="repeated stage timeouts on dispatch",
        detail="a recurring observation",
        occurrences=3,
        work_item_id=None,
        score=0.4,
        label="fail",
    )


def _file(client: FakeBeadsClient, *, project_root: Path) -> str:
    return file_new(
        finding=_finding(),
        fingerprint_hex=_FINGERPRINT,
        client=client,
        repo=project_root,
    )


def _open_token_ids(client: FakeBeadsClient) -> list[str]:
    return [
        token_id
        for token_id in client.no_history_issue_ids()
        if client.show_issue(issue_id=token_id)["status"] != "closed"
    ]


def test_reflection_item_filed_after_cutover_names_exactly_one_open_token(
    tmp_path: Path,
) -> None:
    _commit_dispatcher_block(tmp_path, dispatcher=_CUT_OVER)
    client = _tenant(tmp_path)

    issue_id = _file(client, project_root=tmp_path)

    item = client.show_issue(issue_id=issue_id)
    open_tokens = _open_token_ids(client)
    assert [item["metadata"].get(CLAIM_TOKEN_METADATA_KEY)] == open_tokens
    assert client.show_issue(issue_id=open_tokens[0]).get("labels") == ["claim-token"]
    assert item["status"] == "backlog"
    assert item["labels"] == ["reflection", f"fingerprint:{_FINGERPRINT}"]


def test_missing_token_lane_lists_no_reflection_item_filed_after_cutover(
    tmp_path: Path,
) -> None:
    _commit_dispatcher_block(tmp_path, dispatcher=_CUT_OVER)
    client = _tenant(tmp_path)

    issue_id = _file(client, project_root=tmp_path)

    rows = claim_token_missing_items(project_root=tmp_path, repo="repo", config=_config(tmp_path))
    assert [record["id"] for record in client.list_issues()] == [issue_id]
    assert [row.id for row in rows] == []


@pytest.mark.parametrize("dispatcher", ['{"claim_tokens": false}', "{}"])
def test_before_cutover_a_reflection_item_names_no_token_and_none_is_minted(
    tmp_path: Path,
    dispatcher: str,
) -> None:
    _commit_dispatcher_block(tmp_path, dispatcher=dispatcher)
    client = _tenant(tmp_path)

    issue_id = _file(client, project_root=tmp_path)

    assert client.no_history_issue_ids() == ()
    assert CLAIM_TOKEN_METADATA_KEY not in client.show_issue(issue_id=issue_id)["metadata"]


def test_failed_reflection_create_after_cutover_leaves_no_open_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _commit_dispatcher_block(tmp_path, dispatcher=_CUT_OVER)
    client = _tenant(tmp_path)

    def _refuse(*, draft: IssueDraft) -> str:
        raise BeadsCommandError(command=f"bd create {draft.title}", exit_code=1, stderr="boom")

    monkeypatch.setattr(client, "create_issue", _refuse)

    with pytest.raises(BeadsCommandError, match="bd create .reflection. stage-timeout"):
        _ = _file(client, project_root=tmp_path)

    assert len(client.no_history_issue_ids()) == 1
    assert _open_token_ids(client) == []
    assert client.list_issues() == []


def test_unreadable_setting_refuses_the_reflection_create_and_writes_nothing(
    tmp_path: Path,
) -> None:
    _commit_dispatcher_block(tmp_path, dispatcher='{"claim_tokens": "yes"}')
    client = _tenant(tmp_path)

    with pytest.raises(LivespecConfigUnreadableError, match="dispatcher.claim_tokens must be"):
        _ = _file(client, project_root=tmp_path)

    assert client.list_issues() == []
    assert client.no_history_issue_ids() == ()
