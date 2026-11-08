"""Current canonical lookup recovers an immutable pre-PR hook receipt."""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-dzbwaq
from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import incident_authority as command

from tests.livespec_orchestrator_beads_fabro.commands.test_incident_local_gate_receipt import (
    _canonical,
    _chain,
)


def test_lookup_recovers_recorded_partial_receipt_without_another_append(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    client, _attempt, root, current = _chain()
    monkeypatch.setattr(command, "store_config", lambda **_kwargs: None)
    monkeypatch.setattr(command, "make_beads_client", lambda **_kwargs: client)
    receipt = dict(
        receipt_id="hook-retry",
        hook="pre-commit",
        tree="c" * 40,
        mode="expedited-repair",
        evidence_kind="expedited-local-partial",
        exit_status=0,
        results=[
            dict(
                name="check-fast",
                status="passed",
                reason="gate completed",
                returncode=0,
                duration_seconds=0.123,
                output="real fast gate output",
            )
        ],
    )
    identity = [
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
    ]
    assert (
        command.main(argv=["record-local-gates", *identity, "--receipt-json", _canonical(receipt)])
        == 0
    )
    _ = capsys.readouterr()
    before = client.list_comments(issue_id="test-incident")
    try:
        actual = command.main(argv=["read-local-gates", *identity, "--receipt-id", "hook-retry"])
    except SystemExit as error:
        actual = error.code
    assert actual == 0
    response = json.loads(capsys.readouterr().out)
    assert response["authorizes_current_effects"] is False
    assert response["normal_factory_proof"] is False
    assert response["result"]["status"] == "recorded"
    assert response["result"]["receipt"] == receipt
    assert response["result"]["committed_token_id"] == root
    assert response["result"]["current_token_id"] == current
    assert client.list_comments(issue_id="test-incident") == before
