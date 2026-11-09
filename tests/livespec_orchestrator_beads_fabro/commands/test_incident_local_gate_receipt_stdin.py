"""A local-gate receipt travels on stdin, so its size is bounded by the authority and not by argv."""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-3ufhng
from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient
from livespec_orchestrator_beads_fabro.commands import incident_authority as command

from tests.livespec_orchestrator_beads_fabro.commands.test_incident_local_gate_receipt import (
    _canonical,
    _chain,
)

_ARGV_ENTRY_CAP = 131072


def _identity() -> list[str]:
    return [
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


def _receipt(*, output_bytes: int) -> dict[str, Any]:
    return dict(
        receipt_id="hook-large",
        hook="pre-commit",
        tree="c" * 40,
        mode="expedited-repair",
        evidence_kind="expedited-local-partial",
        exit_status=1,
        results=[
            dict(
                name="check-lint",
                status="failed",
                reason="lint output",
                returncode=1,
                duration_seconds=1.5,
                output="x" * output_bytes,
            )
        ],
    )


def _arm(*, monkeypatch: pytest.MonkeyPatch, text: str) -> FakeBeadsClient:
    client, _attempt, _root, _current = _chain()
    monkeypatch.setattr(command, "store_config", lambda **_kwargs: None)
    monkeypatch.setattr(command, "make_beads_client", lambda **_kwargs: client)
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(text.encode()), encoding="utf-8"))
    return client


def test_a_500_kib_receipt_is_recorded_when_supplied_on_stdin_and_not_in_argv(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    text = _canonical(_receipt(output_bytes=500 * 1024))
    client = _arm(monkeypatch=monkeypatch, text=text)
    argv = ["record-local-gates", *_identity(), "--receipt-stdin"]
    assert all(len(entry.encode()) < _ARGV_ENTRY_CAP for entry in argv)
    assert len(text.encode()) > 500 * 1024
    actual = command.main(argv=argv)
    response = json.loads(capsys.readouterr().out)
    assert (actual, response["status"]) == (0, "verified")
    assert response["result"]["receipt_id"] == "hook-large"
    comments = client.list_comments(issue_id="test-incident")
    assert len(comments) == 2
    assert json.loads(comments[-1]["text"].split("\n", 1)[1])["receipt"] == json.loads(text)


def test_a_receipt_over_the_size_bound_is_refused_invalid_and_records_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    client = _arm(monkeypatch=monkeypatch, text=_canonical(_receipt(output_bytes=1024 * 1024 + 1)))
    actual = command.main(argv=["record-local-gates", *_identity(), "--receipt-stdin"])
    response = json.loads(capsys.readouterr().out)
    assert (actual, response["status"]) == (78, "refused")
    assert response["result"]["code"] == "incident-receipt-invalid"
    assert len(client.list_comments(issue_id="test-incident")) == 1
