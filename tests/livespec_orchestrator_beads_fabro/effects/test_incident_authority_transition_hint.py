"""The transition writer records the head hint, and never trusts a hinted read for reuse."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any, cast

import pytest
from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, IssueDraft
from livespec_orchestrator_beads_fabro._incident_authority_payload import (
    GENESIS_MARKER,
    TOKEN_TITLE,
    TRANSITION_MARKER,
)
from livespec_orchestrator_beads_fabro.errors import BeadsCommandError
from livespec_orchestrator_beads_fabro.incident_authority import (
    AuthorityRefusal,
    IncidentReading,
    commit_incident_transition,
    read_incident_authority,
)

_REPOSITORY = "owner/repository"
_ITEM = "incident-1"
_HINT_KEY = "incident_authority_head"
_QUERY_KEYS = ("attempt_id", "phase", "operation_id", "generation", "owner")


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _attempt(*, generation: int) -> dict[str, Any]:
    return dict(
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


def _chain(*, generations: int) -> tuple[FakeBeadsClient, list[str]]:
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
    client.add_comment(
        issue_id=_ITEM,
        body=GENESIS_MARKER
        + _canonical(dict(schema=1, repository=_REPOSITORY, item_id=_ITEM, root_token_id=token)),
    )
    for generation in range(1, generations + 1):
        successor = client.create_no_history_issue(title=TOKEN_TITLE, description="token")
        payload = dict(
            schema=1,
            repository=_REPOSITORY,
            item_id=_ITEM,
            prior_token_id=token,
            next_token_id=successor,
            attempt=_attempt(generation=generation),
        )
        client.close_issue_without_verdict(
            issue_id=token, reason=TRANSITION_MARKER + _canonical(payload)
        )
        token = successor
        tokens.append(token)
    return client, tokens


def _current(*, client: FakeBeadsClient, generation: int) -> IncidentReading:
    row = _attempt(generation=generation)
    reading = read_incident_authority(
        client=client,
        repository=_REPOSITORY,
        item_id=_ITEM,
        query={key: row[key] for key in _QUERY_KEYS},
    )
    assert isinstance(reading, IncidentReading)
    return reading


def _hint(*, client: FakeBeadsClient) -> object:
    metadata = client.show_issue(issue_id=_ITEM).get("metadata")
    assert isinstance(metadata, dict)
    return cast("dict[str, object]", metadata).get(_HINT_KEY)


def test_a_committed_transition_records_the_token_it_closed_as_the_head_hint() -> None:
    client, tokens = _chain(generations=2)
    observed = _current(client=client, generation=2)
    committed = commit_incident_transition(
        client=client,
        observed=observed,
        successor=replace(observed.attempt, generation=3, operation_id="operation-3"),
    )
    assert isinstance(committed, IncidentReading)
    assert _hint(client=client) == tokens[-1]
    assert committed.attempt.generation == 3
    assert committed.is_current


def test_a_hinted_read_cannot_hide_a_reused_operation_from_the_writer() -> None:
    client, tokens = _chain(generations=3)
    client.update_issue(issue_id=_ITEM, metadata={_HINT_KEY: tokens[2]})
    observed = _current(client=client, generation=3)
    refusal = commit_incident_transition(
        client=client,
        observed=observed,
        successor=replace(observed.attempt, generation=4, operation_id="operation-1"),
    )
    assert isinstance(refusal, AuthorityRefusal)
    assert refusal.code == "incident-transition-operation-reused"
    assert len(client.no_history_issue_ids()) == len(tokens)


def test_a_lost_hint_write_leaves_the_committed_transition_a_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _tokens = _chain(generations=2)
    observed = _current(client=client, generation=2)

    def lose(**_kwargs: object) -> None:
        raise BeadsCommandError(command="bd update", exit_code=1, stderr="lost")

    monkeypatch.setattr(client, "update_issue", lose)
    committed = commit_incident_transition(
        client=client,
        observed=observed,
        successor=replace(observed.attempt, generation=3, operation_id="operation-3"),
    )
    assert isinstance(committed, IncidentReading)
    assert committed.attempt.generation == 3
