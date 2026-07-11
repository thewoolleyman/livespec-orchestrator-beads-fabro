"""Unit coverage for full autonomous mode's two-valve collapse decisions (S3).

Covers
`livespec_orchestrator_beads_fabro.commands._dispatcher_autonomous_collapse`,
the PURE armed-mode override layer over the base admission/acceptance valves.
Pins SPECIFICATION/scenarios.md Scenario 33 (armed collapses a routine manual
approve gate to auto), Scenario 34 (armed collapses an ai-then-human acceptance
to ai-only), and Scenario 36's two escape hatches (a design-human-gated
spec-change-tier slice stays escalated; a human-only acceptance still parks),
plus the invariant that a NOT-armed run is exactly the base decision.
"""

from __future__ import annotations

from dataclasses import replace

from livespec_orchestrator_beads_fabro.commands._dispatcher_autonomous_collapse import (
    acceptance_decision_under_mode,
    collapse_acceptance_to_ai_only,
    collapse_admission_to_auto,
    effective_admission_policy_under_mode,
    is_spec_change_tier,
)
from livespec_orchestrator_beads_fabro.types import WorkItem


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id="bd-ib-c1",
        type="task",
        status="pending-approval",
        title="A routine slice",
        description="Do the thing.",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-06-11T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="manual",
        acceptance_policy="ai-then-human",
    )
    return replace(base, **overrides)


# ---------------------------------------------------------------------------
# is_spec_change_tier — the conservative spec-change backstop signal
# ---------------------------------------------------------------------------


def test_is_spec_change_tier_true_when_spec_commitment_linked() -> None:
    assert is_spec_change_tier(item=_item(spec_commitment_hint="pc4-followup-3")) is True


def test_is_spec_change_tier_false_when_no_spec_linkage() -> None:
    assert is_spec_change_tier(item=_item(spec_commitment_hint=None)) is False


# ---------------------------------------------------------------------------
# collapse_admission_to_auto — the approve-gate collapse (Scenarios 33, 36)
# ---------------------------------------------------------------------------


def test_collapse_admission_true_for_routine_manual_armed() -> None:
    # Scenario 33: a routine manual pending item collapses under an armed run.
    assert collapse_admission_to_auto(item=_item(admission_policy="manual"), armed=True) is True


def test_collapse_admission_true_for_default_none_policy_armed() -> None:
    # admission_policy None inherits the safe `manual` default; still collapses.
    assert collapse_admission_to_auto(item=_item(admission_policy=None), armed=True) is True


def test_collapse_admission_false_when_not_armed() -> None:
    assert collapse_admission_to_auto(item=_item(admission_policy="manual"), armed=False) is False


def test_collapse_admission_false_when_not_pending() -> None:
    item = _item(status="ready", admission_policy="manual")
    assert collapse_admission_to_auto(item=item, armed=True) is False


def test_collapse_admission_false_when_already_auto() -> None:
    assert collapse_admission_to_auto(item=_item(admission_policy="auto"), armed=True) is False


def test_collapse_admission_false_for_spec_change_tier() -> None:
    # Scenario 36 design-human-gated leg: a spec-change-tier slice stays
    # escalated (held), never auto-approved, even under an armed run.
    item = _item(admission_policy="manual", spec_commitment_hint="pc4-followup-3")
    assert collapse_admission_to_auto(item=item, armed=True) is False


# ---------------------------------------------------------------------------
# effective_admission_policy_under_mode — the injected resolver
# ---------------------------------------------------------------------------


def test_effective_admission_policy_under_mode_collapses_to_auto() -> None:
    item = _item(admission_policy="manual")
    assert effective_admission_policy_under_mode(item=item, armed=True) == "auto"


def test_effective_admission_policy_under_mode_base_when_not_armed() -> None:
    item = _item(admission_policy="manual")
    assert effective_admission_policy_under_mode(item=item, armed=False) == "manual"


def test_effective_admission_policy_under_mode_base_for_spec_change_tier() -> None:
    item = _item(admission_policy="manual", spec_commitment_hint="pc4-followup-3")
    assert effective_admission_policy_under_mode(item=item, armed=True) == "manual"


# ---------------------------------------------------------------------------
# collapse_acceptance_to_ai_only — the acceptance collapse (Scenarios 34, 36)
# ---------------------------------------------------------------------------


def test_collapse_acceptance_true_for_ai_then_human_armed() -> None:
    # Scenario 34: an ai-then-human item collapses to ai-only under an armed run.
    item = _item(acceptance_policy="ai-then-human")
    assert collapse_acceptance_to_ai_only(item=item, armed=True) is True


def test_collapse_acceptance_true_for_default_none_policy_armed() -> None:
    # acceptance_policy None inherits the safe `ai-then-human` default.
    assert collapse_acceptance_to_ai_only(item=_item(acceptance_policy=None), armed=True) is True


def test_collapse_acceptance_false_when_not_armed() -> None:
    item = _item(acceptance_policy="ai-then-human")
    assert collapse_acceptance_to_ai_only(item=item, armed=False) is False


def test_collapse_acceptance_false_for_human_only_armed() -> None:
    # Scenario 36 human-only leg: a deliberate human gate is never collapsed.
    item = _item(acceptance_policy="human-only")
    assert collapse_acceptance_to_ai_only(item=item, armed=True) is False


def test_collapse_acceptance_false_for_already_ai_only_armed() -> None:
    item = _item(acceptance_policy="ai-only")
    assert collapse_acceptance_to_ai_only(item=item, armed=True) is False


# ---------------------------------------------------------------------------
# acceptance_decision_under_mode — the layered acceptance decision
# ---------------------------------------------------------------------------


def test_acceptance_decision_under_mode_collapses_to_done() -> None:
    decision = acceptance_decision_under_mode(
        item=_item(acceptance_policy="ai-then-human"), armed=True
    )
    assert (decision.policy, decision.to_done) == ("ai-only", True)


def test_acceptance_decision_under_mode_parks_when_not_armed() -> None:
    decision = acceptance_decision_under_mode(
        item=_item(acceptance_policy="ai-then-human"), armed=False
    )
    assert (decision.policy, decision.to_done) == ("ai-then-human", False)


def test_acceptance_decision_under_mode_human_only_always_parks() -> None:
    # A human-only gate parks whether or not the run is armed (Scenario 36).
    for armed in (True, False):
        decision = acceptance_decision_under_mode(
            item=_item(acceptance_policy="human-only"), armed=armed
        )
        assert (decision.policy, decision.to_done) == ("human-only", False)
