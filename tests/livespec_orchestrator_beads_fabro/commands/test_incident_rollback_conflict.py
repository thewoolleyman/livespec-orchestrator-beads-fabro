"""Failure recovery for the command-side rollback-conflict authority action."""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, IssueDraft
from livespec_orchestrator_beads_fabro._incident_authority_types import (
    AuthorityRefusal,
    IncidentAttempt,
    IncidentReading,
)
from livespec_orchestrator_beads_fabro._incident_entry import INCIDENT_CLAIM_METADATA_KEY
from livespec_orchestrator_beads_fabro._incident_recovery_plan import RecoveryPlan
from livespec_orchestrator_beads_fabro.commands import _incident_rollback_conflict as conflicts
from livespec_orchestrator_beads_fabro.incident_regression_recovery import RecoveryEntry


def _client(*, comments: tuple[str, ...] = ()) -> FakeBeadsClient:
    client = FakeBeadsClient()
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id="incident-1",
            issue_type="bug",
            title="incident",
            description="behavior",
            assignee=None,
            created_at="2026-11-08T00:00:00Z",
        )
    )
    for body in comments:
        client.add_comment(issue_id="incident-1", body=body)
    return client


def _attempt(*, phase: str = "rollback-conflict", generation: int = 3) -> IncidentAttempt:
    return IncidentAttempt(
        repository="owner/repository",
        item_id="incident-1",
        attempt_id="attempt-1",
        phase=phase,
        operation_id=f"operation-{generation}",
        generation=generation,
        owner="operator:alice",
        base="a" * 40,
        head="b" * 40,
        pr_number=1,
        landed_commits=("c" * 40,),
        landed_trees=("d" * 40,),
        original_paths=("app.py",),
        deferred_work=(),
        repayment_required=True,
    )


def _reading(*, attempt: IncidentAttempt) -> IncidentReading:
    return IncidentReading(
        attempt=attempt,
        committed_token_id=str(attempt.generation),
        current_token_id=str(attempt.generation + 1),
        is_current=True,
    )


def _record(*, attempt: IncidentAttempt) -> dict[str, object]:
    return {
        "schema": 1,
        "kind": "rollback-conflict",
        "item_id": attempt.item_id,
        "operation_id": attempt.operation_id,
        "generation": attempt.generation,
        "conflict": {"receipt": "owned-conflict", "release_condition": "controller-release"},
    }


def _commit(*, plan: RecoveryPlan, **_: object) -> RecoveryEntry:
    successor = plan.attempt
    return RecoveryEntry(
        reading=_reading(attempt=successor),
        operation_id=plan.operation_id,
        lifecycle_state=plan.lifecycle_state,
    )


def _resolution(*, receipt: bool = False) -> conflicts.RollbackResolution:
    return conflicts.RollbackResolution(
        release_condition="controller-release",
        revert_receipt_id="controller-receipt" if receipt else "",
        revert_commit="e" * 40 if receipt else "",
    )


def _stale_commit(**_: object) -> AuthorityRefusal:
    return AuthorityRefusal(code="incident-generation-stale", detail="test")


def _lifecycle_refusal(**_: object) -> AuthorityRefusal:
    return AuthorityRefusal(
        code="incident-rollback-conflict-lifecycle-refused", detail="claim-changed"
    )


def _current_refusal(**_: object) -> AuthorityRefusal:
    return AuthorityRefusal(code="incident-generation-stale", detail="test")


def _claim_success(**_: object) -> None:
    return None


def test_rollback_conflict_refuses_incomplete_receipts_and_unknown_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempt = _attempt()
    monkeypatch.setattr(conflicts, "_commit", _commit)
    missing = conflicts.resolve_rollback_conflict(
        client=_client(comments=(conflicts.RECOVERY_MARKER + "not json",)),
        reading=_reading(attempt=attempt),
        resolution=_resolution(),
    )
    assert isinstance(missing, AuthorityRefusal)
    assert missing.code == "incident-rollback-conflict-record-missing"
    invalid = conflicts.resolve_rollback_conflict(
        client=_client(comments=(conflicts.recovery_comment(record=_record(attempt=attempt)),)),
        reading=_reading(attempt=attempt),
        resolution=conflicts.RollbackResolution(
            release_condition="controller-release",
            revert_receipt_id="controller-receipt",
            revert_commit="",
        ),
    )
    assert isinstance(invalid, AuthorityRefusal)
    assert invalid.code == "incident-rollback-conflict-revert-receipt-invalid"


def test_rollback_conflict_propagates_transition_and_lifecycle_refusals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempt = _attempt()
    client = _client(comments=(conflicts.recovery_comment(record=_record(attempt=attempt)),))
    monkeypatch.setattr(conflicts, "_commit", _stale_commit)
    stale = conflicts.resolve_rollback_conflict(
        client=client, reading=_reading(attempt=attempt), resolution=_resolution()
    )
    assert isinstance(stale, AuthorityRefusal)
    assert stale.code == "incident-generation-stale"
    monkeypatch.setattr(conflicts, "_commit", _commit)
    monkeypatch.setattr(conflicts, "require_current_generation", _current_refusal)
    current = conflicts.resolve_rollback_conflict(
        client=client, reading=_reading(attempt=attempt), resolution=_resolution()
    )
    assert isinstance(current, AuthorityRefusal)
    assert current.code == "incident-generation-stale"
    monkeypatch.undo()
    monkeypatch.setattr(conflicts, "_commit", _commit)
    monkeypatch.setattr(conflicts, "_claim", _lifecycle_refusal)
    refused = conflicts.resolve_rollback_conflict(
        client=client, reading=_reading(attempt=attempt), resolution=_resolution(receipt=True)
    )
    assert isinstance(refused, AuthorityRefusal)
    assert refused.code == "incident-rollback-conflict-lifecycle-refused"
    wrong_phase = conflicts.resolve_rollback_conflict(
        client=client,
        reading=_reading(attempt=_attempt(phase="collecting-failures")),
        resolution=_resolution(),
    )
    assert isinstance(wrong_phase, AuthorityRefusal)
    assert wrong_phase.code == "incident-rollback-conflict-not-eligible"
    monkeypatch.setattr(conflicts, "_claim", _claim_success)
    reverting = _attempt(phase="reverting", generation=2)
    # The current reverting generation holds the item claim, as a completed reopen leaves it.
    client.update_issue(
        issue_id="incident-1",
        metadata={
            INCIDENT_CLAIM_METADATA_KEY: {
                "operation_id": reverting.operation_id,
                "generation": reverting.generation,
                "owner": reverting.owner,
            }
        },
    )
    recorded = conflicts.record_rollback_conflict(
        client=client,
        reading=_reading(attempt=reverting),
        conflict=conflicts.RollbackConflict(
            receipt="owned-conflict", release_condition="controller-release"
        ),
    )
    assert isinstance(recorded, RecoveryEntry)
    assert recorded.reading.attempt.phase == "rollback-conflict"
