"""The size-decomposition route to `backlog` under the claim-token cutover.

An item whose Definition of Done exceeds the adopted assertion ceiling is moved
to `backlog` with the reason as a comment. Two of the writers
`SPECIFICATION/contracts.md` ("Claim tokens") names make that move: intake, at
capture, and the `approve` valve, in place of the approval. It changes the
item's status, so while `dispatcher.claim_tokens` is `true` each of them makes
it only after winning the item's current token.

The route is two effects, the status and then the comment. A writer that loses
the token must leave neither: a reason on an item that was never moved would
tell its reader the item is in `backlog` for decomposition when it is not.
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
    create_claim_token,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_guard import (
    TRANSITION_OBSERVATIONS,
)
from livespec_orchestrator_beads_fabro.commands._drive_valves import run_human_valve_action
from livespec_orchestrator_beads_fabro.intake_dor import (
    DefinitionOfReadyChecklist,
    apply_intake_dor,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io

_ITEM_ID = "bd-ib-claimsize"
_CEILING = 2
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
    """A cut-over repository that has adopted an assertion ceiling of two."""
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
        "dispatcher": {"claim_tokens": True, "adopted_assertion_count_ceiling": _CEILING},
    }
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": block}), encoding="utf-8"
    )
    return repo


def _seed() -> tuple[FakeBeadsClient, str]:
    """An item one assertion over the ceiling, awaiting approval, naming an open token."""
    bullets = "\n".join(
        f"- The product satisfies assertion {index}." for index in range(_CEILING + 1)
    )
    item = WorkItem(
        id=_ITEM_ID,
        type="feature",
        status="pending-approval",
        title="An oversized slice",
        description=f"## Definition of Done\n\n{bullets}\n\nReferences: ## Some heading\n",
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
        admission_policy="auto",
    )
    append_work_item(path=_config(), item=item)
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    token = create_claim_token(client=client)
    metadata = dict(client.show_issue(issue_id=_ITEM_ID)["metadata"])
    metadata[CLAIM_TOKEN_METADATA_KEY] = token
    client.update_issue(issue_id=_ITEM_ID, metadata=metadata, names_claim_token=True)
    return client, token


def _lose_the_token(
    *, client: FakeBeadsClient, token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    close = client.close_issue_without_verdict

    def _raced(*, issue_id: str, reason: str) -> None:
        if issue_id == token:
            close(issue_id=issue_id, reason=_ANOTHER_WRITER)
        close(issue_id=issue_id, reason=reason)

    monkeypatch.setattr(client, "close_issue_without_verdict", _raced)


def _snapshot(*, client: FakeBeadsClient) -> dict[str, object]:
    return copy.deepcopy(client.show_issue(issue_id=_ITEM_ID))


def _reasons(*, client: FakeBeadsClient) -> list[str]:
    """The size-decomposition reasons recorded on the item."""
    return [
        comment["text"]
        for comment in client.list_comments(issue_id=_ITEM_ID)
        if "size_justification" in comment["text"]
    ]


def _won(*, client: FakeBeadsClient, token: str) -> dict[str, str]:
    record = client.show_issue(issue_id=token)
    assert record["status"] == "closed", "no writer contested the item's current token"
    return json.loads(record["close_reason"])


def _intake(*, repo: Path) -> object:
    return apply_intake_dor(
        path=_config(repo_root=repo),
        item_id=_ITEM_ID,
        checklist=DefinitionOfReadyChecklist(
            single_coherent_done=True,
            autonomously_verifiable=True,
            autonomy_tiered=True,
            dependency_linked=True,
            repo_targeted=True,
            above_floor=True,
        ),
    )


def _approve(*, repo: Path) -> dict[str, object]:
    return run_human_valve_action(repo=repo, action_id=f"approve:{_ITEM_ID}")


def test_intake_routes_an_oversized_item_to_backlog_under_the_won_token(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    client, token = _seed()

    result = _intake(repo=repo)

    won = _won(client=client, token=token)
    record = client.show_issue(issue_id=_ITEM_ID)
    assert unsafe_perform_io(result.unwrap()) == "backlog"
    assert (won["writer"], won["intent"]) == ("intake", "size-decomposition")
    assert won["successor"] == record["metadata"][CLAIM_TOKEN_METADATA_KEY]
    assert record["status"] == "backlog"
    assert "intake:triaged" in record["labels"]
    assert len(_reasons(client=client)) == 1


def test_intake_that_loses_the_token_leaves_an_oversized_item_unrouted_and_unmarked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    client, token = _seed()
    before = _snapshot(client=client)
    _lose_the_token(client=client, token=token, monkeypatch=monkeypatch)

    result = _intake(repo=repo)

    assert not is_successful(result)
    refused = unsafe_perform_io(result.failure())
    assert (refused.work_item_id, refused.writer) == (_ITEM_ID, "intake")
    assert (refused.intent, refused.outcome) == ("size-decomposition", "claim-changed")
    assert _snapshot(client=client) == before
    assert _reasons(client=client) == []


def test_approve_routes_an_oversized_item_to_backlog_under_the_won_token(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    client, token = _seed()

    result = _approve(repo=repo)

    won = _won(client=client, token=token)
    record = client.show_issue(issue_id=_ITEM_ID)
    assert (result["status"], result["domain_error"]) == ("failed", "size-decomposition")
    assert result["target_status"] == "backlog"
    assert (won["writer"], won["intent"]) == ("human-valve", "approve:size-decomposition")
    assert won["successor"] == record["metadata"][CLAIM_TOKEN_METADATA_KEY]
    assert record["status"] == "backlog"
    assert _reasons(client=client) == [result["summary"]]


def test_approve_that_loses_the_token_reports_claim_changed_and_not_a_backlog_move(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    client, token = _seed()
    before = _snapshot(client=client)
    _lose_the_token(client=client, token=token, monkeypatch=monkeypatch)

    result = _approve(repo=repo)

    assert (result["status"], result["domain_error"]) == ("failed", "claim-changed")
    assert "target_status" not in result
    assert _snapshot(client=client) == before
    assert _reasons(client=client) == []
