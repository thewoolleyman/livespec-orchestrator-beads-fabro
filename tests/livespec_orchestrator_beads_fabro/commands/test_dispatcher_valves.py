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

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import TypeVar

import pytest
from hypothesis import given
from hypothesis import strategies as st
from livespec_orchestrator_beads_fabro.commands import _dispatcher_valves as valves
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    PolicySettingUnreadable,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_valves import (
    DEFAULT_ACCEPTANCE_POLICY,
    DEFAULT_ADMISSION_POLICY,
    DEFAULT_DOER,
    DEFAULT_WIP_CAP,
    acceptance_decision,
    admission_held_detail,
    effective_acceptance_policy,
    effective_admission_policy,
    plan_admissions,
    reject_routing,
    resolve_assignee,
    resolve_wip_cap,
)
from livespec_orchestrator_beads_fabro.types import WorkItem
from returns.io import IOFailure, IOResult
from returns.unsafe import unsafe_perform_io

_NO_CONFIG_CWD = Path("tests/nonexistent-policy-cwd")

_Value = TypeVar("_Value")


def _read(outcome: IOResult[_Value, PolicySettingUnreadable]) -> _Value:
    """The value out of a policy read that SUCCEEDED.

    ⚠️ `unsafe_perform_io` is mandatory rather than decorative: `IOResult.unwrap`
    yields `IO[value]`, not the value, so a bare `.unwrap()` here would compare
    an `IO` wrapper against `5` — false for every input, and type-clean.
    """
    return unsafe_perform_io(outcome.unwrap())


def _failed(outcome: IOResult[object, PolicySettingUnreadable]) -> PolicySettingUnreadable:
    """The `PolicySettingUnreadable` out of a policy read that FAILED."""
    return unsafe_perform_io(outcome.failure())


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
    tmp_path.mkdir(parents=True, exist_ok=True)
    _ = (tmp_path / ".livespec.jsonc").write_text(text, encoding="utf-8")
    return tmp_path


def test_resolve_wip_cap_defaults_when_no_config(tmp_path: Path) -> None:
    assert _read(resolve_wip_cap(cwd=tmp_path)) == DEFAULT_WIP_CAP


def test_resolve_wip_cap_reads_explicit_value(tmp_path: Path) -> None:
    cwd = _write_config(
        tmp_path=tmp_path,
        text='{"livespec-orchestrator-beads-fabro": {"dispatcher": {"wip_cap": 2}}}',
    )
    assert _read(resolve_wip_cap(cwd=cwd)) == 2


def test_resolve_ready_aging_threshold_hours_defaults_when_no_config(tmp_path: Path) -> None:
    assert hasattr(valves, "resolve_ready_aging_threshold_hours")
    assert _read(valves.resolve_ready_aging_threshold_hours(cwd=tmp_path)) == 24


def test_resolve_ready_aging_threshold_hours_reads_explicit_value(tmp_path: Path) -> None:
    cwd = _write_config(
        tmp_path=tmp_path,
        text=(
            '{"livespec-orchestrator-beads-fabro": '
            '{"dispatcher": {"ready_aging_threshold_hours": 36}}}'
        ),
    )

    assert hasattr(valves, "resolve_ready_aging_threshold_hours")
    assert _read(valves.resolve_ready_aging_threshold_hours(cwd=cwd)) == 36


def test_resolve_drift_capture_merge_threshold_defaults_to_one(tmp_path: Path) -> None:
    assert valves.DEFAULT_DRIFT_CAPTURE_MERGE_THRESHOLD == 1
    assert _read(valves.resolve_drift_capture_merge_threshold(cwd=tmp_path)) == 1


def test_resolve_drift_capture_merge_threshold_reads_explicit_value(tmp_path: Path) -> None:
    cwd = _write_config(
        tmp_path=tmp_path,
        text=(
            '{"livespec-orchestrator-beads-fabro": '
            '{"dispatcher": {"drift_capture_merge_threshold": 7}}}'
        ),
    )

    assert _read(valves.resolve_drift_capture_merge_threshold(cwd=cwd)) == 7


@pytest.mark.parametrize("raw", ['"3"', "true", "0", "-1"])
def test_resolve_drift_capture_merge_threshold_fails_when_value_invalid(
    tmp_path: Path, raw: str
) -> None:
    cwd = _write_config(
        tmp_path=tmp_path,
        text=(
            '{"livespec-orchestrator-beads-fabro": '
            f'{{"dispatcher": {{"drift_capture_merge_threshold": {raw}}}}}}}'
        ),
    )

    outcome = valves.resolve_drift_capture_merge_threshold(cwd=cwd)

    assert isinstance(outcome, IOFailure)
    failure = _failed(outcome)
    assert failure.setting == "drift_capture_merge_threshold"
    assert "an integer >= 1" in failure.detail


@pytest.mark.parametrize("raw", ['"24"', "true", "0", "-1"])
def test_resolve_ready_aging_threshold_hours_fails_when_value_invalid(
    tmp_path: Path, raw: str
) -> None:
    cwd = _write_config(
        tmp_path=tmp_path,
        text=f'{{"livespec-orchestrator-beads-fabro": {{"dispatcher": {{"ready_aging_threshold_hours": {raw}}}}}}}',
    )

    assert hasattr(valves, "resolve_ready_aging_threshold_hours")
    outcome = valves.resolve_ready_aging_threshold_hours(cwd=cwd)

    assert isinstance(outcome, IOFailure)
    failure = _failed(outcome)
    assert failure.setting == "ready_aging_threshold_hours"
    assert "an integer >= 1" in failure.detail
    assert (
        unsafe_perform_io(outcome.value_or(valves.DEFAULT_READY_AGING_THRESHOLD_HOURS))
        == valves.DEFAULT_READY_AGING_THRESHOLD_HOURS
    )


def test_resolve_wip_cap_fails_on_parse_error(tmp_path: Path) -> None:
    """A config that will not PARSE is a failure, not an unconfigured repo.

    The caller's fallback still lands on the same default — the third
    assertion pins that — but it is now the CALLER's, taken with the reason in
    hand, instead of a default invented where nobody could see it.
    """
    cwd = _write_config(tmp_path=tmp_path, text="{not valid jsonc")

    outcome = resolve_wip_cap(cwd=cwd)

    assert isinstance(outcome, IOFailure)
    assert "does not parse" in _failed(outcome).detail
    assert unsafe_perform_io(outcome.value_or(DEFAULT_WIP_CAP)) == DEFAULT_WIP_CAP


def test_resolve_wip_cap_fails_when_top_level_not_object(tmp_path: Path) -> None:
    cwd = _write_config(tmp_path=tmp_path, text="[1, 2, 3]")

    outcome = resolve_wip_cap(cwd=cwd)

    assert isinstance(outcome, IOFailure)
    assert "root is not an object" in _failed(outcome).detail


def test_resolve_wip_cap_defaults_when_plugin_block_missing(tmp_path: Path) -> None:
    """An ABSENT block is an answer: nothing is configured, so the default holds."""
    cwd = _write_config(tmp_path=tmp_path, text='{"other": {}}')
    assert _read(resolve_wip_cap(cwd=cwd)) == DEFAULT_WIP_CAP


def test_resolve_wip_cap_fails_when_plugin_block_not_object(tmp_path: Path) -> None:
    cwd = _write_config(tmp_path=tmp_path, text='{"livespec-orchestrator-beads-fabro": 7}')

    outcome = resolve_wip_cap(cwd=cwd)

    assert isinstance(outcome, IOFailure)
    assert "livespec-orchestrator-beads-fabro is not an object" in _failed(outcome).detail


def test_resolve_wip_cap_defaults_when_dispatcher_block_missing(tmp_path: Path) -> None:
    cwd = _write_config(
        tmp_path=tmp_path,
        text='{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
    )
    assert _read(resolve_wip_cap(cwd=cwd)) == DEFAULT_WIP_CAP


def test_resolve_wip_cap_fails_when_dispatcher_block_not_object(tmp_path: Path) -> None:
    cwd = _write_config(
        tmp_path=tmp_path,
        text='{"livespec-orchestrator-beads-fabro": {"dispatcher": 5}}',
    )

    outcome = resolve_wip_cap(cwd=cwd)

    assert isinstance(outcome, IOFailure)
    assert "dispatcher is not an object" in _failed(outcome).detail


@pytest.mark.parametrize("raw", ['"3"', "true", "-1"])
def test_resolve_wip_cap_fails_when_value_invalid(tmp_path: Path, raw: str) -> None:
    """A value the setting cannot accept is the operator being wrong, not silent."""
    cwd = _write_config(
        tmp_path=tmp_path,
        text=f'{{"livespec-orchestrator-beads-fabro": {{"dispatcher": {{"wip_cap": {raw}}}}}}}',
    )

    outcome = resolve_wip_cap(cwd=cwd)

    assert isinstance(outcome, IOFailure)
    failure = _failed(outcome)
    assert failure.setting == "wip_cap"
    assert "an integer >= 0" in failure.detail
    assert unsafe_perform_io(outcome.value_or(DEFAULT_WIP_CAP)) == DEFAULT_WIP_CAP


# ---------------------------------------------------------------------------
# dispatcher policy settings / effective policies / resolve_assignee
# ---------------------------------------------------------------------------


def test_dispatcher_policy_settings_default_when_no_config(tmp_path: Path) -> None:
    assert (
        _read(valves.resolve_auto_approve_ready(cwd=tmp_path)) is valves.DEFAULT_AUTO_APPROVE_READY
    )
    assert (
        _read(valves.resolve_merge_on_review_cap(cwd=tmp_path))
        is valves.DEFAULT_MERGE_ON_REVIEW_CAP
    )
    assert _read(valves.resolve_acceptance_mode(cwd=tmp_path)) == DEFAULT_ACCEPTANCE_POLICY
    assert _read(valves.resolve_review_fix_cap(cwd=tmp_path)) == valves.DEFAULT_REVIEW_FIX_CAP
    assert (
        _read(valves.resolve_acceptance_rework_cap(cwd=tmp_path))
        == valves.DEFAULT_ACCEPTANCE_REWORK_CAP
    )
    assert (
        _read(valves.resolve_ready_aging_threshold_hours(cwd=tmp_path))
        == valves.DEFAULT_READY_AGING_THRESHOLD_HOURS
    )
    assert _read(resolve_wip_cap(cwd=tmp_path)) == DEFAULT_WIP_CAP


def test_dispatcher_policy_settings_read_explicit_values(tmp_path: Path) -> None:
    cwd = _write_config(
        tmp_path=tmp_path,
        text=(
            '{"livespec-orchestrator-beads-fabro": {"dispatcher": {'
            '"auto_approve_ready": true,'
            '"merge_on_review_cap": true,'
            '"acceptance_mode": "human-only",'
            '"review_fix_cap": 4,'
            '"acceptance_rework_cap": 5,'
            '"ready_aging_threshold_hours": 48,'
            '"wip_cap": 6'
            "}}}"
        ),
    )

    assert _read(valves.resolve_auto_approve_ready(cwd=cwd)) is True
    assert _read(valves.resolve_merge_on_review_cap(cwd=cwd)) is True
    assert _read(valves.resolve_acceptance_mode(cwd=cwd)) == "human-only"
    assert _read(valves.resolve_review_fix_cap(cwd=cwd)) == 4
    assert _read(valves.resolve_acceptance_rework_cap(cwd=cwd)) == 5
    assert _read(valves.resolve_ready_aging_threshold_hours(cwd=cwd)) == 48
    assert _read(resolve_wip_cap(cwd=cwd)) == 6


@pytest.mark.parametrize(
    ("key", "raw", "reader"),
    [
        ("auto_approve_ready", '"true"', valves.resolve_auto_approve_ready),
        ("merge_on_review_cap", "1", valves.resolve_merge_on_review_cap),
        ("acceptance_mode", '"sometimes"', valves.resolve_acceptance_mode),
        ("review_fix_cap", "true", valves.resolve_review_fix_cap),
        ("acceptance_rework_cap", "0", valves.resolve_acceptance_rework_cap),
        ("ready_aging_threshold_hours", '"24"', "resolve_ready_aging_threshold_hours"),
    ],
)
def test_dispatcher_policy_settings_fail_on_wrong_typed_values(
    tmp_path: Path,
    key: str,
    raw: str,
    reader: Callable[..., IOResult[object, PolicySettingUnreadable]] | str,
) -> None:
    """The WRONG key fails; the settings beside it still read their defaults.

    Both halves matter. Failing only the key the operator got wrong is what
    makes this a diagnosis rather than a blanket refusal, and it is why the
    per-setting failure carries the setting NAME.
    """
    cwd = _write_config(
        tmp_path=tmp_path,
        text=(f'{{"livespec-orchestrator-beads-fabro": {{"dispatcher": {{"{key}": {raw}}}}}}}'),
    )

    if isinstance(reader, str):
        assert hasattr(valves, reader)
        resolved_reader = getattr(valves, reader)
    else:
        resolved_reader = reader
    outcome = resolved_reader(cwd=cwd)

    assert isinstance(outcome, IOFailure)
    assert _failed(outcome).setting == key
    assert _read(resolve_wip_cap(cwd=cwd)) == DEFAULT_WIP_CAP


def test_effective_admission_policy_inherits_global_auto_when_unlabeled(tmp_path: Path) -> None:
    cwd = _write_config(
        tmp_path=tmp_path,
        text='{"livespec-orchestrator-beads-fabro": {"dispatcher": {"auto_approve_ready": true}}}',
    )
    assert _read(effective_admission_policy(item=_item(admission_policy=None), cwd=cwd)) == "auto"


def test_effective_admission_policy_inherits_manual_when_none(tmp_path: Path) -> None:
    assert (
        _read(effective_admission_policy(item=_item(admission_policy=None), cwd=tmp_path))
        == DEFAULT_ADMISSION_POLICY
    )


def test_effective_admission_policy_propagates_an_unreadable_config(tmp_path: Path) -> None:
    """An item with no per-item policy inherits the global read, failure and all.

    This is the path that silently reverted this repo's own autonomous
    dispatch: `auto_approve_ready: true` in a file that stopped parsing read
    as `manual` and every ready item waited for a human with nothing said.
    """
    cwd = _write_config(tmp_path=tmp_path, text="{not valid jsonc")

    outcome = effective_admission_policy(item=_item(admission_policy=None), cwd=cwd)

    assert isinstance(outcome, IOFailure)
    assert _failed(outcome).setting == "auto_approve_ready"


def test_effective_acceptance_policy_defaults_with_empty_config() -> None:
    assert (
        _read(effective_acceptance_policy(item=_item(acceptance_policy=None), cwd=_NO_CONFIG_CWD))
        == DEFAULT_ACCEPTANCE_POLICY
    )


def test_effective_admission_policy_honors_explicit_in_both_directions(tmp_path: Path) -> None:
    auto_off = _write_config(
        tmp_path=tmp_path / "auto-off",
        text='{"livespec-orchestrator-beads-fabro": {"dispatcher": {"auto_approve_ready": false}}}',
    )
    auto_on = _write_config(
        tmp_path=tmp_path / "auto-on",
        text='{"livespec-orchestrator-beads-fabro": {"dispatcher": {"auto_approve_ready": true}}}',
    )
    assert (
        _read(effective_admission_policy(item=_item(admission_policy="auto"), cwd=auto_off))
        == "auto"
    )
    assert (
        _read(effective_admission_policy(item=_item(admission_policy="manual"), cwd=auto_on))
        == "manual"
    )


def test_effective_admission_policy_honours_a_commitment_bearing_items_own_label(
    tmp_path: Path,
) -> None:
    """A `spec_commitment_hint` no longer floors admission to manual.

    It asserted the floor until `bd-ib-yykjko`. The autonomy-tier bullet makes
    that field the mark of "an implementation follow-up to an already ratified
    change" and forbids reading the tier off it, so the floor held exactly the
    items the clause routes "as it would any other item". A genuinely
    spec-change-tier item is held out of `ready` by `_spec_change_tier_gate`
    instead, which an admission floor could never have reached anyway.
    """
    cwd = _write_config(
        tmp_path=tmp_path,
        text='{"livespec-orchestrator-beads-fabro": {"dispatcher": {"auto_approve_ready": true}}}',
    )
    item = _item(admission_policy="auto", spec_commitment_hint="SC-1")

    assert _read(effective_admission_policy(item=item, cwd=cwd)) == "auto"


def test_effective_acceptance_policy_inherits_global_mode_when_unlabeled(tmp_path: Path) -> None:
    cwd = _write_config(
        tmp_path=tmp_path,
        text='{"livespec-orchestrator-beads-fabro": {"dispatcher": {"acceptance_mode": "ai-only"}}}',
    )
    assert (
        _read(effective_acceptance_policy(item=_item(acceptance_policy=None), cwd=cwd)) == "ai-only"
    )


def test_effective_acceptance_policy_inherits_default_when_none(tmp_path: Path) -> None:
    assert (
        _read(effective_acceptance_policy(item=_item(acceptance_policy=None), cwd=tmp_path))
        == DEFAULT_ACCEPTANCE_POLICY
    )


def test_effective_acceptance_policy_honors_explicit(tmp_path: Path) -> None:
    cwd = _write_config(
        tmp_path=tmp_path,
        text='{"livespec-orchestrator-beads-fabro": {"dispatcher": {"acceptance_mode": "ai-only"}}}',
    )
    assert (
        _read(effective_acceptance_policy(item=_item(acceptance_policy="human-only"), cwd=cwd))
        == "human-only"
    )


def test_new_raw_label_overrides_beat_global_settings(tmp_path: Path) -> None:
    cwd = _write_config(
        tmp_path=tmp_path,
        text=(
            '{"livespec-orchestrator-beads-fabro": {"dispatcher": {'
            '"merge_on_review_cap": false,'
            '"review_fix_cap": 3,'
            '"acceptance_rework_cap": 2'
            "}}}"
        ),
    )

    assert (
        _read(
            valves.effective_merge_on_review_cap(
                item=_item(), cwd=cwd, raw_labels=("merge-on-review-cap:true",)
            )
        )
        is True
    )
    assert (
        _read(
            valves.effective_review_fix_cap(item=_item(), cwd=cwd, raw_labels=("review-fix-cap:7",))
        )
        == 7
    )
    assert (
        _read(
            valves.effective_acceptance_rework_cap(
                item=_item(), cwd=cwd, raw_labels=("acceptance-rework-cap:8",)
            )
        )
        == 8
    )


def test_raw_label_override_answers_even_when_the_config_is_unreadable(tmp_path: Path) -> None:
    """A per-item label decides BEFORE the global read, so it never reaches it."""
    cwd = _write_config(tmp_path=tmp_path, text="{not valid jsonc")

    assert (
        _read(
            valves.effective_review_fix_cap(item=_item(), cwd=cwd, raw_labels=("review-fix-cap:7",))
        )
        == 7
    )
    assert isinstance(valves.effective_review_fix_cap(item=_item(), cwd=cwd), IOFailure)


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
    plan = plan_admissions(
        ready_items=items,
        free_slots=2,
        cwd=_NO_CONFIG_CWD,
        resolve_assignee=_always(DEFAULT_DOER),
    )
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
    plan = plan_admissions(
        ready_items=items,
        free_slots=5,
        cwd=_NO_CONFIG_CWD,
        resolve_assignee=_always(DEFAULT_DOER),
    )
    assert [item.id for item, _ in plan.admitted] == ["a0"]
    assert [(item.id, reason) for item, reason in plan.held] == [("m0", "manual-admission")]


def test_plan_admissions_holds_default_none_policy_as_manual_when_pending() -> None:
    plan = plan_admissions(
        ready_items=[_item(id="n0", status="pending-approval", admission_policy=None)],
        free_slots=5,
        cwd=_NO_CONFIG_CWD,
        resolve_assignee=_always(DEFAULT_DOER),
    )
    assert plan.admitted == ()
    assert [(item.id, reason) for item, reason in plan.held] == [("n0", "manual-admission")]


def test_plan_admissions_auto_approves_pending_item() -> None:
    plan = plan_admissions(
        ready_items=[_item(id="a0", status="pending-approval", admission_policy="auto")],
        free_slots=0,
        cwd=_NO_CONFIG_CWD,
        resolve_assignee=_always(DEFAULT_DOER),
    )
    assert [item.id for item in plan.approved] == ["a0"]
    assert plan.admitted == ()
    assert plan.held == ()


def test_plan_admissions_holds_unresolvable_assignee() -> None:
    plan = plan_admissions(
        ready_items=[_item(id="a0", admission_policy="auto")],
        free_slots=5,
        cwd=_NO_CONFIG_CWD,
        resolve_assignee=_always(None),
    )
    assert plan.admitted == ()
    assert [(item.id, reason) for item, reason in plan.held] == [("a0", "unresolvable-assignee")]


def test_plan_admissions_admits_nothing_when_no_free_slots() -> None:
    plan = plan_admissions(
        ready_items=[_item(id="a0", admission_policy="auto")],
        free_slots=0,
        cwd=_NO_CONFIG_CWD,
        resolve_assignee=_always(DEFAULT_DOER),
    )
    assert plan.admitted == ()
    assert plan.held == ()


def test_plan_admissions_honors_injected_admission_policy_resolver() -> None:
    # The injected `admission_policy` seam is how the full-autonomous-mode
    # collapse flips a manual pending item to auto WITHOUT this valve knowing
    # about the mode: an all-`auto` resolver approves an otherwise-held manual.
    def _all_auto(*, item: WorkItem, cwd: Path) -> str:
        _ = (item, cwd)
        return "auto"

    plan = plan_admissions(
        ready_items=[_item(id="m0", status="pending-approval", admission_policy="manual")],
        free_slots=0,
        cwd=_NO_CONFIG_CWD,
        resolve_assignee=_always(DEFAULT_DOER),
        admission_policy=_all_auto,
    )
    assert [item.id for item in plan.approved] == ["m0"]
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
        ready_items=items,
        free_slots=free_slots,
        cwd=_NO_CONFIG_CWD,
        resolve_assignee=_always(resolved),
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
