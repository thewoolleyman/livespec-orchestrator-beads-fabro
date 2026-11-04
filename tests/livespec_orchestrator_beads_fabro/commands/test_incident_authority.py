"""The process protocol preserves trust and historical/current distinctions."""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-dzbwaq
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import incident_authority as command
from livespec_orchestrator_beads_fabro.incident_authority import (
    AuthorityRefusal,
    IncidentAttempt,
    IncidentReading,
)


def _argv(*, action: str, root: Path) -> list[str]:
    return [
        action,
        "--repo",
        str(root),
        "--repository",
        "owner/repo",
        "--item",
        "item-1",
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


@pytest.mark.parametrize("action", ["read-current", "read-history"])
def test_process_reply_never_upgrades_incident_evidence_to_normal_factory_proof(
    action: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    attempt = IncidentAttempt(
        repository="owner/repo",
        item_id="item-1",
        attempt_id="attempt-1",
        phase="repair",
        operation_id="operation-1",
        generation=1,
        owner="operator:alice",
        base="a" * 40,
        head="b" * 40,
        pr_number=7,
        landed_commits=("b" * 40,),
        landed_trees=("c" * 40,),
        original_paths=("app.py",),
        deferred_work=("normal-factory-proof",),
        repayment_required=True,
    )
    captured: dict[str, Any] = {}

    def read(**kwargs: Any) -> IncidentReading:
        captured.update(kwargs)
        return IncidentReading(
            attempt=attempt,
            committed_token_id=attempt.item_id,
            current_token_id=attempt.attempt_id,
            is_current=True,
        )

    monkeypatch.setattr(command, "store_config", lambda **_kwargs: None)
    monkeypatch.setattr(command, "make_beads_client", lambda **_kwargs: "client")
    monkeypatch.setattr(command, "read_incident_authority", read)
    assert command.main(argv=_argv(action=action, root=tmp_path)) == 0
    response = json.loads(capsys.readouterr().out)
    assert response["schema"] == 1
    assert response["status"] == "verified"
    assert response["normal_factory_proof"] is False
    assert response["authorizes_current_effects"] is (action == "read-current")
    assert response["result"]["attempt"]["landed_commits"] == ["b" * 40]
    assert captured["historical"] is (action == "read-history")
    assert captured["query"] == dict(
        attempt_id="attempt-1",
        phase="repair",
        operation_id="operation-1",
        generation=1,
        owner="operator:alice",
    )


def test_refusal_has_named_code_nonzero_exit_and_no_normal_fallback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setattr(command, "store_config", lambda **_kwargs: None)
    monkeypatch.setattr(command, "make_beads_client", lambda **_kwargs: "client")
    monkeypatch.setattr(
        command,
        "read_incident_authority",
        lambda **_kwargs: AuthorityRefusal(
            code="incident-authority-unavailable", detail="tenant unavailable"
        ),
    )
    assert command.main(argv=_argv(action="read-current", root=tmp_path)) == 78
    response = json.loads(capsys.readouterr().out)
    assert response["status"] == "refused"
    assert response["result"]["code"] == "incident-authority-unavailable"
    assert response["authorizes_current_effects"] is False
    assert response["normal_factory_proof"] is False


@pytest.mark.parametrize("action", ["read-current", "read-history"])
def test_read_commands_reject_transition_payloads(action: str, tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="2"):
        command.main(argv=[*_argv(action=action, root=tmp_path), "--successor-json", "{}"])


@pytest.mark.parametrize("encoding", ["indented", "duplicate-key"])
def test_writer_rejects_noncanonical_successor_before_commit(
    encoding: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    attempt = IncidentAttempt(
        repository="owner/repo",
        item_id="item-1",
        attempt_id="attempt-1",
        phase="repair",
        operation_id="operation-1",
        generation=1,
        owner="operator:alice",
        base="a" * 40,
        head="b" * 40,
        pr_number=7,
        landed_commits=(),
        landed_trees=(),
        original_paths=("app.py",),
        deferred_work=("normal-factory-proof",),
        repayment_required=True,
    )
    reading = IncidentReading(
        attempt=attempt,
        committed_token_id=attempt.item_id,
        current_token_id=attempt.attempt_id,
        is_current=True,
    )
    monkeypatch.setattr(command, "store_config", lambda **_kwargs: None)
    monkeypatch.setattr(command, "make_beads_client", lambda **_kwargs: "client")
    monkeypatch.setattr(command, "read_incident_authority", lambda **_kwargs: reading)
    calls: list[object] = []
    monkeypatch.setattr(
        command, "commit_incident_transition", lambda **kwargs: calls.append(kwargs)
    )
    value = asdict(attempt) | dict(generation=2, operation_id="operation-2")
    raw = (
        json.dumps(value, sort_keys=True, indent=2)
        if encoding == "indented"
        else json.dumps(value, sort_keys=True, separators=(",", ":")).replace(
            '"generation":2', '"generation":2,"generation":2'
        )
    )
    assert (
        command.main(
            argv=[*_argv(action="commit-transition", root=tmp_path), "--successor-json", raw]
        )
        == 78
    )
    assert (
        json.loads(capsys.readouterr().out)["result"]["code"]
        == "incident-transition-invalid-successor"
    )
    assert calls == []
