"""Unit + property coverage for the Dispatcher admission/acceptance valves.

Covers `livespec_orchestrator_beads_fabro.commands._dispatcher_valves`, the
PURE planning layer behind the Dispatcher's approval/admission valves
(`pending-approval -> ready`, then mechanical `ready -> active`) and
post-merge acceptance (`acceptance -> done`), plus the per-repo WIP-cap read.
The integration-tier journeys that drive these
through the real store/client seam (Scenarios 22-25) live in
`tests/integration/test_dispatcher_admission_acceptance_scenarios22_25.py`;
this module pins the pure decision functions exhaustively (every branch) plus
a Hypothesis invariant on the admission planner.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from livespec_orchestrator_beads_fabro.commands._dispatcher_valves import (
    DEFAULT_ACCEPTANCE_POLICY,
    DEFAULT_ADMISSION_POLICY,
    DEFAULT_AUTONOMOUS_MODE,
    DEFAULT_DOER,
    DEFAULT_WIP_CAP,
    acceptance_decision,
    admission_held_detail,
    effective_acceptance_policy,
    effective_admission_policy,
    plan_admissions,
    reject_routing,
    resolve_assignee,
    resolve_autonomous_mode_permission,
    resolve_wip_cap,
)
from livespec_orchestrator_beads_fabro.types import WorkItem


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id="bd-ib-t1",
        type="task",
        status="ready",
        title="A ready task",
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
    )
    return replace(base, **overrides)


def _always(value: str | None) -> object:
    """An injected assignee resolver returning a fixed value for any item."""

    def _resolve(*, item: WorkItem) -> str | None:
        _ = item
        return value

    return _resolve


# ---------------------------------------------------------------------------
# resolve_wip_cap
# ---------------------------------------------------------------------------


def _write_config(*, tmp_path: Path, text: str) -> Path:
    _ = (tmp_path / ".livespec.jsonc").write_text(text, encoding="utf-8")
    return tmp_path


def test_resolve_wip_cap_defaults_when_no_config(tmp_path: Path) -> None:
    assert resolve_wip_cap(cwd=tmp_path) == DEFAULT_WIP_CAP


def test_resolve_wip_cap_reads_explicit_value(tmp_path: Path) -> None:
    cwd = _write_config(
        tmp_path=tmp_path,
        text='{"livespec-orchestrator-beads-fabro": {"dispatcher": {"wip_cap": 2}}}',
    )
    assert resolve_wip_cap(cwd=cwd) == 2


def test_resolve_wip_cap_defaults_on_parse_error(tmp_path: Path) -> None:
    cwd = _write_config(tmp_path=tmp_path, text="{not valid jsonc")
    assert resolve_wip_cap(cwd=cwd) == DEFAULT_WIP_CAP


def test_resolve_wip_cap_defaults_when_top_level_not_object(tmp_path: Path) -> None:
    cwd = _write_config(tmp_path=tmp_path, text="[1, 2, 3]")
    assert resolve_wip_cap(cwd=cwd) == DEFAULT_WIP_CAP


def test_resolve_wip_cap_defaults_when_plugin_block_missing(tmp_path: Path) -> None:
    cwd = _write_config(tmp_path=tmp_path, text='{"other": {}}')
    assert resolve_wip_cap(cwd=cwd) == DEFAULT_WIP_CAP


def test_resolve_wip_cap_defaults_when_plugin_block_not_object(tmp_path: Path) -> None:
    cwd = _write_config(tmp_path=tmp_path, text='{"livespec-orchestrator-beads-fabro": 7}')
    assert resolve_wip_cap(cwd=cwd) == DEFAULT_WIP_CAP


def test_resolve_wip_cap_defaults_when_dispatcher_block_missing(tmp_path: Path) -> None:
    cwd = _write_config(
        tmp_path=tmp_path,
        text='{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
    )
    assert resolve_wip_cap(cwd=cwd) == DEFAULT_WIP_CAP


def test_resolve_wip_cap_defaults_when_dispatcher_block_not_object(tmp_path: Path) -> None:
    cwd = _write_config(
        tmp_path=tmp_path,
        text='{"livespec-orchestrator-beads-fabro": {"dispatcher": 5}}',
    )
    assert resolve_wip_cap(cwd=cwd) == DEFAULT_WIP_CAP


@pytest.mark.parametrize("raw", ['"3"', "true", "0", "-1"])
def test_resolve_wip_cap_defaults_when_value_invalid(tmp_path: Path, raw: str) -> None:
    cwd = _write_config(
        tmp_path=tmp_path,
        text=f'{{"livespec-orchestrator-beads-fabro": {{"dispatcher": {{"wip_cap": {raw}}}}}}}',
    )
    assert resolve_wip_cap(cwd=cwd) == DEFAULT_WIP_CAP


# ---------------------------------------------------------------------------
# resolve_autonomous_mode_permission (Scenario 37 — the persistent factor)
# ---------------------------------------------------------------------------


def test_resolve_autonomous_mode_defaults_false_when_no_config(tmp_path: Path) -> None:
    assert resolve_autonomous_mode_permission(cwd=tmp_path) is DEFAULT_AUTONOMOUS_MODE


def test_resolve_autonomous_mode_reads_true(tmp_path: Path) -> None:
    cwd = _write_config(
        tmp_path=tmp_path,
        text='{"livespec-orchestrator-beads-fabro": {"dispatcher": {"autonomous_mode": true}}}',
    )
    assert resolve_autonomous_mode_permission(cwd=cwd) is True


@pytest.mark.parametrize("raw", ["false", '"true"', "1", "0", "null"])
def test_resolve_autonomous_mode_only_boolean_true_enables(tmp_path: Path, raw: str) -> None:
    # A dangerous, default-off override: only an explicit boolean `true` arms
    # the persistent factor; a truthy int or the string "true" stays False.
    cwd = _write_config(
        tmp_path=tmp_path,
        text=f'{{"livespec-orchestrator-beads-fabro": {{"dispatcher": {{"autonomous_mode": {raw}}}}}}}',
    )
    assert resolve_autonomous_mode_permission(cwd=cwd) is False


def test_resolve_autonomous_mode_read_does_not_persist(tmp_path: Path) -> None:
    # Scenario 37 "does not persist": the permission read NEVER mutates config.
    text = '{"livespec-orchestrator-beads-fabro": {"dispatcher": {"autonomous_mode": true}}}'
    cwd = _write_config(tmp_path=tmp_path, text=text)
    before = (cwd / ".livespec.jsonc").read_text(encoding="utf-8")
    _ = resolve_autonomous_mode_permission(cwd=cwd)
    _ = resolve_autonomous_mode_permission(cwd=cwd)
    assert (cwd / ".livespec.jsonc").read_text(encoding="utf-8") == before


# ---------------------------------------------------------------------------
# effective_*_policy / resolve_assignee
# ---------------------------------------------------------------------------


def test_effective_admission_policy_inherits_manual_when_none() -> None:
    assert effective_admission_policy(item=_item(admission_policy=None)) == DEFAULT_ADMISSION_POLICY


def test_effective_admission_policy_honors_explicit() -> None:
    assert effective_admission_policy(item=_item(admission_policy="auto")) == "auto"


def test_effective_acceptance_policy_inherits_default_when_none() -> None:
    assert (
        effective_acceptance_policy(item=_item(acceptance_policy=None)) == DEFAULT_ACCEPTANCE_POLICY
    )


def test_effective_acceptance_policy_honors_explicit() -> None:
    assert effective_acceptance_policy(item=_item(acceptance_policy="ai-only")) == "ai-only"


def test_resolve_assignee_honors_explicit() -> None:
    assert resolve_assignee(item=_item(assignee="alice")) == "alice"


def test_resolve_assignee_defaults_to_doer() -> None:
    assert resolve_assignee(item=_item(assignee=None)) == DEFAULT_DOER


# ---------------------------------------------------------------------------
# plan_admissions
# ---------------------------------------------------------------------------


def test_plan_admissions_admits_up_to_free_slots_in_rank_order() -> None:
    items = [
        _item(id="a0", rank="a0", admission_policy="manual"),
        _item(id="a1", rank="a1", admission_policy="auto"),
        _item(id="a2", rank="a2", admission_policy="auto"),
    ]
    plan = plan_admissions(ready_items=items, free_slots=2, resolve_assignee=_always(DEFAULT_DOER))
    assert plan.approved == ()
    assert [item.id for item, _ in plan.admitted] == ["a0", "a1"]
    assert all(assignee == DEFAULT_DOER for _, assignee in plan.admitted)
    # a2 is capacity-deferred: in neither list, it waits for the next pass.
    assert plan.held == ()


def test_plan_admissions_holds_manual_pending_items_regardless_of_capacity() -> None:
    items = [
        _item(id="m0", status="pending-approval", admission_policy="manual"),
        _item(id="a0", admission_policy="auto"),
    ]
    plan = plan_admissions(ready_items=items, free_slots=5, resolve_assignee=_always(DEFAULT_DOER))
    assert [item.id for item, _ in plan.admitted] == ["a0"]
    assert [(item.id, reason) for item, reason in plan.held] == [("m0", "manual-admission")]


def test_plan_admissions_holds_default_none_policy_as_manual_when_pending() -> None:
    plan = plan_admissions(
        ready_items=[_item(id="n0", status="pending-approval", admission_policy=None)],
        free_slots=5,
        resolve_assignee=_always(DEFAULT_DOER),
    )
    assert plan.admitted == ()
    assert [(item.id, reason) for item, reason in plan.held] == [("n0", "manual-admission")]


def test_plan_admissions_auto_approves_pending_item() -> None:
    plan = plan_admissions(
        ready_items=[_item(id="a0", status="pending-approval", admission_policy="auto")],
        free_slots=0,
        resolve_assignee=_always(DEFAULT_DOER),
    )
    assert [item.id for item in plan.approved] == ["a0"]
    assert plan.admitted == ()
    assert plan.held == ()


def test_plan_admissions_holds_unresolvable_assignee() -> None:
    plan = plan_admissions(
        ready_items=[_item(id="a0", admission_policy="auto")],
        free_slots=5,
        resolve_assignee=_always(None),
    )
    assert plan.admitted == ()
    assert [(item.id, reason) for item, reason in plan.held] == [("a0", "unresolvable-assignee")]


def test_plan_admissions_admits_nothing_when_no_free_slots() -> None:
    plan = plan_admissions(
        ready_items=[_item(id="a0", admission_policy="auto")],
        free_slots=0,
        resolve_assignee=_always(DEFAULT_DOER),
    )
    assert plan.admitted == ()
    assert plan.held == ()


@given(
    policies=st.lists(st.sampled_from(["auto", "manual", None]), min_size=0, max_size=8),
    free_slots=st.integers(min_value=0, max_value=10),
    resolved=st.one_of(st.none(), st.just(DEFAULT_DOER)),
)
def test_plan_admissions_invariants(
    policies: list[str | None],
    free_slots: int,
    resolved: str | None,
) -> None:
    items = [
        _item(
            id=f"i{index}",
            rank=f"a{index}",
            status="pending-approval" if policy != "auto" else "ready",
            admission_policy=policy,
        )
        for index, policy in enumerate(policies)
    ]
    plan = plan_admissions(
        ready_items=items, free_slots=free_slots, resolve_assignee=_always(resolved)
    )
    # Admissions never exceed the free slots, and each admitted item is
    # auto-policy + resolvable.
    assert len(plan.admitted) <= free_slots
    for item, assignee in plan.admitted:
        assert item.admission_policy == "auto"
        assert assignee == resolved
        assert resolved is not None
    # No item is both admitted and held; the disjoint union never exceeds the
    # input set.
    admitted_ids = {item.id for item, _ in plan.admitted}
    held_ids = {item.id for item, _ in plan.held}
    assert admitted_ids.isdisjoint(held_ids)
    assert (admitted_ids | held_ids) <= {item.id for item in items}
    # Ready admission is mechanical; policy holds only apply before approval.
    for item in items:
        if item.status == "pending-approval" and item.admission_policy != "auto":
            assert item.id in held_ids


# ---------------------------------------------------------------------------
# acceptance_decision / reject_routing
# ---------------------------------------------------------------------------


def test_acceptance_decision_ai_only_goes_to_done() -> None:
    decision = acceptance_decision(policy="ai-only")
    assert (decision.policy, decision.to_done) == ("ai-only", True)


@pytest.mark.parametrize("policy", ["ai-then-human", "human-only"])
def test_acceptance_decision_parks_when_human_required(policy: str) -> None:
    decision = acceptance_decision(policy=policy)
    assert (decision.policy, decision.to_done) == (policy, False)


def test_reject_routing_rework_goes_to_active() -> None:
    assert reject_routing(kind="rework") == "active"


def test_reject_routing_regroom_goes_to_backlog() -> None:
    assert reject_routing(kind="re-groom") == "backlog"


def test_reject_routing_unknown_kind_raises() -> None:
    with pytest.raises(ValueError, match="unknown reject kind"):
        _ = reject_routing(kind="bogus")


# ---------------------------------------------------------------------------
# admission_held_detail
# ---------------------------------------------------------------------------


def test_admission_held_detail_manual_is_actionable() -> None:
    detail = admission_held_detail(item_id="bd-ib-spec1", reason="manual-admission")
    assert "bd-ib-spec1" in detail
    assert "approve" in detail.lower()


def test_admission_held_detail_unresolvable_is_actionable() -> None:
    detail = admission_held_detail(item_id="bd-ib-x9", reason="unresolvable-assignee")
    assert "bd-ib-x9" in detail
    assert "assign" in detail.lower()
