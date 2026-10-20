"""A stale pointer and a failed local gate are reconciled before any action is chosen.

Scenario 163 of `SPECIFICATION/scenarios.md`: the consumer "re-reads scope,
authorization, safety, epoch, ledger, forge and recorded remote factory", then
"selects a typed sanctioned action based on current authoritative evidence", and
"no blind redispatch follows solely from the local gate failure".
"""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro.commands._session_recovery_action import (
    ACTION_NONE_AUTHORIZED,
    ACTION_SELECTED,
    ACTION_STALE_EPOCH,
    ACTION_UNAUTHORIZED,
    ACTION_UNOBSERVABLE,
    DIAGNOSTIC_FORGE_UNOBSERVABLE,
    DIAGNOSTIC_LEDGER_UNOBSERVABLE,
    DIAGNOSTIC_LOCAL_GATE_FAILED,
    DIAGNOSTIC_REMOTE_FACTORY_UNOBSERVABLE,
    GATE_FAILED,
    REASON_AUTHORIZED_DIAGNOSIS,
    REASON_LEDGER_READY,
    REASON_MERGED_PULL_REQUEST,
    REASON_STALE_DIAGNOSTIC_COMPLETED,
    AuthoritativeEvidence,
    Reading,
    sanctioned_operation,
    select_sanctioned_action,
)

_ITEM = "bd-ib-dle6l3"
_EPIC = "bd-ib-jnpvh4"
_STALE_DIAGNOSIS = f"diagnose-plan-progress:{_EPIC}"

_ACTIVE = Reading(value="active")
_NO_MERGE = Reading(value="")
_REMOTE_SUCCEEDED = Reading(value="succeeded")
_READY = Reading(value="ready")
_UNOBSERVED = Reading(value=None)


def _evidence(
    *,
    item_id: str = _ITEM,
    ledger_status: Reading = _ACTIVE,
    merged_pull_request: Reading = _NO_MERGE,
    remote_run_outcome: Reading = _REMOTE_SUCCEEDED,
    recorded_next_operation: str = _STALE_DIAGNOSIS,
    recorded_operation_completed: bool = True,
    local_gate_outcome: str = GATE_FAILED,
    recorded_epoch: int = 9,
    current_epoch: int = 9,
) -> AuthoritativeEvidence:
    return AuthoritativeEvidence(
        item_id=item_id,
        epic_id=_EPIC,
        recorded_next_operation=recorded_next_operation,
        recorded_operation_completed=recorded_operation_completed,
        ledger_status=ledger_status,
        merged_pull_request=merged_pull_request,
        remote_run_outcome=remote_run_outcome,
        local_gate_outcome=local_gate_outcome,
        recorded_epoch=recorded_epoch,
        current_epoch=current_epoch,
    )


def test_a_failed_gate_whose_remote_pull_request_merged_selects_the_per_item_reconcile() -> None:
    """The measured 2026-10-09 case: the gate reported FAILED after the PR had merged."""
    selected = select_sanctioned_action(
        evidence=_evidence(merged_pull_request=Reading(value="9117b1c8"))
    )

    assert selected.state == ACTION_SELECTED
    assert selected.authorized
    assert selected.operation == f"reconcile-merged:{_ITEM}"
    assert selected.reason == REASON_MERGED_PULL_REQUEST
    assert DIAGNOSTIC_LOCAL_GATE_FAILED in selected.diagnostics


def test_the_local_gate_outcome_never_decides_the_action_it_is_only_reported() -> None:
    """A failed local gate is not proof its remote run or merged PR failed."""
    merged = Reading(value="9117b1c8")

    failed = select_sanctioned_action(
        evidence=_evidence(merged_pull_request=merged, local_gate_outcome=GATE_FAILED)
    )
    succeeded = select_sanctioned_action(
        evidence=_evidence(merged_pull_request=merged, local_gate_outcome="succeeded")
    )

    assert failed.operation == succeeded.operation
    assert failed.reason == succeeded.reason
    assert DIAGNOSTIC_LOCAL_GATE_FAILED in failed.diagnostics
    assert DIAGNOSTIC_LOCAL_GATE_FAILED not in succeeded.diagnostics


def test_a_stale_completed_diagnostic_is_refreshed_rather_than_repeated() -> None:
    refreshed = select_sanctioned_action(evidence=_evidence(ledger_status=_READY))

    assert refreshed.state == ACTION_SELECTED
    assert refreshed.operation == f"impl:{_ITEM}"
    assert refreshed.reason == REASON_LEDGER_READY
    assert refreshed.operation != _STALE_DIAGNOSIS


def test_a_completed_diagnostic_with_nothing_else_authorized_repeats_nothing() -> None:
    exhausted = select_sanctioned_action(evidence=_evidence())

    assert exhausted.state == ACTION_NONE_AUTHORIZED
    assert exhausted.operation is None
    assert exhausted.reason == REASON_STALE_DIAGNOSTIC_COMPLETED


def test_an_expired_obligation_starts_authorized_diagnosis_rather_than_a_human_block() -> None:
    diagnosis = select_sanctioned_action(
        evidence=_evidence(
            recorded_next_operation=f"impl:{_ITEM}", recorded_operation_completed=False
        )
    )

    assert diagnosis.state == ACTION_SELECTED
    assert diagnosis.operation == _STALE_DIAGNOSIS
    assert diagnosis.reason == REASON_AUTHORIZED_DIAGNOSIS


def test_an_epoch_that_has_moved_selects_nothing_at_all() -> None:
    stale = select_sanctioned_action(
        evidence=_evidence(recorded_epoch=9, current_epoch=10, ledger_status=_READY)
    )

    assert stale.state == ACTION_STALE_EPOCH
    assert stale.operation is None


@pytest.mark.parametrize(
    ("unreadable", "diagnostic"),
    [
        ({"ledger_status": _UNOBSERVED}, DIAGNOSTIC_LEDGER_UNOBSERVABLE),
        (
            {"ledger_status": _READY, "merged_pull_request": _UNOBSERVED},
            DIAGNOSTIC_FORGE_UNOBSERVABLE,
        ),
        (
            {"ledger_status": _READY, "remote_run_outcome": _UNOBSERVED},
            DIAGNOSTIC_REMOTE_FACTORY_UNOBSERVABLE,
        ),
    ],
)
def test_any_unreadable_authority_retains_uncertainty_instead_of_choosing(
    *, unreadable: dict[str, Reading], diagnostic: str
) -> None:
    uncertain = select_sanctioned_action(evidence=_evidence(**unreadable))

    assert uncertain.state == ACTION_UNOBSERVABLE
    assert uncertain.operation is None
    assert diagnostic in uncertain.diagnostics


def test_an_unsanctioned_derived_operation_authorizes_nothing() -> None:
    unauthorized = select_sanctioned_action(
        evidence=_evidence(
            item_id="I will try a different approach.",
            ledger_status=_READY,
            local_gate_outcome="succeeded",
        )
    )

    assert unauthorized.state == ACTION_UNAUTHORIZED
    assert unauthorized.operation is None


@pytest.mark.parametrize(
    ("operation", "sanctioned"),
    [
        (f"reconcile-merged:{_ITEM}", True),
        (f"impl:{_ITEM}", True),
        (_STALE_DIAGNOSIS, True),
        ("revise:agent-session-stall-prevention", True),
        ("reconcile-merged:", False),
        ("reconcile merged bd-ib-dle6l3", False),
        ("I will try a different approach.", False),
        ("diagnose-this-is-not-a-supported-operation", False),
    ],
)
def test_the_sanctioned_grammar_is_closed(*, operation: str, sanctioned: bool) -> None:
    assert sanctioned_operation(operation=operation) is sanctioned


def test_a_reading_that_could_not_be_taken_is_not_an_empty_reading() -> None:
    assert _NO_MERGE.observable
    assert not _UNOBSERVED.observable
