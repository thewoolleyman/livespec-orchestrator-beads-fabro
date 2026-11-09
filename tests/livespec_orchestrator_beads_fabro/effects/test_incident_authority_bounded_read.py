"""A current incident authority read does not re-read the whole retained token chain.

The reader starts at the item's recorded head hint (the latest closed token the
transition writer named) and walks forward to the open successor, so the records
it reads are bounded by the hint's lag rather than by the number of generations.
The hint is a start point, never authority: an absent, stale or foreign hint
reads the same authority the full walk from genesis reads.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    BeadsRecord,
    FakeBeadsClient,
    IssueDraft,
)
from livespec_orchestrator_beads_fabro._incident_authority_payload import (
    GENESIS_MARKER,
    TOKEN_TITLE,
    TRANSITION_MARKER,
)
from livespec_orchestrator_beads_fabro.effects._incident_authority_reader import (
    read_authority,
    read_incident_head,
)
from livespec_orchestrator_beads_fabro.incident_authority import (
    AuthorityRefusal,
    IncidentReading,
)

_REPOSITORY = "owner/repository"
_ITEM = "incident-1"
_OTHER_ITEM = "incident-2"
_HINT_KEY = "incident_authority_head"
_QUERY_KEYS = ("attempt_id", "phase", "operation_id", "generation", "owner")


def _recording(*, client: FakeBeadsClient, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record every ledger read so a test can state how many a read cost."""
    reads: list[str] = []
    show_issue = client.show_issue
    list_comments = client.list_comments

    def counted_show(*, issue_id: str) -> BeadsRecord:
        reads.append(issue_id)
        return show_issue(issue_id=issue_id)

    def counted_comments(*, issue_id: str) -> list[BeadsRecord]:
        reads.append(f"comments:{issue_id}")
        return list_comments(issue_id=issue_id)

    monkeypatch.setattr(client, "show_issue", counted_show)
    monkeypatch.setattr(client, "list_comments", counted_comments)
    return reads


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _attempt(*, item: str, generation: int) -> dict[str, Any]:
    return dict(
        repository=_REPOSITORY,
        item_id=item,
        attempt_id=f"attempt-{generation}",
        phase="repair",
        operation_id=f"operation-{item}-{generation}",
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


def _chain(*, client: FakeBeadsClient, item: str, generations: int) -> list[str]:
    """Build one retained chain; returns its tokens, root first, the open one last."""
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=item,
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
        issue_id=item,
        body=GENESIS_MARKER
        + _canonical(dict(schema=1, repository=_REPOSITORY, item_id=item, root_token_id=token)),
    )
    for generation in range(1, generations + 1):
        successor = client.create_no_history_issue(title=TOKEN_TITLE, description="token")
        payload = dict(
            schema=1,
            repository=_REPOSITORY,
            item_id=item,
            prior_token_id=token,
            next_token_id=successor,
            attempt=_attempt(item=item, generation=generation),
        )
        client.close_issue_without_verdict(
            issue_id=token, reason=TRANSITION_MARKER + _canonical(payload)
        )
        token = successor
        tokens.append(token)
    return tokens


def _hint(*, client: FakeBeadsClient, item: str, token: str) -> None:
    client.update_issue(issue_id=item, metadata={_HINT_KEY: token})


def _query(*, item: str, generation: int) -> dict[str, object]:
    row = _attempt(item=item, generation=generation)
    return {key: value for key, value in row.items() if key in _QUERY_KEYS}


def _current(*, client: FakeBeadsClient, item: str, generation: int) -> IncidentReading:
    reading = read_authority(
        client=client,
        repository=_REPOSITORY,
        item_id=item,
        query=_query(item=item, generation=generation),
        historical=False,
    )
    assert isinstance(reading, IncidentReading)
    return reading


def _hinted(
    *, generations: int, monkeypatch: pytest.MonkeyPatch
) -> tuple[FakeBeadsClient, list[str], list[str]]:
    client = FakeBeadsClient()
    tokens = _chain(client=client, item=_ITEM, generations=generations)
    _hint(client=client, item=_ITEM, token=tokens[-2])
    return client, tokens, _recording(client=client, monkeypatch=monkeypatch)


def _cost(*, generations: int, monkeypatch: pytest.MonkeyPatch) -> int:
    client, _tokens, reads = _hinted(generations=generations, monkeypatch=monkeypatch)
    _ = _current(client=client, item=_ITEM, generation=generations)
    return len(reads)


def test_a_current_read_at_thirty_generations_costs_at_most_twice_the_first_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _cost(generations=30, monkeypatch=monkeypatch) <= 2 * _cost(
        generations=1, monkeypatch=monkeypatch
    )


def test_a_current_read_reads_a_bounded_number_of_token_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, tokens, reads = _hinted(generations=30, monkeypatch=monkeypatch)
    reading = _current(client=client, item=_ITEM, generation=30)
    token_reads = [read for read in reads if read in tokens]
    assert len(token_reads) <= 3
    assert reading.current_token_id == tokens[-1]
    assert reading.committed_token_id == tokens[-2]
    assert reading.is_current


def test_the_incident_head_read_reads_a_bounded_number_of_token_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, tokens, reads = _hinted(generations=30, monkeypatch=monkeypatch)
    head = read_incident_head(client=client, repository=_REPOSITORY, item_id=_ITEM)
    assert isinstance(head, IncidentReading)
    assert len([read for read in reads if read in tokens]) <= 3
    assert head.attempt.generation == 30
    assert head.current_token_id == tokens[-1]


def test_a_stale_hint_walks_forward_to_the_same_head_the_full_walk_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeBeadsClient()
    tokens = _chain(client=client, item=_ITEM, generations=30)
    full = _current(client=client, item=_ITEM, generation=30)
    _hint(client=client, item=_ITEM, token=tokens[27])
    reads = _recording(client=client, monkeypatch=monkeypatch)
    hinted = _current(client=client, item=_ITEM, generation=30)
    assert hinted.attempt == full.attempt
    assert hinted.current_token_id == full.current_token_id
    assert hinted.committed_token_id == full.committed_token_id
    assert len([read for read in reads if read in tokens]) <= 6


def test_a_hint_naming_the_open_token_reads_the_full_walk() -> None:
    client = FakeBeadsClient()
    tokens = _chain(client=client, item=_ITEM, generations=5)
    _hint(client=client, item=_ITEM, token=tokens[-1])
    assert _current(client=client, item=_ITEM, generation=5).committed_token_id == tokens[-2]


def test_a_hint_naming_another_items_token_reads_the_full_walk() -> None:
    client = FakeBeadsClient()
    tokens = _chain(client=client, item=_ITEM, generations=5)
    foreign = _chain(client=client, item=_OTHER_ITEM, generations=3)
    _hint(client=client, item=_ITEM, token=foreign[0])
    reading = _current(client=client, item=_ITEM, generation=5)
    assert reading.committed_token_id == tokens[-2]
    assert reading.attempt.item_id == _ITEM


def test_a_hint_cannot_make_a_non_head_generation_current() -> None:
    client = FakeBeadsClient()
    tokens = _chain(client=client, item=_ITEM, generations=5)
    _hint(client=client, item=_ITEM, token=tokens[1])
    refusal = read_authority(
        client=client,
        repository=_REPOSITORY,
        item_id=_ITEM,
        query=_query(item=_ITEM, generation=2),
        historical=False,
    )
    assert isinstance(refusal, AuthorityRefusal)
    assert refusal.code == "incident-authority-identity-mismatch"


def test_a_historical_read_still_finds_the_first_generation_through_a_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, tokens, _reads = _hinted(generations=30, monkeypatch=monkeypatch)
    reading = read_authority(
        client=client,
        repository=_REPOSITORY,
        item_id=_ITEM,
        query=_query(item=_ITEM, generation=1),
        historical=True,
    )
    assert isinstance(reading, IncidentReading)
    assert reading.committed_token_id == tokens[0]
    assert not reading.is_current
    assert len(reading.operation_ids) == 30
