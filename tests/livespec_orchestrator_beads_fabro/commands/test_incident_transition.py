"""Installed consumers can conditionally advance an existing incident chain."""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-dzbwaq
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, IssueDraft
from livespec_orchestrator_beads_fabro._incident_authority_payload import (
    GENESIS_MARKER,
    TOKEN_TITLE,
    TRANSITION_MARKER,
)
from livespec_orchestrator_beads_fabro.commands import incident_authority as command
from livespec_orchestrator_beads_fabro.incident_authority import IncidentReading


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _attempt(**changes: Any) -> dict[str, Any]:
    return (
        dict(
            repository="owner/repository",
            item_id="test-incident",
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
        | changes
    )


def _chain(*, monkeypatch: pytest.MonkeyPatch, initialized: bool = True) -> FakeBeadsClient:
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
    if initialized:
        root = client.create_no_history_issue(title=TOKEN_TITLE, description="authority")
        current = client.create_no_history_issue(title=TOKEN_TITLE, description="authority")
        client.add_comment(
            issue_id="test-incident",
            body=GENESIS_MARKER
            + _json(
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
            + _json(
                dict(
                    schema=1,
                    repository="owner/repository",
                    item_id="test-incident",
                    prior_token_id=root,
                    next_token_id=current,
                    attempt=_attempt(),
                )
            ),
        )
    monkeypatch.setattr(command, "store_config", lambda **_kwargs: None)
    monkeypatch.setattr(command, "make_beads_client", lambda **_kwargs: client)
    return client


def _argv(*, successor: object, generation: int = 1) -> list[str]:
    return [
        "commit-transition",
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
        str(generation),
        "--owner",
        "operator:alice",
        "--successor-json",
        _json(successor),
    ]


def _successor(**changes: Any) -> dict[str, Any]:
    return _attempt(generation=2, phase="master-observation", operation_id="observe-1") | changes


def test_process_transition_commits_and_recovers_exact_retry_without_duplicate_effect(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = _chain(monkeypatch=monkeypatch)
    original = client.show_issue(issue_id="test-incident")
    assert command.main(argv=_argv(successor=_successor())) == 0
    first = json.loads(capsys.readouterr().out)
    standing = client.list_issues()
    assert first["status"] == "verified"
    assert first["result"]["attempt"] == _successor()
    assert first["authorizes_current_effects"] is False
    assert first["normal_factory_proof"] is False
    assert command.main(argv=_argv(successor=_successor())) == 0
    assert json.loads(capsys.readouterr().out) == first
    assert client.list_issues() == standing
    assert client.show_issue(issue_id="test-incident") == original


@pytest.mark.parametrize(
    "successor",
    [
        None,
        {},
        True,
        _successor(generation=True),
        _successor(repository="foreign/repo"),
        _successor(original_paths=["other.py"]),
    ],
)
def test_invalid_successor_refuses_without_writing(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    successor: object,
) -> None:
    client = _chain(monkeypatch=monkeypatch)
    before = client.list_issues()
    assert command.main(argv=_argv(successor=successor)) == 78
    response = json.loads(capsys.readouterr().out)
    assert response["status"] == "refused"
    assert response["result"]["code"] == "incident-transition-invalid-successor"
    assert client.list_issues() == before


def test_absent_authority_never_bootstraps_or_claims_factory_fencing(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = _chain(monkeypatch=monkeypatch, initialized=False)
    before = client.list_issues()
    assert command.main(argv=_argv(successor=_successor())) == 78
    response = json.loads(capsys.readouterr().out)
    assert response["result"]["code"] == "incident-authority-missing"
    assert response["authorizes_current_effects"] is False
    assert client.list_issues() == before


def test_wrong_expected_generation_refuses_without_writing(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = _chain(monkeypatch=monkeypatch)
    before = client.list_issues()
    assert command.main(argv=_argv(successor=_successor(), generation=4)) == 78
    assert (
        json.loads(capsys.readouterr().out)["result"]["code"]
        == "incident-authority-identity-mismatch"
    )
    assert client.list_issues() == before


def test_reused_operation_with_changed_payload_refuses_before_mutation(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = _chain(monkeypatch=monkeypatch)
    assert command.main(argv=_argv(successor=_successor())) == 0
    _ = capsys.readouterr()
    before = client.list_issues()
    assert command.main(argv=_argv(successor=_successor(head="d" * 40))) == 78
    assert (
        json.loads(capsys.readouterr().out)["result"]["code"]
        == "incident-transition-operation-conflict"
    )
    assert client.list_issues() == before


def test_observation_does_not_synthesize_a_successful_commit_when_writer_refuses(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from livespec_orchestrator_beads_fabro.incident_authority import AuthorityRefusal

    _chain(monkeypatch=monkeypatch)
    seen: list[IncidentReading] = []

    def refuse(**kwargs: Any) -> AuthorityRefusal:
        seen.append(kwargs["observed"])
        return AuthorityRefusal(code="incident-transition-lost-race", detail="new owner")

    monkeypatch.setattr(command, "commit_incident_transition", refuse)
    assert command.main(argv=_argv(successor=_successor())) == 78
    assert json.loads(capsys.readouterr().out)["result"]["code"] == "incident-transition-lost-race"
    assert asdict(seen[0].attempt)["generation"] == 1


@pytest.mark.parametrize("raw", ["not json", '{"generation":2,"generation":3}'])
def test_malformed_transition_request_refuses_without_writing(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    raw: str,
) -> None:
    client = _chain(monkeypatch=monkeypatch)
    before = client.list_issues()
    argv = _argv(successor=_successor())
    argv[-1] = raw
    assert command.main(argv=argv) == 78
    assert (
        json.loads(capsys.readouterr().out)["result"]["code"]
        == "incident-transition-invalid-successor"
    )
    assert client.list_issues() == before


def test_transition_requires_successor_while_read_actions_remain_unmodified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _chain(monkeypatch=monkeypatch)
    before = client.list_issues()
    with pytest.raises(SystemExit, match="2"):
        command.main(argv=_argv(successor=_successor())[:-2])
    assert client.list_issues() == before
