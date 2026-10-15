"""The launch and completion arms a covered, writable store never reaches.

Every case here is a state the uncovered-refusal suite cannot produce, because
each one needs coverage to GRADE as verified and then needs something after the
grade to go wrong: a second call under one operation id, a store that cannot be
written, an effect that will not name what it launched, an attachment that
cannot be persisted. They are kept apart from the refusal suite for the reason
the launch module keeps the states apart — a refusal and an unfinished launch
are different facts with different remedies.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _session_obligation_launch
from livespec_orchestrator_beads_fabro.commands._session_obligation_coverage import (
    COVERAGE_UNMONITORED,
    COVERAGE_VERIFIED,
    DIAGNOSTIC_BUDGET_EXCEEDS_BOUND,
    CoverageDeclaration,
    CoverageReading,
    coverage_verdict,
)
from livespec_orchestrator_beads_fabro.commands._session_obligation_launch import (
    COMPLETION_PROTECTED,
    DIAGNOSTIC_ATTACHMENT_UNAVAILABLE,
    DIAGNOSTIC_INTENT_ALREADY_RECORDED,
    DIAGNOSTIC_INTENT_UNAVAILABLE,
    DIAGNOSTIC_TARGET_UNOBSERVED,
    LAUNCH_ATTACHMENT_PENDING,
    LAUNCH_PROTECTED,
    LAUNCH_REGISTRATION_UNAVAILABLE,
    protected_completion,
    protected_launch,
)
from livespec_orchestrator_beads_fabro.commands._session_obligation_records import (
    ATTACH_UNAVAILABLE,
    INTENT_UNAVAILABLE,
    LaunchAuthority,
    LaunchIntent,
    LaunchTarget,
    obligation_record_path,
    read_obligation_record,
)


class _Effect:
    """A launch effect recording every call, answering with a target or `None`."""

    def __init__(self, *, target: LaunchTarget | None = None) -> None:
        self.target = target
        self.calls: list[str] = []

    def __call__(self, *, operation_id: str) -> LaunchTarget | None:
        self.calls.append(operation_id)
        return self.target or LaunchTarget(kind="gate", identity=f"gate:/g:{operation_id}")


class _SilentEffect:
    """An effect that launches and cannot say what it launched."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, *, operation_id: str) -> LaunchTarget | None:
        self.calls.append(operation_id)
        return None


def _intent(*, repository: Path, operation_id: str) -> LaunchIntent:
    return LaunchIntent(
        operation_id=operation_id,
        authority=LaunchAuthority(
            session_id="session-l",
            repository=repository,
            invoker="role:dispatcher",
            scope="item:bd-ib-zejlae",
        ),
        required_result_identity="item_status bd-ib-zejlae status closed",
        result_epoch=5,
        original_deadline="2026-10-15T09:00:00Z",
    )


def _declaration(
    *,
    max_observation_interval_seconds: float = 20.0,
    takeover_budget_seconds: float = 20.0,
) -> CoverageDeclaration:
    return CoverageDeclaration(
        runtime="codex",
        runtime_version="0.58.0",
        terminal_backend="herdr",
        terminal_version="1.4.0",
        terminal_instance="tmux:/run/herdr.sock",
        service_identity="overseerd@hp",
        service_generation="1760500000",
        recovery_route="overseer-supervised-service",
        max_observation_interval_seconds=max_observation_interval_seconds,
        takeover_budget_seconds=takeover_budget_seconds,
        proof_artifact="scenario-160-capture",
    )


def _covered() -> CoverageReading:
    return CoverageReading(declaration=_declaration())


def test_a_second_launch_under_one_operation_id_performs_no_second_effect(
    *, tmp_path: Path
) -> None:
    store = tmp_path / "launch-obligations"
    intent = _intent(repository=tmp_path, operation_id="op-launch-1")
    first = protected_launch(
        intent=intent,
        coverage=_covered(),
        obligation_store_root=store,
        effect=_Effect(),
        now=10.0,
    )
    assert first.state == LAUNCH_PROTECTED
    second_effect = _Effect()

    second = protected_launch(
        intent=intent,
        coverage=_covered(),
        obligation_store_root=store,
        effect=second_effect,
        now=20.0,
    )

    assert second.state == LAUNCH_ATTACHMENT_PENDING
    assert second.protected is False
    assert second.diagnostic == DIAGNOSTIC_INTENT_ALREADY_RECORDED
    assert second.target is None
    assert second_effect.calls == []


def test_an_unwritable_obligation_store_refuses_before_any_effect(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unavailable(**_: object) -> str:
        return INTENT_UNAVAILABLE

    monkeypatch.setattr(_session_obligation_launch, "record_launch_intent", unavailable)
    effect = _Effect()

    verdict = protected_launch(
        intent=_intent(repository=tmp_path, operation_id="op-launch-2"),
        coverage=_covered(),
        obligation_store_root=tmp_path / "launch-obligations",
        effect=effect,
        now=10.0,
    )

    assert verdict.state == LAUNCH_REGISTRATION_UNAVAILABLE
    assert verdict.protected is False
    assert verdict.diagnostic == DIAGNOSTIC_INTENT_UNAVAILABLE
    assert verdict.coverage_state == COVERAGE_VERIFIED
    assert effect.calls == []


def test_an_effect_that_cannot_name_its_target_leaves_the_obligation_pending(
    *, tmp_path: Path
) -> None:
    store = tmp_path / "launch-obligations"
    effect = _SilentEffect()

    verdict = protected_launch(
        intent=_intent(repository=tmp_path, operation_id="op-launch-3"),
        coverage=_covered(),
        obligation_store_root=store,
        effect=effect,
        now=10.0,
    )

    assert verdict.state == LAUNCH_ATTACHMENT_PENDING
    assert verdict.protected is False
    assert verdict.diagnostic == DIAGNOSTIC_TARGET_UNOBSERVED
    assert effect.calls == ["op-launch-3"]
    payload = read_obligation_record(
        path=obligation_record_path(obligation_store_root=store, operation_id="op-launch-3")
    ).payload
    assert payload is not None
    assert payload["target"] is None


def test_an_unpersistable_attachment_is_pending_rather_than_protected(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unavailable(**_: object) -> str:
        return ATTACH_UNAVAILABLE

    monkeypatch.setattr(_session_obligation_launch, "attach_launch_target", unavailable)
    effect = _Effect()

    verdict = protected_launch(
        intent=_intent(repository=tmp_path, operation_id="op-launch-4"),
        coverage=_covered(),
        obligation_store_root=tmp_path / "launch-obligations",
        effect=effect,
        now=10.0,
    )

    assert verdict.state == LAUNCH_ATTACHMENT_PENDING
    assert verdict.protected is False
    assert verdict.diagnostic == DIAGNOSTIC_ATTACHMENT_UNAVAILABLE
    assert verdict.target is None
    assert effect.calls == ["op-launch-4"]


def test_completion_under_verified_coverage_names_its_outstanding_obligations(
    *, tmp_path: Path
) -> None:
    store = tmp_path / "launch-obligations"
    for index in (1, 2):
        _ = protected_launch(
            intent=_intent(repository=tmp_path, operation_id=f"op-complete-{index}"),
            coverage=_covered(),
            obligation_store_root=store,
            effect=_Effect(),
            now=float(index),
        )

    verdict = protected_completion(coverage=_covered(), obligation_store_root=store)

    assert verdict.state == COMPLETION_PROTECTED
    assert verdict.protected is True
    assert verdict.coverage_state == COVERAGE_VERIFIED
    assert verdict.diagnostic is None
    assert verdict.outstanding_operation_ids == ("op-complete-1", "op-complete-2")


@pytest.mark.parametrize(
    "budget",
    [float("inf"), 0.0, -1.0],
)
def test_a_budget_that_is_not_a_positive_finite_number_cannot_fit_the_bound(
    *, budget: float
) -> None:
    verdict = coverage_verdict(
        reading=CoverageReading(declaration=_declaration(max_observation_interval_seconds=budget))
    )

    assert verdict.state == COVERAGE_UNMONITORED
    assert verdict.verified is False
    assert verdict.diagnostic == DIAGNOSTIC_BUDGET_EXCEEDS_BOUND
