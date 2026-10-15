"""Missing or unsupported recovery coverage refuses as unmonitored, never as protected."""

from __future__ import annotations

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._session_obligation_coverage import (
    COVERAGE_UNMONITORED,
    COVERAGE_UNOBSERVABLE,
    DIAGNOSTIC_BUDGET_EXCEEDS_BOUND,
    DIAGNOSTIC_COVERAGE_UNREADABLE,
    DIAGNOSTIC_IDENTITY_UNBOUND,
    DIAGNOSTIC_OWNER_ABSENT,
    DIAGNOSTIC_ROUTE_UNSUPPORTED,
    DIAGNOSTIC_SELF_DECLARED,
    CoverageDeclaration,
    CoverageReading,
)
from livespec_orchestrator_beads_fabro.commands._session_obligation_launch import (
    COMPLETION_UNMONITORED,
    COMPLETION_UNOBSERVABLE,
    LAUNCH_UNMONITORED,
    LAUNCH_UNOBSERVABLE,
    protected_completion,
    protected_launch,
)
from livespec_orchestrator_beads_fabro.commands._session_obligation_records import (
    LaunchAuthority,
    LaunchIntent,
    LaunchTarget,
    obligation_record_path,
    outstanding_obligations,
)


class _Effect:
    """A launch effect that records every call it was asked to make."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, *, operation_id: str) -> LaunchTarget | None:
        self.calls.append(operation_id)
        return LaunchTarget(kind="gate", identity=f"gate:/g:{operation_id}")


def _intent(*, repository: Path, operation_id: str) -> LaunchIntent:
    return LaunchIntent(
        operation_id=operation_id,
        authority=LaunchAuthority(
            session_id="session-u",
            repository=repository,
            invoker="role:coordinator",
            scope="item:bd-ib-zejlae",
        ),
        required_result_identity="item_status bd-ib-zejlae status closed",
        result_epoch=2,
        original_deadline="2026-10-15T08:00:00Z",
    )


def _declaration(
    *,
    service_identity: str = "overseerd@hp",
    recovery_route: str = "overseer-supervised-service",
    max_observation_interval_seconds: float = 20.0,
    takeover_budget_seconds: float = 20.0,
    terminal_instance: str = "tmux:/run/herdr.sock",
) -> CoverageDeclaration:
    return CoverageDeclaration(
        runtime="codex",
        runtime_version="0.58.0",
        terminal_backend="herdr",
        terminal_version="1.4.0",
        terminal_instance=terminal_instance,
        service_identity=service_identity,
        service_generation="1760500000",
        recovery_route=recovery_route,
        max_observation_interval_seconds=max_observation_interval_seconds,
        takeover_budget_seconds=takeover_budget_seconds,
        proof_artifact="scenario-160-capture",
    )


@pytest.mark.parametrize(
    ("reading", "expected_diagnostic"),
    [
        (CoverageReading(declaration=None), DIAGNOSTIC_OWNER_ABSENT),
        (
            CoverageReading(declaration=_declaration(recovery_route="ad-hoc-pane-nudge")),
            DIAGNOSTIC_ROUTE_UNSUPPORTED,
        ),
        (
            CoverageReading(declaration=_declaration(service_identity="4821")),
            DIAGNOSTIC_SELF_DECLARED,
        ),
        (
            CoverageReading(
                declaration=_declaration(
                    max_observation_interval_seconds=45.0, takeover_budget_seconds=30.0
                )
            ),
            DIAGNOSTIC_BUDGET_EXCEEDS_BOUND,
        ),
        (
            CoverageReading(declaration=_declaration(terminal_instance="   ")),
            DIAGNOSTIC_IDENTITY_UNBOUND,
        ),
    ],
)
def test_uncovered_launch_refuses_as_unmonitored_without_launching(
    *, tmp_path: Path, reading: CoverageReading, expected_diagnostic: str
) -> None:
    store = tmp_path / "launch-obligations"
    effect = _Effect()

    verdict = protected_launch(
        intent=_intent(repository=tmp_path, operation_id="op-unmonitored"),
        coverage=reading,
        obligation_store_root=store,
        effect=effect,
        now=10.0,
    )

    assert verdict.state == LAUNCH_UNMONITORED
    assert verdict.protected is False
    assert verdict.coverage_state == COVERAGE_UNMONITORED
    assert verdict.diagnostic == expected_diagnostic
    assert effect.calls == []
    assert not obligation_record_path(
        obligation_store_root=store, operation_id="op-unmonitored"
    ).exists()


def test_an_unreadable_coverage_reading_is_unobservable_rather_than_unmonitored(
    *, tmp_path: Path
) -> None:
    effect = _Effect()

    verdict = protected_launch(
        intent=_intent(repository=tmp_path, operation_id="op-unobservable"),
        coverage=CoverageReading(declaration=None, diagnostic=DIAGNOSTIC_COVERAGE_UNREADABLE),
        obligation_store_root=tmp_path / "launch-obligations",
        effect=effect,
        now=10.0,
    )

    assert verdict.state == LAUNCH_UNOBSERVABLE
    assert verdict.protected is False
    assert verdict.coverage_state == COVERAGE_UNOBSERVABLE
    assert verdict.diagnostic == DIAGNOSTIC_COVERAGE_UNREADABLE
    assert effect.calls == []


def test_completion_with_no_recovery_owner_reports_unmonitored_not_protected(
    *, tmp_path: Path
) -> None:
    store = tmp_path / "launch-obligations"
    launched = protected_launch(
        intent=_intent(repository=tmp_path, operation_id="op-completion-1"),
        coverage=CoverageReading(declaration=_declaration()),
        obligation_store_root=store,
        effect=_Effect(),
        now=10.0,
    )
    assert launched.protected is True

    verdict = protected_completion(
        coverage=CoverageReading(declaration=None),
        obligation_store_root=store,
    )

    assert verdict.state == COMPLETION_UNMONITORED
    assert verdict.protected is False
    assert verdict.coverage_state == COVERAGE_UNMONITORED
    assert verdict.diagnostic == DIAGNOSTIC_OWNER_ABSENT
    assert verdict.outstanding_operation_ids == ("op-completion-1",)


def test_completion_with_unreadable_coverage_is_unobservable(*, tmp_path: Path) -> None:
    verdict = protected_completion(
        coverage=CoverageReading(declaration=None, diagnostic=DIAGNOSTIC_COVERAGE_UNREADABLE),
        obligation_store_root=tmp_path / "launch-obligations",
    )

    assert verdict.state == COMPLETION_UNOBSERVABLE
    assert verdict.protected is False
    assert verdict.coverage_state == COVERAGE_UNOBSERVABLE
    assert verdict.diagnostic == DIAGNOSTIC_COVERAGE_UNREADABLE


def test_an_unreadable_obligation_store_is_unobservable_rather_than_no_obligations(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = tmp_path / "launch-obligations"
    store.mkdir()

    def refuse(_self: Path, _pattern: str) -> list[Path]:
        raise OSError("store unreadable")

    monkeypatch.setattr(Path, "glob", refuse)
    census = outstanding_obligations(obligation_store_root=store)
    assert census.records == ()

    verdict = protected_completion(
        coverage=CoverageReading(declaration=_declaration()),
        obligation_store_root=store,
    )

    assert verdict.state == COMPLETION_UNOBSERVABLE
    assert verdict.protected is False
    assert verdict.diagnostic == census.diagnostics[0]
    assert verdict.outstanding_operation_ids == ()
