"""Pin the public API of the extracted dispatcher planning-layer modules.

`_dispatcher_host_only` (host-only routing predicate) and `_dispatcher_goal`
(per-item goal-brief assembly) were split out of `_dispatcher_plan` /
`_dispatcher_overlay` so each stays an honest cohesive unit under the file
LLOC ceiling. This test pins that the moved public functions are importable
and callable from their NEW defining modules AND remain re-exported (as the
SAME objects) from `_dispatcher_plan`, so `dispatcher.py`'s imports are
untouched by the move.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands import _dispatcher_plan
from livespec_orchestrator_beads_fabro.commands._dispatcher_admission import (
    Admission,
    admission_held_outcome,
    admit_and_select,
    autonomous_armed,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_goal import render_goal
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_only import (
    host_only_refusal_detail,
    is_host_only_item,
)
from livespec_orchestrator_beads_fabro.types import WorkItem


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id="livespec-impl-beads-t1",
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
        admission_policy="auto",
        acceptance_policy="ai-only",
    )
    from dataclasses import replace

    return replace(base, **overrides)


def test_host_only_predicate_importable_and_callable_from_new_module() -> None:
    assert is_host_only_item(item=_item(title="Refactor [host-only] the hook")) is True
    assert is_host_only_item(item=_item()) is False


def test_host_only_refusal_detail_importable_and_callable_from_new_module() -> None:
    detail = host_only_refusal_detail(item_id="livespec-impl-beads-uvd")
    assert "host-only refusal" in detail
    assert "livespec-impl-beads-uvd" in detail


def test_render_goal_importable_and_callable_from_new_module(tmp_path: Path) -> None:
    goal = render_goal(item=_item(), repo=tmp_path, branch="feat/t")
    assert "Work-item: livespec-impl-beads-t1" in goal
    assert "Publish branch" in goal


def test_new_module_functions_are_re_exported_from_dispatcher_plan() -> None:
    # dispatcher.py imports these from _dispatcher_plan; the move keeps that
    # surface intact by re-exporting the SAME function objects.
    assert _dispatcher_plan.render_goal is render_goal
    assert _dispatcher_plan.is_host_only_item is is_host_only_item
    assert _dispatcher_plan.host_only_refusal_detail is host_only_refusal_detail


def test_admission_cluster_importable_from_new_module() -> None:
    assert Admission.__name__ == "Admission"
    assert admit_and_select.__name__ == "admit_and_select"
    assert admission_held_outcome(item=_item(), reason="manual").stage == "admission-held"
    assert autonomous_armed(args=object()) is False
