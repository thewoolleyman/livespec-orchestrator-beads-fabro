"""A pre-PR hook persists partial evidence without granting normal proof."""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-dzbwaq
from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, IssueDraft
from livespec_orchestrator_beads_fabro._incident_authority_payload import (
    GENESIS_MARKER,
    TOKEN_TITLE,
    TRANSITION_MARKER,
)
from livespec_orchestrator_beads_fabro.commands import incident_authority as command


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _chain() -> tuple[FakeBeadsClient, dict[str, object], str, str]:
    client = FakeBeadsClient()
    client.create_issue(
        draft=IssueDraft(
            issue_id="test-incident",
            issue_type="bug",
            title="incident",
            description="behavior",
            assignee=None,
            created_at="2026-11-04T00:00:00Z",
        )
    )
    root = client.create_no_history_issue(title=TOKEN_TITLE, description="authority")
    current = client.create_no_history_issue(title=TOKEN_TITLE, description="authority")
    attempt = dict(
        repository="owner/repository",
        item_id="test-incident",
        attempt_id="attempt-1",
        phase="repair",
        operation_id="operation-1",
        generation=1,
        owner="operator:alice",
        base="a" * 40,
        head="b" * 40,
        pr_number=0,
        landed_commits=[],
        landed_trees=[],
        original_paths=["app.py"],
        deferred_work=["normal-factory-proof"],
        repayment_required=True,
    )
    client.add_comment(
        issue_id="test-incident",
        body=GENESIS_MARKER
        + _canonical(
            dict(
                schema=1,
                repository="owner/repository",
                item_id="test-incident",
                root_token_id=root,
            )
        ),
    )
    client.close_issue_without_verdict(
        issue_id=root,
        reason=TRANSITION_MARKER
        + _canonical(
            dict(
                schema=1,
                repository="owner/repository",
                item_id="test-incident",
                prior_token_id=root,
                next_token_id=current,
                attempt=attempt,
            )
        ),
    )
    return client, attempt, root, current


def test_pre_pr_hook_records_exact_partial_results_and_retries_without_normal_proof(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    client, attempt, root, current = _chain()
    monkeypatch.setattr(command, "store_config", lambda **_kwargs: None)
    monkeypatch.setattr(command, "make_beads_client", lambda **_kwargs: client)
    receipt = dict(
        receipt_id="hook-1",
        hook="pre-commit",
        tree="c" * 40,
        mode="expedited-repair",
        evidence_kind="expedited-local-partial",
        exit_status=0,
        results=[
            dict(
                name="check-types",
                status="deferred",
                reason="known slow gate",
                returncode=None,
                duration_seconds=0.0,
                output="",
            )
        ],
    )
    argv = [
        "record-local-gates",
        "--repo",
        str(Path.cwd()),
        "--repository",
        "owner/repository",
        "--item",
        "test-incident",
        "--attempt",
        "attempt-1",
        "--phase",
        "repair",
        "--operation",
        "operation-1",
        "--generation",
        "1",
        "--owner",
        "operator:alice",
        "--receipt-json",
        _canonical(receipt),
    ]
    try:
        actual = command.main(argv=argv)
    except SystemExit as error:
        actual = error.code
    assert actual == 0
    response = json.loads(capsys.readouterr().out)
    assert response["status"] == "verified"
    assert response["authorizes_current_effects"] is False
    assert response["normal_factory_proof"] is False
    comments = client.list_comments(issue_id="test-incident")
    assert len(comments) == 2
    body = comments[-1]["text"]
    assert body.startswith("livespec-incident-local-gates-v1\n")
    stored = json.loads(body.split("\n", 1)[1])
    assert stored["attempt"] == attempt
    assert stored["committed_token_id"] == root
    assert stored["current_token_id"] == current
    assert stored["receipt"] == receipt
    assert command.main(argv=argv) == 0
    assert json.loads(capsys.readouterr().out) == response
    assert client.list_comments(issue_id="test-incident") == comments
