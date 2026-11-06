"""Consumers obtain incident receipts only from the retained chain of a named item."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    fake_singleton,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro._incident_authority_payload import (
    GENESIS_MARKER,
    TOKEN_TITLE,
    TRANSITION_MARKER,
)
from livespec_orchestrator_beads_fabro.commands._incident_receipt_source import (
    IncidentReceiptRefusal,
    add_incident_item_argument,
    describe_refusal,
    incident_authority_client,
    resolve_incident_receipts,
)

_REPOSITORY = "owner/repository"
_ITEM = "incident-1"


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _attempt(*, generation: int, phase: str, pr_number: int) -> dict[str, Any]:
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
        pr_number=pr_number,
        landed_commits=[] if pr_number == 0 else ["c" * 40],
        landed_trees=[] if pr_number == 0 else ["d" * 40],
        original_paths=["app.py"],
        deferred_work=["normal-factory-proof"],
        repayment_required=True,
    )


def _chain(*, attempts: list[dict[str, Any]]) -> FakeBeadsClient:
    client = FakeBeadsClient()
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
    token = client.create_no_history_issue(title=TOKEN_TITLE, description="token")
    client.add_comment(
        issue_id=_ITEM,
        body=GENESIS_MARKER
        + _canonical(dict(schema=1, repository=_REPOSITORY, item_id=_ITEM, root_token_id=token)),
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
    return client


def test_the_argument_is_a_repeatable_explicit_item_id() -> None:
    parser = argparse.ArgumentParser()
    add_incident_item_argument(parser=parser)
    assert parser.parse_args([]).incident_items is None
    assert parser.parse_args(["--incident-item", "a", "--incident-item", "b"]).incident_items == [
        "a",
        "b",
    ]


def test_receipts_come_from_every_pr_bound_attempt_of_each_named_item() -> None:
    client = _chain(
        attempts=[
            _attempt(generation=1, phase="repair", pr_number=0),
            _attempt(generation=2, phase="repair", pr_number=73),
            _attempt(generation=3, phase="repayment-active", pr_number=80),
        ]
    )
    receipts = resolve_incident_receipts(client=client, repository=_REPOSITORY, item_ids=(_ITEM,))
    assert not isinstance(receipts, IncidentReceiptRefusal)
    assert [(receipt.phase, receipt.pr_number) for receipt in receipts] == [
        ("repair", 73),
        ("repayment-active", 80),
    ]
    assert all(receipt.repayment_outstanding for receipt in receipts)
    assert resolve_incident_receipts(client=client, repository=_REPOSITORY, item_ids=()) == ()


def test_an_item_whose_chain_cannot_be_read_is_a_named_refusal_not_an_empty_set() -> None:
    client = _chain(attempts=[_attempt(generation=1, phase="repair", pr_number=73)])
    refusal = resolve_incident_receipts(
        client=client, repository=_REPOSITORY, item_ids=(_ITEM, "absent")
    )
    assert isinstance(refusal, IncidentReceiptRefusal)
    assert refusal.item_id == "absent"
    assert refusal.code == "incident-authority-unavailable"
    text = describe_refusal(refusal=refusal)
    assert text.startswith("incident item absent could not be verified")
    assert "incident-authority-unavailable" in text
    wrong_repository = resolve_incident_receipts(
        client=client, repository="other/repository", item_ids=(_ITEM,)
    )
    assert isinstance(wrong_repository, IncidentReceiptRefusal)
    assert wrong_repository.code == "incident-authority-invalid-genesis"


def test_the_client_is_the_injected_one_else_the_project_configured_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    injected = FakeBeadsClient()
    assert incident_authority_client(repo=tmp_path, client=injected) is injected
    _ = (tmp_path / ".livespec.jsonc").write_text(
        json.dumps(
            {"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib", "fake": True}}}
        ),
        encoding="utf-8",
    )
    assert incident_authority_client(repo=tmp_path, client=None) is fake_singleton()
    reset_fake_singleton()
