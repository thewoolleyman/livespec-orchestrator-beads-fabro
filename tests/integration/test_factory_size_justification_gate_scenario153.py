"""Scenario 153: adopted assertion ceilings and attributed exceptions.

This integration journey binds the size gate through the same shared decision
that capture, groom, approval, and factory dispatch consume.  Store-facing
cases use the real in-memory beads seam; only processes outside the repository
are stood in.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any, cast

from livespec_orchestrator_beads_fabro.types import WorkItem


def _item(*, assertion_count: int, item_id: str = "bd-size") -> WorkItem:
    bullets = "\n".join(
        f"- The product satisfies assertion {index}." for index in range(assertion_count)
    )
    return WorkItem(
        id=item_id,
        type="feature",
        status="ready",
        title="Factory size gate",
        description=(
            "## Definition of Done\n\n"
            f"{bullets}\n\n"
            "References: ## Scenario 153 — An adopted assertion ceiling requires "
            "an attributed exception without waiving other gates\n"
        ),
        origin="freeform",
        gap_id=None,
        rank="a4",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-09T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        spec_commitment_hint=None,
        admission_policy="auto",
    )


def _size_gate_module() -> Any:
    return import_module("livespec_orchestrator_beads_fabro.commands._dispatcher_factory_size_gate")


def test_absent_ceiling_leaves_every_entry_path_on_ordinary_admission() -> None:
    """No adopted ceiling means justification presence has no gate effect."""
    module = _size_gate_module()
    valid = {
        "rationale": "This slice is cohesive despite its assertion count.",
        "author": "human:maintainer",
        "at": "2026-10-09T00:00:00Z",
    }

    decisions = [
        cast(
            "Any",
            module.factory_size_decision(
                item=_item(assertion_count=4, item_id=f"bd-{surface}-{variant}"),
                adopted_ceiling=None,
                raw_justification=raw,
            ),
        )
        for surface in ("capture", "groom", "approval", "dispatch")
        for variant, raw in (("missing", None), ("present", valid))
    ]

    assert [decision.disposition for decision in decisions] == ["proceed"] * 8
    assert all(decision.adopted_ceiling is None for decision in decisions)
    assert all(decision.assertion_count == 4 for decision in decisions)
    assert all(decision.reason is None for decision in decisions)
    assert all(decision.size_justified is False for decision in decisions)
