"""The incident head read names every refusal the chain can raise, hinted or not."""

from __future__ import annotations

import json
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, IssueDraft
from livespec_orchestrator_beads_fabro._incident_authority_payload import (
    GENESIS_MARKER,
    HEAD_HINT_KEY,
    TOKEN_TITLE,
    TRANSITION_MARKER,
)
from livespec_orchestrator_beads_fabro.effects import _incident_authority_chain as chain_module
from livespec_orchestrator_beads_fabro.effects._incident_authority_reader import (
    read_incident_head,
)
from livespec_orchestrator_beads_fabro.errors import BeadsConnectionError
from livespec_orchestrator_beads_fabro.incident_authority import (
    AuthorityRefusal,
    IncidentReading,
)

_REPOSITORY = "owner/repository"
_ITEM = "incident-1"


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _attempt(*, generation: int, carrier: object = None) -> dict[str, Any]:
    row: dict[str, Any] = dict(
        repository=_REPOSITORY,
        item_id=_ITEM,
        attempt_id=f"attempt-{generation}",
        phase="repair",
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
    if carrier is not None:
        row["carrier"] = carrier
    return row


def _chain(
    *, attempts: list[dict[str, Any]], armed: bool = True
) -> tuple[FakeBeadsClient, list[str]]:
    client = FakeBeadsClient()
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=_ITEM,
            issue_type="bug",
            title="incident",
            description="behavior",
            assignee=None,
            created_at="2026-11-04T00:00:00Z",
        )
    )
    token = client.create_no_history_issue(title=TOKEN_TITLE, description="token")
    tokens = [token]
    if armed:
        client.add_comment(
            issue_id=_ITEM,
            body=GENESIS_MARKER
            + _canonical(
                dict(schema=1, repository=_REPOSITORY, item_id=_ITEM, root_token_id=token)
            ),
        )
    for attempt in attempts:
        successor = client.create_no_history_issue(title=TOKEN_TITLE, description="token")
        payload = dict(
            schema=1,
            repository=_REPOSITORY,
            item_id=_ITEM,
            prior_token_id=token,
            next_token_id=successor,
            attempt=attempt,
        )
        client.close_issue_without_verdict(
            issue_id=token, reason=TRANSITION_MARKER + _canonical(payload)
        )
        token = successor
        tokens.append(token)
    return client, tokens


def _head(client: FakeBeadsClient) -> IncidentReading | AuthorityRefusal:
    return read_incident_head(client=client, repository=_REPOSITORY, item_id=_ITEM)


def test_an_unarmed_item_has_no_head() -> None:
    client, _tokens = _chain(attempts=[], armed=False)
    refusal = _head(client)
    assert isinstance(refusal, AuthorityRefusal)
    assert refusal.code == "incident-authority-missing"


def test_a_chain_with_no_transition_has_no_head() -> None:
    client, _tokens = _chain(attempts=[])
    refusal = _head(client)
    assert isinstance(refusal, AuthorityRefusal)
    assert refusal.code == "incident-authority-identity-mismatch"


def test_a_chain_naming_an_unsupported_carrier_refuses_by_name() -> None:
    client, _tokens = _chain(attempts=[_attempt(generation=1, carrier={"state": "future"})])
    refusal = _head(client)
    assert isinstance(refusal, AuthorityRefusal)
    assert refusal.code == "incident-carrier-unsupported"


def test_a_hinted_head_whose_walk_cannot_continue_refuses_by_name() -> None:
    client, tokens = _chain(attempts=[_attempt(generation=1), _attempt(generation=2)])
    client.update_issue(issue_id=_ITEM, metadata={HEAD_HINT_KEY: tokens[1]})
    client.update_issue(issue_id=tokens[2], status="ready")
    refusal = _head(client)
    assert isinstance(refusal, AuthorityRefusal)
    assert refusal.code == "incident-authority-invalid-token-state"


def test_the_walk_refuses_when_the_chain_outgrows_its_token_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _tokens = _chain(attempts=[_attempt(generation=1), _attempt(generation=2)])
    monkeypatch.setattr(chain_module, "_MAX_TOKENS", 1)
    refusal = _head(client)
    assert isinstance(refusal, AuthorityRefusal)
    assert refusal.code == "incident-authority-history-limit"


def test_a_tenant_outage_is_unavailable_never_a_missing_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _tokens = _chain(attempts=[_attempt(generation=1)])

    def refuse(*, issue_id: str) -> dict[str, object]:
        raise BeadsConnectionError(detail=f"connection refused reading {issue_id}")

    monkeypatch.setattr(client, "show_issue", refuse)
    refusal = _head(client)
    assert isinstance(refusal, AuthorityRefusal)
    assert refusal.code == "incident-authority-unavailable"
