"""A drill-closed chain is terminal: a named drill closure, never repayment or `closed`."""

from __future__ import annotations

from dataclasses import replace

from livespec_orchestrator_beads_fabro._incident_authority_types import IncidentAttempt
from livespec_orchestrator_beads_fabro._incident_completion_rules import (
    DRILL_CLOSED_OBLIGATION,
    IncidentCompletionEvidence,
    completion_obligations,
)


def _attempt(*, phase: str) -> IncidentAttempt:
    return IncidentAttempt(
        repository="owner/repository",
        item_id="bd-ib-drill",
        attempt_id="drill-1",
        phase=phase,
        operation_id=f"drill-1#{phase}",
        generation=2,
        owner="operator:alice",
        base="a" * 40,
        head="b" * 40,
        pr_number=7,
        landed_commits=("c" * 40,),
        landed_trees=("d" * 40,),
        original_paths=("app.py",),
        deferred_work=("normal-factory-proof",),
        repayment_required=False,
    )


def test_a_drill_closed_chain_reads_as_one_named_drill_closure_not_repayment() -> None:
    evidence = IncidentCompletionEvidence()

    assert completion_obligations(history=(_attempt(phase="drill-closed"),), evidence=evidence) == (
        DRILL_CLOSED_OBLIGATION,
    )


def test_a_closed_chain_still_owes_nothing_and_an_empty_chain_is_named() -> None:
    evidence = IncidentCompletionEvidence()
    closed = replace(_attempt(phase="closed"), repayment_required=True)

    assert completion_obligations(history=(closed,), evidence=evidence) == ()
    assert completion_obligations(history=(), evidence=evidence) == ("incident-history-empty",)
