"""The retained-history read at the ledger boundary: ordered attempts, named refusals, no fallback."""

from __future__ import annotations

import json
from typing import Any

from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, IssueDraft
from livespec_orchestrator_beads_fabro._incident_authority_payload import (
    GENESIS_MARKER,
    TOKEN_TITLE,
    TRANSITION_MARKER,
)
from livespec_orchestrator_beads_fabro.effects._incident_authority_reader import read_history
from livespec_orchestrator_beads_fabro.errors import BeadsConnectionError
from livespec_orchestrator_beads_fabro.incident_authority import AuthorityRefusal

_REPOSITORY = "owner/repository"
_ITEM = "incident-1"


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _attempt(*, generation: int, phase: str) -> dict[str, Any]:
    return dict(
        repository=_REPOSITORY,
        item_id=_ITEM,
        attempt_id=f"attempt-{generation}",
        phase=phase,
        operation_id=f"operation-{generation}",
        generation=generation,
        owner="operator:alice",
        base="a" * 40,
        head="b" * 40,
        pr_number=73,
        landed_commits=["c" * 40],
        landed_trees=["d" * 40],
        original_paths=["app.py"],
        deferred_work=["normal-factory-proof"],
        repayment_required=True,
    )


def _item(client: FakeBeadsClient) -> None:
    client.create_issue(
        draft=IssueDraft(
            issue_id=_ITEM,
            issue_type="bug",
            title="incident",
            description="behavior",
            assignee=None,
            created_at="2026-11-04T00:00:00Z",
        )
    )


def _chain(*, phases: tuple[str, ...]) -> FakeBeadsClient:
    client = FakeBeadsClient()
    _item(client)
    token = client.create_no_history_issue(title=TOKEN_TITLE, description="token")
    client.add_comment(
        issue_id=_ITEM,
        body=GENESIS_MARKER
        + _canonical(dict(schema=1, repository=_REPOSITORY, item_id=_ITEM, root_token_id=token)),
    )
    for generation, phase in enumerate(phases, start=1):
        successor = client.create_no_history_issue(title=TOKEN_TITLE, description="token")
        payload = dict(
            schema=1,
            repository=_REPOSITORY,
            item_id=_ITEM,
            prior_token_id=token,
            next_token_id=successor,
            attempt=_attempt(generation=generation, phase=phase),
        )
        client.close_issue_without_verdict(
            issue_id=token, reason=TRANSITION_MARKER + _canonical(payload)
        )
        token = successor
    return client


class _Outage:
    """A tenant whose first read fails the way a lost connection does."""

    def show_issue(self, *, issue_id: str) -> dict[str, object]:
        raise BeadsConnectionError(detail=f"connection refused reading {issue_id}")


def test_history_returns_every_committed_attempt_oldest_first() -> None:
    client = _chain(phases=("repair", "master-observation", "repayment-admission"))
    history = read_history(client=client, repository=_REPOSITORY, item_id=_ITEM)
    assert not isinstance(history, AuthorityRefusal)
    assert [attempt.phase for attempt in history] == [
        "repair",
        "master-observation",
        "repayment-admission",
    ]
    assert [attempt.generation for attempt in history] == [1, 2, 3]
    assert read_history(client=_chain(phases=()), repository=_REPOSITORY, item_id=_ITEM) == ()


def test_an_item_with_no_genesis_refuses_by_name() -> None:
    client = FakeBeadsClient()
    _item(client)
    refusal = read_history(client=client, repository=_REPOSITORY, item_id=_ITEM)
    assert isinstance(refusal, AuthorityRefusal)
    assert refusal.code == "incident-authority-missing"


def test_a_broken_chain_refuses_by_name() -> None:
    client = _chain(phases=("repair",))
    open_token = next(
        token
        for token in client.no_history_issue_ids()
        if client.show_issue(issue_id=token).get("status") == "backlog"
    )
    client.update_issue(issue_id=open_token, status="ready")
    refusal = read_history(client=client, repository=_REPOSITORY, item_id=_ITEM)
    assert isinstance(refusal, AuthorityRefusal)
    assert refusal.code == "incident-authority-invalid-token-state"


def test_a_tenant_outage_is_unavailable_never_an_empty_history() -> None:
    refusal = read_history(client=_Outage(), repository=_REPOSITORY, item_id=_ITEM)  # type: ignore[arg-type]
    assert isinstance(refusal, AuthorityRefusal)
    assert refusal.code == "incident-authority-unavailable"
    assert "connection refused" in refusal.detail
