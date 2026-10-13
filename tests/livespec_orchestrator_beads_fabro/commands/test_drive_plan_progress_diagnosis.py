"""The plan-progress diagnosis executor's router guard and its one literal.

`tests/integration/test_plan_legacy_tracking_scenario148.py` drives the
executor end to end through the real `drive` router over a fixture tenant. This
module covers the two things that tier cannot show: which action ids the router
claims, and that the prefix it claims is the SAME literal the recovery grammar
admits as executable.

That second case is the one worth keeping. The resume EXPOSES this operation and
the recovery validator ADMITS it, so two spellings of one token would let a
resume hand out an action the router then rejects as unknown — a dead end whose
only symptom is an operator running a suggested command and being told it does
not exist.
"""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro.commands._drive_plan_progress_diagnosis import (
    PLAN_PROGRESS_DIAGNOSIS_PREFIX,
    is_plan_progress_diagnosis_action,
)
from livespec_orchestrator_beads_fabro.commands._plan_progress_resume import (
    diagnosis_operation,
)
from livespec_orchestrator_beads_fabro.commands._plan_recovery import (
    is_executable_operation,
)

_EPIC_ID = "bd-ib-diagnosisepic"


def test_the_router_claims_a_well_formed_diagnosis_action() -> None:
    assert is_plan_progress_diagnosis_action(
        action_id=f"{PLAN_PROGRESS_DIAGNOSIS_PREFIX}{_EPIC_ID}"
    )


@pytest.mark.parametrize(
    "action_id",
    [
        "",
        "impl:bd-ib-diagnosisepic",
        "diagnose-plan-progress",
        PLAN_PROGRESS_DIAGNOSIS_PREFIX,
        f"{PLAN_PROGRESS_DIAGNOSIS_PREFIX}   ",
        "diagnose-something-else:bd-ib-diagnosisepic",
    ],
)
def test_the_router_claims_nothing_else(action_id: str) -> None:
    """An EMPTY epic id is refused rather than claimed and run on nothing.

    Claiming it would resolve a store and read an obligation for the empty
    string, which answers with a confident missing-tracking finding about an
    epic that does not exist.
    """
    assert is_plan_progress_diagnosis_action(action_id=action_id) is False


def test_the_exposed_operation_is_exactly_the_one_the_router_claims() -> None:
    """The three surfaces agree on one literal, asserted as a round trip.

    The resume composes the operation, the recovery grammar admits it, and the
    router claims it. Any two of those drifting apart is invisible until an
    operator runs the action a finding told them to run.
    """
    exposed = diagnosis_operation(epic_id=_EPIC_ID)

    assert is_plan_progress_diagnosis_action(action_id=exposed)
    assert is_executable_operation(operation=exposed)
