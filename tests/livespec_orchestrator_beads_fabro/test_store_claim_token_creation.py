"""The creation seam's first claim token: the setting read and the creating write.

`test_claim_token_first_token_on_create` pins what a filed item looks like
after the cutover. The cases here pin the two primitives underneath it: which
committed settings read as cut over, and what one create writes, including the
token a refused create must not leave open.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, IssueDraft
from livespec_orchestrator_beads_fabro._store_claim_token_creation import (
    claim_tokens_committed,
    create_issue_naming_first_claim_token,
)
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    CLAIM_TOKEN_METADATA_KEY,
    change_claim,
)
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsMappingError,
    LivespecConfigUnreadableError,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

_PLUGIN_BLOCK = '{"livespec-orchestrator-beads-fabro": '


def _config(repo_root: Path | None) -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
        repo_root=repo_root,
    )


def _draft(*, item_id: str = "bd-new") -> IssueDraft:
    return IssueDraft(
        issue_id=item_id,
        issue_type="task",
        title=f"{item_id} title",
        description="A work item.",
        assignee=None,
        created_at="2026-11-06T00:00:00Z",
        labels=["origin:freeform"],
        metadata={"rank": "a0"},
    )


def _statuses(client: FakeBeadsClient) -> list[object]:
    return [
        client.show_issue(issue_id=token_id)["status"] for token_id in client.no_history_issue_ids()
    ]


def test_descriptor_naming_no_repository_reads_as_not_cut_over() -> None:
    assert claim_tokens_committed(path=_config(None)) is False


def test_repository_committing_no_configuration_reads_as_not_cut_over(tmp_path: Path) -> None:
    assert claim_tokens_committed(path=_config(tmp_path)) is False


@pytest.mark.parametrize(
    "plugin_block",
    ["{}", '{"dispatcher": {}}', '{"dispatcher": {"claim_tokens": false}}'],
)
def test_setting_committed_false_or_left_unset_reads_as_not_cut_over(
    tmp_path: Path,
    plugin_block: str,
) -> None:
    _ = (tmp_path / ".livespec.jsonc").write_text(
        _PLUGIN_BLOCK + plugin_block + "}", encoding="utf-8"
    )

    assert claim_tokens_committed(path=_config(tmp_path)) is False


def test_setting_committed_true_reads_as_cut_over(tmp_path: Path) -> None:
    _ = (tmp_path / ".livespec.jsonc").write_text(
        _PLUGIN_BLOCK + '{"dispatcher": {"claim_tokens": true}}}', encoding="utf-8"
    )

    assert claim_tokens_committed(path=_config(tmp_path)) is True


@pytest.mark.parametrize(
    ("committed", "detail"),
    [
        (
            _PLUGIN_BLOCK + '{"dispatcher": {"claim_tokens": 1}}}',
            "dispatcher.claim_tokens must be a boolean; got 1",
        ),
        (
            _PLUGIN_BLOCK + '{"dispatcher": []}}',
            ".livespec.jsonc livespec-orchestrator-beads-fabro.dispatcher is not an object",
        ),
    ],
)
def test_unreadable_setting_raises_rather_than_reading_as_false(
    tmp_path: Path,
    committed: str,
    detail: str,
) -> None:
    _ = (tmp_path / ".livespec.jsonc").write_text(committed, encoding="utf-8")

    with pytest.raises(LivespecConfigUnreadableError) as raised:
        _ = claim_tokens_committed(path=_config(tmp_path))

    assert raised.value.detail == detail


def test_create_not_naming_a_token_is_the_bare_create() -> None:
    client = FakeBeadsClient()
    draft = _draft()

    create_issue_naming_first_claim_token(client=client, draft=draft, names_token=False)

    assert client.show_issue(issue_id="bd-new")["metadata"] == {"rank": "a0"}
    assert client.no_history_issue_ids() == ()


def test_create_naming_a_token_writes_it_in_the_creating_write() -> None:
    client = FakeBeadsClient()
    draft = _draft()
    written: list[dict[str, object]] = []
    original_create = client.create_issue

    def _record(*, draft: IssueDraft) -> str:
        written.append(dict(draft.metadata))
        return original_create(draft=draft)

    client.create_issue = _record

    create_issue_naming_first_claim_token(client=client, draft=draft, names_token=True)

    (token_id,) = client.no_history_issue_ids()
    item = client.show_issue(issue_id="bd-new")
    assert written == [{"rank": "a0", CLAIM_TOKEN_METADATA_KEY: token_id}]
    assert item["metadata"] == {"rank": "a0", CLAIM_TOKEN_METADATA_KEY: token_id}
    assert item["labels"] == ["origin:freeform"]
    assert draft.metadata == {"rank": "a0"}
    assert client.show_issue(issue_id=token_id)["labels"] == ["claim-token"]
    assert _statuses(client) == ["backlog"]


@pytest.mark.parametrize(
    "refusal",
    [
        BeadsCommandError(command="bd create bd-new", exit_code=1, stderr="boom"),
        BeadsMappingError(record_id="bd-new", detail="boom"),
    ],
)
def test_refused_create_discards_its_token_and_raises_the_refusal(
    refusal: BeadsCommandError | BeadsMappingError,
) -> None:
    client = FakeBeadsClient()

    def _refuse(**_kwargs: object) -> str:
        raise refusal

    client.create_issue = _refuse

    with pytest.raises(type(refusal)) as raised:
        create_issue_naming_first_claim_token(client=client, draft=_draft(), names_token=True)

    assert raised.value is refusal
    assert _statuses(client) == ["closed"]
    assert client.list_issues() == []


def test_discard_reason_has_the_shape_the_claim_protocol_gives_a_losing_successor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeBeadsClient()
    create_issue_naming_first_claim_token(client=client, draft=_draft(), names_token=True)
    (current,) = client.no_history_issue_ids()
    original_close = client.close_issue_without_verdict

    def _lose(*, issue_id: str, reason: str) -> None:
        if issue_id == current:
            original_close(issue_id=issue_id, reason="other writer won")
        original_close(issue_id=issue_id, reason=reason)

    monkeypatch.setattr(client, "close_issue_without_verdict", _lose)
    loser = change_claim(
        client=client,
        work_item_id="bd-new",
        writer="work-item-create",
        intent="any",
        claim_tokens=True,
        status="ready",
    )
    (protocol_discard,) = [
        client.show_issue(issue_id=token_id)["close_reason"]
        for token_id in client.no_history_issue_ids()
        if token_id != current
    ]
    monkeypatch.undo()

    def _refuse(*, draft: IssueDraft) -> str:
        raise BeadsCommandError(command=f"bd create {draft.issue_id}", exit_code=1, stderr="boom")

    client.create_issue = _refuse
    with pytest.raises(BeadsCommandError):
        create_issue_naming_first_claim_token(
            client=client, draft=_draft(item_id="bd-refused"), names_token=True
        )
    creation_discard = client.show_issue(issue_id=client.no_history_issue_ids()[-1])["close_reason"]

    assert loser.outcome == "claim-changed"
    assert creation_discard == protocol_discard
    assert creation_discard == '{"kind":"claim-token-discard","writer":"work-item-create"}'
