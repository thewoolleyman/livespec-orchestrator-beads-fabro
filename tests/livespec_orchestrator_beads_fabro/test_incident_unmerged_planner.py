"""The unmerged-correction planner refuses a stale or unbound reading before any fact.

bd-ib-elq5ry. The `correct-unmerged-attempt` entrance checks eligibility before
it reads the forge, so this pure-planner guard is exercised directly.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro._incident_authority_payload import decode_attempt
from livespec_orchestrator_beads_fabro._incident_authority_types import (
    AuthorityRefusal,
    IncidentReading,
)
from livespec_orchestrator_beads_fabro._incident_recovery_correction import Correction
from livespec_orchestrator_beads_fabro._incident_unmerged_correction import (
    UnmergedFailure,
    plan_unmerged_correction,
)

REPAIR_BRANCH = "incident/test-incident-attempt-1"
FAILED_HEAD = "b" * 40
FAILED_RUN = "pr-run-5"
CORRECTED_REF = "refs/heads/incident/test-incident-attempt-2"


def _bound() -> IncidentReading:
    attempt = decode_attempt(
        value=dict(
            repository="owner/repository",
            item_id="test-incident",
            attempt_id="attempt-1",
            phase="repair",
            operation_id="bind-1",
            generation=2,
            owner="operator:alice",
            base="a" * 40,
            head=FAILED_HEAD,
            pr_number=7,
            landed_commits=[],
            landed_trees=[],
            original_paths=["app.py"],
            deferred_work=[],
            repayment_required=True,
            carrier=dict(
                state="pr-bound",
                target_ref="refs/heads/" + REPAIR_BRANCH,
                input_parent="a" * 40,
                staged_tree="c" * 40,
                remote_head=FAILED_HEAD,
            ),
        )
    )
    assert attempt is not None
    tokens = {"committed_token_id": "wisp-1", "current_token_id": "wisp-2"}
    return IncidentReading(attempt=attempt, is_current=True, **tokens)


def test_the_pure_planner_refuses_a_stale_or_unbound_reading_without_consulting_the_facts() -> None:
    bound = _bound()
    observed = UnmergedFailure(
        pr_number=7,
        pr_state="CLOSED",
        head_ref=REPAIR_BRANCH,
        pr_head=FAILED_HEAD,
        run_id=FAILED_RUN,
        run_head=FAILED_HEAD,
        run_conclusion="failure",
        run_complete=True,
    )
    correction = Correction(
        kind="repair",
        evidence_id="lloc-split-commit",
        base="a" * 40,
        head="1" * 40,
        staged_tree="2" * 40,
    )
    plans = [
        plan_unmerged_correction(
            reading=reading,
            observed=observed,
            prior=(),
            correction=correction,
            target_ref=CORRECTED_REF,
        )
        for reading in (
            IncidentReading(
                attempt=bound.attempt,
                committed_token_id=bound.committed_token_id,
                current_token_id=bound.current_token_id,
                is_current=False,
            ),
            bound,
        )
    ]
    assert [plan.code if isinstance(plan, AuthorityRefusal) else "planned" for plan in plans] == [
        "incident-correction-not-eligible",
        "planned",
    ]
