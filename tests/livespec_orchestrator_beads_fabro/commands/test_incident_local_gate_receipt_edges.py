"""Malformed evidence, retries, races and lost replies preserve authority."""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-dzbwaq
from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import incident_local_gate_receipt as module
from livespec_orchestrator_beads_fabro.incident_authority import (
    AuthorityRefusal,
    IncidentReading,
    read_incident_authority,
)

from tests.livespec_orchestrator_beads_fabro.commands.test_incident_local_gate_receipt import (
    _canonical,
    _chain,
)


def _context() -> tuple[Any, IncidentReading, dict[str, Any]]:
    client, attempt, _root, _current = _chain()
    observed = read_incident_authority(
        client=client,
        repository="owner/repository",
        item_id="test-incident",
        query={
            key: attempt[key]
            for key in ("attempt_id", "phase", "operation_id", "generation", "owner")
        },
    )
    assert isinstance(observed, IncidentReading)
    receipt = dict(
        receipt_id="hook-1",
        hook="pre-commit",
        tree="c" * 40,
        mode="expedited-repair",
        evidence_kind="expedited-local-partial",
        exit_status=0,
        results=[
            dict(
                name="check-lint",
                status="passed",
                reason="gate completed",
                returncode=0,
                duration_seconds=0.1,
                output="ok",
            )
        ],
    )
    return client, observed, receipt


@pytest.mark.parametrize(
    "change",
    [
        {"extra": False},
        {"receipt_id": ""},
        {"hook": []},
        {"hook": "other"},
        {"tree": "short"},
        {"mode": "normal"},
        {"evidence_kind": "normal"},
        {"exit_status": True},
        {"exit_status": -1},
        {"results": {}},
        {"results": []},
        {"results": [None]},
        {"results": [{}]},
    ],
)
def test_invalid_receipts_never_append_or_change_authority(change: dict[str, Any]) -> None:
    client, observed, receipt = _context()
    before = client.list_comments(issue_id="test-incident")
    result = module.record_local_gates(
        client=client, observed=observed, text=_canonical(receipt | change)
    )
    assert isinstance(result, AuthorityRefusal)
    assert result.code == "incident-receipt-invalid"
    assert client.list_comments(issue_id="test-incident") == before


@pytest.mark.parametrize(
    "change",
    [
        {"name": ""},
        {"output": None},
        {"reason": 1},
        {"status": []},
        {"duration_seconds": True},
        {"duration_seconds": float("inf")},
        {"duration_seconds": -1},
        {"duration_seconds": 60},
        {"returncode": False},
        {"returncode": 1},
        {"status": "unknown"},
        {"status": "deferred", "returncode": None, "duration_seconds": 1},
        {"status": "deferred-timeout", "returncode": None, "duration_seconds": 1},
        {"status": "deferred", "returncode": 0},
    ],
)
def test_invalid_gate_results_are_not_partial_success(change: dict[str, Any]) -> None:
    client, observed, receipt = _context()
    receipt["results"][0].update(change)
    result = module.record_local_gates(client=client, observed=observed, text=_canonical(receipt))
    assert isinstance(result, AuthorityRefusal)
    assert result.code == "incident-receipt-invalid"


@pytest.mark.parametrize(
    "text", ["{", "[]", '{"receipt_id":"first","receipt_id":"last"}', " " * 1048577]
)
def test_unbounded_or_noncanonical_json_refuses(text: str) -> None:
    client, observed, _receipt = _context()
    result = module.record_local_gates(client=client, observed=observed, text=text)
    assert isinstance(result, AuthorityRefusal)
    assert result.code == "incident-receipt-invalid"


def test_same_receipt_identity_conflicting_payload_never_overwrites_first() -> None:
    client, observed, receipt = _context()
    first = module.record_local_gates(client=client, observed=observed, text=_canonical(receipt))
    assert isinstance(first, module.LocalGateReceipt)
    before = client.list_comments(issue_id="test-incident")
    receipt["results"][0]["output"] = "different"
    result = module.record_local_gates(client=client, observed=observed, text=_canonical(receipt))
    assert isinstance(result, AuthorityRefusal)
    assert result.code == "incident-receipt-operation-conflict"
    assert client.list_comments(issue_id="test-incident") == before


def test_stale_supplied_reading_never_records() -> None:
    client, observed, receipt = _context()
    result = module.record_local_gates(
        client=client, observed=replace(observed, is_current=False), text=_canonical(receipt)
    )
    assert isinstance(result, AuthorityRefusal)
    assert result.code == "incident-receipt-stale-observation"
    assert len(client.list_comments(issue_id="test-incident")) == 1


def test_receipt_survives_generation_change_during_append_but_cannot_admit_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, observed, receipt = _context()
    append = client.add_comment

    def moved(*, issue_id: str, body: str) -> None:
        append(issue_id=issue_id, body=body)
        client.close_issue_without_verdict(
            issue_id=observed.current_token_id, reason="foreign transition"
        )

    monkeypatch.setattr(client, "add_comment", moved)
    result = module.record_local_gates(client=client, observed=observed, text=_canonical(receipt))
    assert isinstance(result, AuthorityRefusal)
    assert len(client.list_comments(issue_id="test-incident")) == 2


def test_missing_readback_never_claims_durable_receipt(monkeypatch: pytest.MonkeyPatch) -> None:
    client, observed, receipt = _context()
    monkeypatch.setattr(client, "add_comment", lambda **_kwargs: None)
    result = module.record_local_gates(client=client, observed=observed, text=_canonical(receipt))
    assert isinstance(result, AuthorityRefusal)
    assert result.code == "incident-receipt-readback-conflict"


def test_actual_failure_retains_refusal_even_when_cleanup_crosses_deadline() -> None:
    client, observed, receipt = _context()
    receipt["exit_status"] = 1
    receipt["results"][0].update(status="failed", returncode=1, duration_seconds=60.1)
    result = module.record_local_gates(client=client, observed=observed, text=_canonical(receipt))
    assert isinstance(result, module.LocalGateReceipt)
    assert len(client.list_comments(issue_id="test-incident")) == 2


def test_ordinary_comment_and_foreign_receipt_do_not_satisfy_persistence() -> None:
    client, observed, receipt = _context()
    client.add_comment(
        issue_id="test-incident",
        body=module.MARKER + _canonical({"receipt": {"receipt_id": "foreign"}}),
    )
    result = module.record_local_gates(client=client, observed=observed, text=_canonical(receipt))
    assert isinstance(result, module.LocalGateReceipt)
    assert len(client.list_comments(issue_id="test-incident")) == 3


def test_unavailable_store_never_claims_recorded_partial_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, observed, receipt = _context()

    def outage(**_kwargs: Any) -> None:
        raise OSError("tenant unavailable")

    monkeypatch.setattr(client, "list_comments", outage)
    result = module.record_local_gates(client=client, observed=observed, text=_canonical(receipt))
    assert isinstance(result, AuthorityRefusal)
    assert result.code == "incident-receipt-unavailable"


def test_receipt_cli_requires_its_own_payload_without_accepting_it_on_read_commands() -> None:
    from livespec_orchestrator_beads_fabro.commands import incident_authority as command

    for action, extra in (("record-local-gates", []), ("read-current", ["--receipt-json", "{}"])):
        argv = [
            action,
            "--repo",
            ".",
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
            *extra,
        ]
        with pytest.raises(SystemExit, match="2"):
            command.main(argv=argv)


def test_original_red_negative_control_still_detects_an_unsupported_process_action(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from livespec_orchestrator_beads_fabro.commands import incident_authority as command

    from tests.livespec_orchestrator_beads_fabro.commands.test_incident_local_gate_receipt import (
        test_pre_pr_hook_records_exact_partial_results_and_retries_without_normal_proof,
    )

    def unsupported(**_kwargs: Any) -> int:
        raise SystemExit(2)

    monkeypatch.setattr(command, "main", unsupported)
    with pytest.raises(AssertionError):
        test_pre_pr_hook_records_exact_partial_results_and_retries_without_normal_proof(
            monkeypatch=monkeypatch, capsys=capsys
        )
