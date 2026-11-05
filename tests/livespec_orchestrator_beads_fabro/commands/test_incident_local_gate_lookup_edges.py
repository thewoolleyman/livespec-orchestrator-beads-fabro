"""Canonical lookup distinguishes exact evidence, absence, races and outage."""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-dzbwaq
from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._incident_authority_payload import attempt_record
from livespec_orchestrator_beads_fabro.commands import incident_authority as command
from livespec_orchestrator_beads_fabro.commands import incident_local_gate_lookup as module
from livespec_orchestrator_beads_fabro.commands import incident_local_gate_receipt as writer
from livespec_orchestrator_beads_fabro.commands.incident_local_gate_receipt import matching_receipts
from livespec_orchestrator_beads_fabro.incident_authority import AuthorityRefusal

from tests.livespec_orchestrator_beads_fabro.commands.test_incident_local_gate_receipt import (
    _canonical,
)
from tests.livespec_orchestrator_beads_fabro.commands.test_incident_local_gate_receipt_edges import (
    _context,
)


def _body(*, observed: Any, receipt: dict[str, Any]) -> str:
    return writer.MARKER + _canonical(
        dict(
            schema=1,
            attempt=attempt_record(attempt=observed.attempt),
            committed_token_id=observed.committed_token_id,
            current_token_id=observed.current_token_id,
            receipt=receipt,
            normal_factory_proof=False,
        )
    )


def test_absence_is_current_canonical_read_without_append() -> None:
    client, observed, _receipt = _context()
    before = client.list_comments(issue_id=observed.attempt.item_id)
    result = module.read_local_gates(client=client, observed=observed, receipt_id="not-recorded")
    assert isinstance(result, module.LocalGateLookup)
    assert result.status == "absent"
    assert result.receipt is None and result.checksum is None
    assert result.committed_token_id == observed.committed_token_id
    assert result.current_token_id == observed.current_token_id
    assert client.list_comments(issue_id=observed.attempt.item_id) == before


def test_recorded_failure_recovers_exact_payload_and_comment_checksum() -> None:
    client, observed, receipt = _context()
    receipt["exit_status"] = 1
    receipt["results"][0].update(status="failed", returncode=1, duration_seconds=61.25)
    persisted = writer.record_local_gates(
        client=client, observed=observed, text=_canonical(receipt)
    )
    assert isinstance(persisted, writer.LocalGateReceipt)
    comments = client.list_comments(issue_id=observed.attempt.item_id)
    result = module.read_local_gates(
        client=client, observed=observed, receipt_id=receipt["receipt_id"]
    )
    assert isinstance(result, module.LocalGateLookup)
    assert result.status == "recorded"
    assert result.receipt == receipt
    assert result.checksum == persisted.checksum
    assert result.checksum == "sha256:" + hashlib.sha256(comments[-1]["text"].encode()).hexdigest()
    assert client.list_comments(issue_id=observed.attempt.item_id) == comments


@pytest.mark.parametrize("receipt_id", ["", " ", " hook-1", "hook-1 "])
def test_noncanonical_receipt_identity_refuses(receipt_id: str) -> None:
    client, observed, _receipt = _context()
    result = module.read_local_gates(client=client, observed=observed, receipt_id=receipt_id)
    assert isinstance(result, AuthorityRefusal)
    assert result.code == "incident-receipt-invalid"


def test_historical_observation_cannot_supply_current_lookup() -> None:
    client, observed, _receipt = _context()
    result = module.read_local_gates(
        client=client, observed=replace(observed, is_current=False), receipt_id="hook-1"
    )
    assert isinstance(result, AuthorityRefusal)
    assert result.code == "incident-receipt-stale-observation"


def test_conflicting_immutable_evidence_never_selects_arbitrary_receipt() -> None:
    client, observed, receipt = _context()
    result = writer.record_local_gates(client=client, observed=observed, text=_canonical(receipt))
    assert isinstance(result, writer.LocalGateReceipt)
    receipt["results"][0]["output"] = "conflicting retained result"
    client.add_comment(
        issue_id=observed.attempt.item_id, body=_body(observed=observed, receipt=receipt)
    )
    result = module.read_local_gates(
        client=client, observed=observed, receipt_id=receipt["receipt_id"]
    )
    assert isinstance(result, AuthorityRefusal)
    assert result.code == "incident-receipt-readback-conflict"


@pytest.mark.parametrize(
    "change",
    [
        {"schema": 2},
        {"extra": True},
        {"normal_factory_proof": True},
        {"committed_token_id": "foreign-root"},
        {"current_token_id": "foreign-current"},
        {"attempt": {}},
    ],
)
def test_matching_receipt_id_never_accepts_foreign_envelope(change: dict[str, Any]) -> None:
    client, observed, receipt = _context()
    record = dict(
        schema=1,
        attempt=attempt_record(attempt=observed.attempt),
        committed_token_id=observed.committed_token_id,
        current_token_id=observed.current_token_id,
        receipt=receipt,
        normal_factory_proof=False,
    )
    client.add_comment(
        issue_id=observed.attempt.item_id, body=writer.MARKER + _canonical(record | change)
    )
    result = module.read_local_gates(
        client=client, observed=observed, receipt_id=receipt["receipt_id"]
    )
    assert isinstance(result, AuthorityRefusal)
    assert result.code == "incident-receipt-identity-conflict"


def test_matching_but_invalid_receipt_is_not_authoritative_absence() -> None:
    client, observed, receipt = _context()
    receipt["exit_status"] = True
    client.add_comment(
        issue_id=observed.attempt.item_id, body=_body(observed=observed, receipt=receipt)
    )
    result = module.read_local_gates(
        client=client, observed=observed, receipt_id=receipt["receipt_id"]
    )
    assert isinstance(result, AuthorityRefusal)
    assert result.code == "incident-receipt-identity-conflict"


def test_moved_generation_during_lookup_refuses_even_when_initial_read_was_current(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, observed, _receipt = _context()
    original = matching_receipts

    def moved(**kwargs: Any) -> set[str]:
        matches = original(**kwargs)
        client.close_issue_without_verdict(
            issue_id=observed.current_token_id, reason="foreign transition"
        )
        return matches

    monkeypatch.setattr(module, "matching_receipts", moved)
    result = module.read_local_gates(client=client, observed=observed, receipt_id="hook-1")
    assert isinstance(result, AuthorityRefusal)


def test_unavailable_comments_never_become_authoritative_absence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, observed, _receipt = _context()

    def unavailable(**_kwargs: Any) -> set[str]:
        raise OSError("tenant unavailable")

    monkeypatch.setattr(module, "matching_receipts", unavailable)
    result = module.read_local_gates(client=client, observed=observed, receipt_id="hook-1")
    assert isinstance(result, AuthorityRefusal)
    assert result.code == "incident-receipt-unavailable"


@pytest.mark.parametrize(
    ("action", "extra"),
    [
        ("read-local-gates", []),
        ("read-current", ["--receipt-id", "hook-1"]),
        ("record-local-gates", ["--receipt-json", "{}", "--receipt-id", "hook-1"]),
    ],
)
def test_lookup_identity_argument_is_scoped_to_its_own_action(
    action: str, extra: list[str]
) -> None:
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
        "--owner",
        "operator:alice",
        "--generation",
        "1",
    ]
    with pytest.raises(SystemExit, match="2"):
        command.main(argv=[action, *identity, *extra])


def test_original_red_negative_control_still_detects_unsupported_lookup(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from tests.livespec_orchestrator_beads_fabro.commands.test_incident_local_gate_lookup import (
        test_lookup_recovers_recorded_partial_receipt_without_another_append,
    )

    original = command.main

    def unsupported(*, argv: list[str]) -> int:
        if argv[0] == "read-local-gates":
            raise SystemExit(2)
        return original(argv=argv)

    monkeypatch.setattr(command, "main", unsupported)
    with pytest.raises(AssertionError):
        test_lookup_recovers_recorded_partial_receipt_without_another_append(
            monkeypatch=monkeypatch, capsys=capsys
        )
