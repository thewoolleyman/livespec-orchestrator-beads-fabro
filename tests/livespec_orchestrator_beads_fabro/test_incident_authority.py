"""Incident trust is read from authenticated immutable ledger history."""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-dzbwaq
from __future__ import annotations

import json
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, IssueDraft
from livespec_orchestrator_beads_fabro.incident_authority import (
    AuthorityRefusal,
    read_incident_authority,
    read_incident_history,
)

REPOSITORY = "owner/repository"
ITEM = "test-incident"


def _ledger() -> FakeBeadsClient:
    client = FakeBeadsClient()
    client.create_issue(
        draft=IssueDraft(
            issue_id=ITEM,
            issue_type="bug",
            title="incident",
            description="behavior",
            assignee=None,
            created_at="2026-11-04T00:00:00Z",
        )
    )
    return client


def _attempt(**changes: Any) -> dict[str, Any]:
    fields = dict(
        repository=REPOSITORY,
        item_id=ITEM,
        attempt_id="attempt-1",
        phase="repair",
        operation_id="operation-1",
        generation=1,
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
    return fields | changes


def _query(attempt: dict[str, Any]) -> dict[str, Any]:
    return {
        key: attempt[key] for key in ("attempt_id", "phase", "operation_id", "generation", "owner")
    }


def test_environment_markers_and_metadata_do_not_establish_incident_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _ledger()
    client.update_issue(
        issue_id=ITEM,
        metadata={"incident_attempt": _attempt()},
        add_labels=["expedited-incident-response"],
    )
    monkeypatch.setenv("LIVESPEC_INCIDENT_CONTEXT", json.dumps(_attempt()))
    result = read_incident_authority(
        client=client, repository=REPOSITORY, item_id=ITEM, query=_query(_attempt())
    )
    assert isinstance(result, AuthorityRefusal)
    assert result.code == "incident-authority-missing"


def test_history_is_provenance_for_every_retained_attempt_and_refuses_an_unarmed_item() -> None:
    client = _ledger()
    refusal = read_incident_history(client=client, repository=REPOSITORY, item_id=ITEM)
    assert isinstance(refusal, AuthorityRefusal)
    assert refusal.code == "incident-authority-missing"
