"""Tests for the value the shared result reader answers with."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._plan_result_observation import (
    OBSERVATION_SATISFIED,
    SOURCE_LEDGER,
    satisfied,
)


def test_a_satisfied_observation_carries_every_field_the_clause_requires() -> None:
    observation = satisfied(
        repo="repo",
        target="item_status bd-ib-1 status done",
        source=SOURCE_LEDGER,
        now="2026-10-08T12:00:00Z",
        evidence="ledger record bd-ib-1 at status done",
        detail="the ledger reports bd-ib-1 at the expected status done",
    )
    assert observation.status == OBSERVATION_SATISFIED
    assert observation.repo == "repo"
    assert observation.target == "item_status bd-ib-1 status done"
    assert observation.source == SOURCE_LEDGER
    assert observation.observed_at == "2026-10-08T12:00:00Z"
    assert observation.evidence == "ledger record bd-ib-1 at status done"
    assert "expected status done" in observation.detail


def test_a_satisfied_result_leaves_no_obligation_outstanding() -> None:
    """`outstanding` asks whether the reading is anything OTHER than satisfied.

    The question is deliberately not "is it unsatisfied": the clause requires an
    unobservable reading to preserve the budget and refuse any transition claiming
    completion, and a caller asking the narrower question would read FALSE for an
    obligation that is very much outstanding.
    """
    observation = satisfied(
        repo="repo",
        target="t",
        source=SOURCE_LEDGER,
        now="2026-10-08T12:00:00Z",
        evidence="e",
        detail="d",
    )
    assert observation.outstanding is False
