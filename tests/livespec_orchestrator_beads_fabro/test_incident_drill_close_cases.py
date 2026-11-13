"""The drill-close authority action fails closed on every unproven drill shape."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro import incident_drill_close
from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, IssueDraft
from livespec_orchestrator_beads_fabro._incident_authority_payload import (
    GENESIS_MARKER,
    TOKEN_TITLE,
    TRANSITION_MARKER,
)
from livespec_orchestrator_beads_fabro._incident_authority_types import (
    AuthorityRefusal,
    IncidentReading,
)
from livespec_orchestrator_beads_fabro._store_claim_tokens import (
    ClaimChangeResult,
    create_claim_token,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.incident_authority import read_incident_authority
from livespec_orchestrator_beads_fabro.incident_completion import read_incident_standing
from livespec_orchestrator_beads_fabro.incident_drill_close import DrillClose, close_drill

_REPOSITORY = "owner/repository"
_ITEM = "bd-ib-drill-cases"
_SCRATCH = "refs/heads/incident-scratch/bd-ib-drill-cases"


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _attempt(**changes: Any) -> dict[str, Any]:
    return {
        "repository": _REPOSITORY,
        "item_id": _ITEM,
        "attempt_id": "drill-1",
        "phase": "reverting",
        "operation_id": "drill-1#reverting",
        "generation": 1,
        "owner": "operator:alice",
        "base": "a" * 40,
        "head": "b" * 40,
        "pr_number": 7,
        "landed_commits": [],
        "landed_trees": [],
        "original_paths": ["app.py"],
        "deferred_work": ["normal-factory-proof"],
        "repayment_required": True,
        "carrier": {
            "state": "pr-bound",
            "target_ref": _SCRATCH,
            "input_parent": "a" * 40,
            "staged_tree": "c" * 40,
            "remote_head": "b" * 40,
        },
    } | changes


def _seed(*, snapshot: dict[str, Any]) -> tuple[FakeBeadsClient, IncidentReading]:
    client = FakeBeadsClient()
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=_ITEM,
            issue_type="bug",
            title="drill",
            description="recorded drill",
            assignee="operator:alice",
            created_at="2026-11-13T00:00:00Z",
        )
    )
    root = client.create_no_history_issue(title=TOKEN_TITLE, description="authority root")
    token = client.create_no_history_issue(title=TOKEN_TITLE, description="authority token")
    client.add_comment(
        issue_id=_ITEM,
        body=GENESIS_MARKER
        + _json({"schema": 1, "repository": _REPOSITORY, "item_id": _ITEM, "root_token_id": root}),
    )
    client.close_issue_without_verdict(
        issue_id=root,
        reason=TRANSITION_MARKER
        + _json(
            {
                "schema": 1,
                "repository": _REPOSITORY,
                "item_id": _ITEM,
                "prior_token_id": root,
                "next_token_id": token,
                "attempt": snapshot,
            }
        ),
    )
    client.update_issue(
        issue_id=_ITEM,
        status="active",
        metadata={"dispatch_claim_token": create_claim_token(client=client)},
        names_claim_token=True,
    )
    reading = read_incident_authority(
        client=client,
        repository=_REPOSITORY,
        item_id=_ITEM,
        query={
            key: snapshot[key]
            for key in ("attempt_id", "phase", "operation_id", "generation", "owner")
        },
    )
    assert isinstance(reading, IncidentReading)
    return client, reading


class _Forge:
    def __init__(self, *, pr: CommandResult, comparison: CommandResult | None = None) -> None:
        self.pr = pr
        self.comparison = comparison
        self.calls: list[list[str]] = []

    def run(self, *, argv: list[str], **_: object) -> CommandResult:
        self.calls.append(argv)
        if argv[:3] == ["gh", "pr", "view"]:
            return self.pr
        if argv[:3] == ["gh", "api", f"repos/{_REPOSITORY}/compare/{'d' * 40}...master"]:
            assert self.comparison is not None
            return self.comparison
        raise AssertionError(argv)  # pragma: no cover - fixture contract guard


def _merged(*, base: str = "incident-scratch/bd-ib-drill-cases") -> CommandResult:
    return CommandResult(
        exit_code=0,
        stdout=_json({"number": 7, "state": "MERGED", "baseRefName": base}),
        stderr="",
    )


@pytest.mark.parametrize(
    ("snapshot", "forge", "code", "detail"),
    [
        (
            _attempt(
                phase="repair",
                carrier={
                    "state": "branch-reserved",
                    "target_ref": _SCRATCH,
                    "input_parent": "a" * 40,
                    "staged_tree": "c" * 40,
                },
                pr_number=0,
            ),
            _Forge(pr=_merged()),
            "incident-not-a-recorded-drill",
            "attempt drill-1",
        ),
        (
            _attempt(),
            _Forge(pr=_merged(base="master")),
            "incident-not-a-recorded-drill",
            f"carrier {_SCRATCH}",
        ),
        (
            _attempt(),
            _Forge(pr=CommandResult(exit_code=1, stdout="", stderr="down")),
            "incident-drill-evidence-unavailable",
            "PR #7",
        ),
        (
            _attempt(),
            _Forge(pr=CommandResult(exit_code=0, stdout="{}", stderr="")),
            "incident-drill-evidence-unavailable",
            "PR #7",
        ),
        (
            _attempt(landed_commits=["d" * 40], landed_trees=["e" * 40]),
            _Forge(
                pr=_merged(),
                comparison=CommandResult(exit_code=0, stdout=_json({"behind_by": 0}), stderr=""),
            ),
            "incident-not-a-recorded-drill",
            "landed commit",
        ),
        (
            _attempt(landed_commits=["d" * 40], landed_trees=["e" * 40]),
            _Forge(pr=_merged(), comparison=CommandResult(exit_code=0, stdout="[]", stderr="")),
            "incident-drill-evidence-unavailable",
            "commit",
        ),
        (
            _attempt(landed_commits=["d" * 40], landed_trees=["e" * 40]),
            _Forge(
                pr=_merged(),
                comparison=CommandResult(exit_code=0, stdout=_json({"behind_by": -1}), stderr=""),
            ),
            "incident-drill-evidence-unavailable",
            "commit",
        ),
    ],
)
def test_refusal_preserves_the_incident_reading_and_claim(
    snapshot: dict[str, Any], forge: _Forge, code: str, detail: str, tmp_path: Path
) -> None:
    client, reading = _seed(snapshot=snapshot)
    before = client.show_issue(issue_id=_ITEM)
    refused = close_drill(
        client=client, reading=reading, runner=forge, repo=tmp_path, repository=_REPOSITORY
    )

    assert isinstance(refused, AuthorityRefusal)
    assert refused.code == code
    assert detail in refused.detail
    after = client.show_issue(issue_id=_ITEM)
    assert after["status"] == before["status"]
    assert after["assignee"] == before["assignee"]
    current = read_incident_standing(client=client, item_id=_ITEM)
    assert (current.history[-1].phase, current.history[-1].generation) == (
        snapshot["phase"],
        snapshot["generation"],
    )


def test_close_uses_forge_compare_and_recovers_the_same_fenced_operation(tmp_path: Path) -> None:
    client, reading = _seed(snapshot=_attempt(landed_commits=["d" * 40], landed_trees=["e" * 40]))
    forge = _Forge(
        pr=_merged(),
        comparison=CommandResult(exit_code=0, stdout=_json({"behind_by": 2}), stderr=""),
    )

    closed = close_drill(
        client=client, reading=reading, runner=forge, repo=tmp_path, repository=_REPOSITORY
    )
    recovered = close_drill(
        client=client, reading=reading, runner=forge, repo=tmp_path, repository=_REPOSITORY
    )

    assert isinstance(closed, DrillClose)
    assert recovered == closed
    assert closed.reading.attempt.operation_id == "drill-1#drill-close"
    assert closed.reading.attempt.repayment_required is False
    assert len(forge.calls) == 2
    standing = read_incident_standing(client=client, item_id=_ITEM)
    assert standing.history[-1].phase == "drill-closed"


def test_non_eligible_phase_is_not_a_recorded_drill(tmp_path: Path) -> None:
    client, reading = _seed(snapshot=_attempt(phase="closed"))

    refused = close_drill(
        client=client,
        reading=reading,
        runner=_Forge(pr=_merged()),
        repo=tmp_path,
        repository=_REPOSITORY,
    )

    assert isinstance(refused, AuthorityRefusal)
    assert refused.code == "incident-not-a-recorded-drill"


def test_authority_history_refusal_is_returned_unchanged(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client, reading = _seed(snapshot=_attempt())
    refusal = AuthorityRefusal(code="incident-authority-unavailable", detail=_ITEM)

    def unavailable_history(
        *, client: FakeBeadsClient, repository: str, item_id: str
    ) -> AuthorityRefusal:
        _ = (client, repository, item_id)
        return refusal

    monkeypatch.setattr(incident_drill_close, "read_history", unavailable_history)

    assert (
        close_drill(
            client=client,
            reading=reading,
            runner=_Forge(pr=_merged()),
            repo=tmp_path,
            repository=_REPOSITORY,
        )
        == refusal
    )


def test_late_generation_change_refuses_after_the_authority_close(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client, reading = _seed(snapshot=_attempt())
    calls = 0

    def current(**_: object) -> IncidentReading | AuthorityRefusal:
        nonlocal calls
        calls += 1
        return (
            reading
            if calls == 1
            else AuthorityRefusal(code="incident-generation-stale", detail=_ITEM)
        )

    monkeypatch.setattr(incident_drill_close, "require_current_generation", current)
    refused = close_drill(
        client=client,
        reading=reading,
        runner=_Forge(pr=_merged()),
        repo=tmp_path,
        repository=_REPOSITORY,
    )

    assert isinstance(refused, AuthorityRefusal)
    assert refused.code == "incident-generation-stale"


def test_lifecycle_claim_refusal_is_named(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client, reading = _seed(snapshot=_attempt())

    def claim_changed(**_: object) -> ClaimChangeResult:
        return ClaimChangeResult(outcome="claim-changed")

    monkeypatch.setattr(
        incident_drill_close,
        "change_claim",
        claim_changed,
    )

    refused = close_drill(
        client=client,
        reading=reading,
        runner=_Forge(pr=_merged()),
        repo=tmp_path,
        repository=_REPOSITORY,
    )

    assert isinstance(refused, AuthorityRefusal)
    assert (refused.code, refused.detail) == (
        "incident-drill-close-lifecycle-refused",
        "claim-changed",
    )
