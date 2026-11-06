"""Whole-repository incident history is located by genesis and authenticated by the chain."""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-y7ryj3
from __future__ import annotations

import json
from typing import Any

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
from livespec_orchestrator_beads_fabro.errors import BeadsCommandError
from livespec_orchestrator_beads_fabro.incident_authority import (
    AuthorityRefusal,
    IncidentReading,
    read_incident_history,
)

_REPOSITORY = "owner/repository"
_ITEM = "incident-1"
_UNKNOWN_ROOT = "elsewhere"


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _item(client: FakeBeadsClient, *, item: str) -> None:
    client.create_issue(
        draft=IssueDraft(
            issue_id=item,
            issue_type="bug",
            title="incident",
            description="behavior",
            assignee=None,
            created_at="2026-11-04T00:00:00Z",
        )
    )


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
        pr_number=7,
        landed_commits=["b" * 40],
        landed_trees=["c" * 40],
        original_paths=["app.py"],
        deferred_work=["normal-factory-proof"],
        repayment_required=True,
    )


def _ledger(
    *,
    client: FakeBeadsClient | None = None,
    phases: tuple[str, ...] = ("repair", "repayment-ready"),
) -> FakeBeadsClient:
    client = client if client is not None else FakeBeadsClient()
    _item(client, item=_ITEM)
    token = client.create_no_history_issue(title=TOKEN_TITLE, description="retained")
    root = token
    client.add_comment(
        issue_id=_ITEM,
        body=GENESIS_MARKER
        + _json(dict(schema=1, repository=_REPOSITORY, item_id=_ITEM, root_token_id=root)),
    )
    for generation, phase in enumerate(phases, start=1):
        successor = client.create_no_history_issue(title=TOKEN_TITLE, description="retained")
        payload = dict(
            schema=1,
            repository=_REPOSITORY,
            item_id=_ITEM,
            prior_token_id=token,
            next_token_id=successor,
            attempt=_attempt(generation=generation, phase=phase),
        )
        client.close_issue_without_verdict(
            issue_id=token, reason=TRANSITION_MARKER + _json(payload)
        )
        token = successor
    return client


class ListedLedger(FakeBeadsClient):
    """A ledger whose listing also carries records the locator must pass over."""

    def __init__(self, *, extra: list[BeadsRecord]) -> None:
        super().__init__()
        self.extra = extra

    def list_issues(self) -> list[BeadsRecord]:
        return [*self.extra, *super().list_issues()]


class ChangingHeadLedger(FakeBeadsClient):
    """A ledger whose current head stops being open between the walk and the re-read."""

    def __init__(self, *, head: str) -> None:
        super().__init__()
        self.head = head
        self.reads = 0

    def show_issue(self, *, issue_id: str) -> BeadsRecord:
        record = super().show_issue(issue_id=issue_id)
        if issue_id == self.head:
            self.reads += 1
            if self.reads > 1:
                return record | {"status": "closed"}
        return record


class BrokenLedger(FakeBeadsClient):
    def list_comments(self, *, issue_id: str) -> list[BeadsRecord]:
        raise BeadsCommandError(command=f"bd comments {issue_id}", exit_code=1, stderr="down")


def test_every_committed_attempt_is_returned_oldest_first_with_one_current_head() -> None:
    result = read_incident_history(client=_ledger(), repository=_REPOSITORY)
    assert isinstance(result, tuple)
    assert [reading.attempt.phase for reading in result] == ["repair", "repayment-ready"]
    assert [reading.is_current for reading in result] == [False, True]
    assert all(isinstance(reading, IncidentReading) for reading in result)
    assert len({reading.current_token_id for reading in result}) == 1
    assert result[0].operation_ids == ("operation-1", "operation-2")


def test_a_repository_filter_of_none_reads_every_repository() -> None:
    result = read_incident_history(client=_ledger(), repository=None)
    assert isinstance(result, tuple)
    assert len(result) == 2


def test_an_item_with_a_genesis_that_names_no_chain_refuses_the_whole_read() -> None:
    client = _ledger()
    _item(client, item="incident-2")
    client.add_comment(
        issue_id="incident-2",
        body=GENESIS_MARKER
        + _json(
            dict(
                schema=1, repository=_REPOSITORY, item_id="incident-9", root_token_id=_UNKNOWN_ROOT
            )
        ),
    )
    result = read_incident_history(client=client, repository=_REPOSITORY)
    assert isinstance(result, AuthorityRefusal)
    assert result.code == "incident-authority-invalid-genesis"


def test_a_head_that_changes_after_the_walk_refuses_by_name() -> None:
    client = _ledger(client=ChangingHeadLedger(head="fake-wisp-3"))
    result = read_incident_history(client=client, repository=_REPOSITORY)
    assert isinstance(result, AuthorityRefusal)
    assert result.code == "incident-authority-changed"


def test_records_without_a_text_id_or_a_comment_are_passed_over_by_the_locator() -> None:
    ledger = ListedLedger(
        extra=[
            {"id": None, "title": "no id"},
            {"id": "wisp-1", "title": TOKEN_TITLE},
            {"id": "quiet", "title": "no comments", "comment_count": 0},
        ]
    )
    assert read_incident_history(client=ledger, repository=_REPOSITORY) == ()


def test_an_unreadable_ledger_is_a_named_refusal_never_an_empty_history() -> None:
    client = BrokenLedger()
    _item(client, item=_ITEM)
    result = read_incident_history(client=client, repository=_REPOSITORY)
    assert isinstance(result, AuthorityRefusal)
    assert result.code == "incident-authority-unavailable"
