"""Claim-token records never appear in a listing surface.

contracts.md, "Stranded claim release" -> "Claim tokens": "Token records MUST
be excluded from `list-work-items`, `next`, `needs-attention`'s work-item facts
and every child enumeration."

WHAT HOLDS THE EXCLUSION IS THE RECORD CLASS, and these cases are built to say
so rather than to pass by coincidence. A token minted by the protocol is a
no-history record, which no list surface returns. A bare token would also be
missed by most surfaces for unrelated reasons: it rests in `backlog`, carries
no Definition of Done and has no parent edge. So each case first DRESSES the
minted token as the work item it serves, copying that item's status,
description, labels, metadata and dependency edges onto it. After that the
token differs from a ready, dispatchable child of the epic in its id, its title
and its record class, and nothing else.

Each surface then has two cases. The token minted through `create_claim_token`
is absent. The same token minted as an ordinary issue is present, so the same
check raises: that control is what proves the check could have failed.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
)
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    CLAIM_TOKEN_METADATA_KEY,
    create_claim_token,
)
from livespec_orchestrator_beads_fabro.commands import needs_attention
from livespec_orchestrator_beads_fabro.commands._context_envelope import child_ids_of
from livespec_orchestrator_beads_fabro.commands.list_work_items import main as list_work_items
from livespec_orchestrator_beads_fabro.commands.needs_attention import build_attention
from livespec_orchestrator_beads_fabro.commands.next import main as next_candidates
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_EPIC_ID = "bd-ib-epic"
_ITEM_ID = "bd-ib-child"
_ORDINARY_TOKEN_ID = "bd-ib-ordinary-token"
_SPEC_HEADING = "## Effective acceptance criteria"
_DEFINITION_OF_DONE = (
    "## Definition of Done\n"
    "\n"
    "- The surface enumerates this item.\n"
    "\n"
    f"References: {_SPEC_HEADING}\n"
)

Check = Callable[[str, Path, pytest.CaptureFixture[str]], None]


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _tenant() -> FakeBeadsClient:
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    return client


def _work_item(*, id_: str, type_: str, status: str) -> WorkItem:
    return WorkItem(
        id=id_,
        type=type_,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        title=f"{id_} title",
        description=_DEFINITION_OF_DONE,
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-05T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A governed project whose tenant holds an epic and one ready child of it."""
    _ = (tmp_path / ".livespec.jsonc").write_text(
        json.dumps(
            {"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib", "fake": True}}}
        ),
        encoding="utf-8",
    )
    spec = tmp_path / "SPECIFICATION"
    spec.mkdir()
    _ = (spec / "contracts.md").write_text(
        f"# Contracts\n\n{_SPEC_HEADING}\n\nSome prose.\n", encoding="utf-8"
    )
    monkeypatch.setattr(needs_attention, "spec_next", lambda **_kwargs: None)
    monkeypatch.setattr(needs_attention, "currency_staleness_items", lambda **_kwargs: [])
    append_work_item(path=_config(), item=_work_item(id_=_EPIC_ID, type_="epic", status="backlog"))
    append_work_item(path=_config(), item=_work_item(id_=_ITEM_ID, type_="task", status="ready"))
    _tenant().add_dependency(from_id=_ITEM_ID, to_id=_EPIC_ID, edge_type="parent-child")
    return tmp_path


def _mint_token_dressed_as_the_item() -> str:
    """Mint the item's claim token, then make the record look like the item itself."""
    client = _tenant()
    token_id = create_claim_token(client=client)
    item = client.show_issue(issue_id=_ITEM_ID)
    client.update_issue(
        issue_id=token_id,
        status=item["status"],
        description=item["description"],
        add_labels=item["labels"],
        metadata=item["metadata"],
    )
    for edge in item["dependencies"]:
        client.add_dependency(from_id=token_id, to_id=edge["depends_on_id"], edge_type=edge["type"])
    client.update_issue(
        issue_id=_ITEM_ID, metadata={**item["metadata"], CLAIM_TOKEN_METADATA_KEY: token_id}
    )
    return token_id


def _mint_tokens_as_ordinary_issues(monkeypatch: pytest.MonkeyPatch) -> None:
    """The control: the protocol's create, minus the no-history record class."""
    client = _tenant()

    def _create_ordinary(*, title: str, description: str) -> str:
        return client.create_issue(
            draft=IssueDraft(
                issue_id=_ORDINARY_TOKEN_ID,
                issue_type="task",
                title=title,
                description=description,
                assignee=None,
                created_at="2026-11-05T00:00:00Z",
            )
        )

    monkeypatch.setattr(client, "create_no_history_issue", _create_ordinary)


def _check_list_work_items(
    token_id: str, project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert list_work_items(argv=["--json", "--project-root", str(project)]) == 0
    listed = {record["id"] for record in json.loads(capsys.readouterr().out)}
    assert listed >= {_EPIC_ID, _ITEM_ID}
    assert token_id not in listed


def _check_next(token_id: str, project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert next_candidates(argv=["--json", "--limit", "50", "--project-root", str(project)]) == 0
    ranked = [
        action["work_item_ref"] for action in json.loads(capsys.readouterr().out)["candidates"]
    ]
    assert _ITEM_ID in ranked
    assert token_id not in ranked


def _check_needs_attention_facts(
    token_id: str, project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _ = capsys
    facts = materialize_work_items(records=read_work_items(path=_config()))
    assert _ITEM_ID in facts
    assert token_id not in facts
    attention = build_attention(project_root=project, repo_name="repo", include_hygiene=False)
    assert f"impl:{_ITEM_ID}" in [row.id for row in attention]
    assert all(token_id not in row.id and row.source_ref.work_item != token_id for row in attention)


def _check_epic_children(token_id: str, project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _ = (token_id, project, capsys)
    client = _tenant()
    assert child_ids_of(records=client.list_issues(), epic_id=_EPIC_ID) == (_ITEM_ID,)
    assert [record["id"] for record in client.children(parent_id=_EPIC_ID)] == [_ITEM_ID]


def test_list_work_items_projection_holds_no_record_for_a_minted_claim_token(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    token_id = _mint_token_dressed_as_the_item()

    assert token_id in _tenant().no_history_issue_ids()
    _check_list_work_items(token_id, project, capsys)


def test_next_ranked_actions_name_no_claim_token_record(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _check_next(_mint_token_dressed_as_the_item(), project, capsys)


def test_needs_attention_work_item_facts_hold_no_claim_token_record(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _check_needs_attention_facts(_mint_token_dressed_as_the_item(), project, capsys)


def test_enumerating_an_epics_children_returns_the_child_and_no_claim_token_record(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _check_epic_children(_mint_token_dressed_as_the_item(), project, capsys)


@pytest.mark.parametrize(
    "check",
    [_check_list_work_items, _check_next, _check_needs_attention_facts, _check_epic_children],
)
def test_each_exclusion_fails_when_the_token_is_minted_as_an_ordinary_issue(
    check: Check,
    project: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mint_tokens_as_ordinary_issues(monkeypatch)
    token_id = _mint_token_dressed_as_the_item()

    assert token_id == _ORDINARY_TOKEN_ID
    assert _tenant().no_history_issue_ids() == ()
    with pytest.raises(AssertionError):
        check(token_id, project, capsys)
