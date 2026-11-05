"""Mechanical commit-refusal budget declaration for Scenario 285."""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import build_plan
from livespec_orchestrator_beads_fabro.commands._jsonc import loads

_ROOT = Path(__file__).resolve().parents[3]
_TARGETS = (
    "check-lint",
    "check-format",
    "check-keyword-only-args",
    "check-file-lloc",
    "check-per-file-coverage",
)


def test_dispatch_plan_carries_the_declared_mechanical_commit_refusal_budget() -> None:
    """A dispatch has the target list and two separate mechanical re-entries."""
    configured = loads(text=(_ROOT / ".livespec.jsonc").read_text(encoding="utf-8"))
    assert isinstance(configured, dict)
    dispatcher = configured["livespec-orchestrator-beads-fabro"]["dispatcher"]

    implement = dispatcher.get("implement", {})
    assert implement.get("mechanical_targets") == list(_TARGETS)

    plan = build_plan(
        repo=_ROOT,
        work_item_id="bd-ib-v5dqyn",
        workflow_toml=_ROOT / ".claude-plugin/.fabro/workflows/implement-work-item/workflow.toml",
        goal_file=_ROOT / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=_ROOT / "janitor",
        config_text=(_ROOT / ".livespec.jsonc").read_text(encoding="utf-8"),
    )

    assert getattr(plan, "mechanical_targets", None) == _TARGETS
    assert getattr(plan, "mechanical_reentries", None) == 2
