"""The edges of the partition-free Definition of Done rendering.

`test_spec_change_tier_proof_mode_partition.py` carries the assertions of
`bd-ib-ajtmgf`; this module covers the section shapes it does not reach: a
section with no reference line, a stray line the grammar does not admit, and a
section with no bullet at all. Each is asserted to keep what it carried, since
a rendering that dropped them would hide a real edit from the digest.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._spec_change_tier import asked_for_behaviour
from livespec_orchestrator_beads_fabro.types import WorkItem


def _statement(*, description: str) -> str:
    item = WorkItem(
        id="bd-ib-one",
        type="feature",
        status="backlog",
        title="A title",
        description=description,
        origin="freeform",
        gap_id=None,
        rank="m",
        assignee=None,
        depends_on=(),
        captured_at="2026-01-01T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )
    return asked_for_behaviour(item=item)


def test_a_section_without_a_reference_line_renders_no_reference_line() -> None:
    statement = _statement(description="## Definition of Done\n\n- Only bullet.\n")
    assert "References:" not in statement
    assert "- Only bullet." in statement


def test_a_stray_line_is_kept_so_that_editing_it_is_a_real_change() -> None:
    statement = _statement(
        description="## Definition of Done\n\nA stray sentence.\n\n- A bullet.\n"
    )
    assert "A stray sentence." in statement


def test_a_section_with_no_bullet_keeps_its_heading_and_reference_line() -> None:
    statement = _statement(description="## Definition of Done\n\nReferences: ## A heading\n")
    assert "## Definition of Done" in statement
    assert "References: ## A heading" in statement
