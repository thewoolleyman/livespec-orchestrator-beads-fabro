"""Tests for the value the shared result reader answers with."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._plan_result_observation import (
    OBSERVATION_SATISFIED,
    OBSERVATION_UNSATISFIED,
    SOURCE_LEDGER,
    satisfied,
    unsatisfied,
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


def test_the_status_names_are_the_three_the_clause_enumerates() -> None:
    """The literal spellings, bound here because one caller spells them by hand.

    `tests/integration/test_plan_result_reader_scenario146.py` writes the
    non-satisfied statuses as literals rather than importing them, so that a Red
    for a status that does not exist yet fails on its assertion instead of dying at
    collection. This assertion is what keeps that literal honest: a renamed
    constant fails here rather than drifting past a test that would still pass.
    """
    assert OBSERVATION_SATISFIED == "satisfied"
    assert OBSERVATION_UNSATISFIED == "unsatisfied"


def test_an_unsatisfied_observation_is_a_confident_negative_with_its_evidence() -> None:
    """The unmet reading carries what WAS observed, not merely that it was not met.

    Without the evidence an operator cannot tell a target that has not moved from
    an instrument that was pointed somewhere else — and those have opposite
    remedies.
    """
    observation = unsatisfied(
        repo="repo",
        target="item_status bd-ib-1 status done",
        source=SOURCE_LEDGER,
        now="2026-10-08T12:00:00Z",
        evidence="ledger record bd-ib-1 at status ready",
        detail="the ledger reports bd-ib-1 at status ready, not the expected done",
    )
    assert observation.status == OBSERVATION_UNSATISFIED
    assert observation.evidence == "ledger record bd-ib-1 at status ready"
    assert observation.outstanding is True
