"""The edges of the partition-free Definition of Done rendering.

`test_spec_change_tier_proof_mode_partition.py` carries the assertions of
`bd-ib-ajtmgf`; this module covers the section shapes it does not reach: a
section with no reference line, a stray line the grammar does not admit, a
section with no bullet at all, and the sub-headings and `Reason:` lines that are
NOT proof-mode metadata. Each is asserted to keep what it carried, since a
rendering that dropped them would hide a real edit from the digest. Only the
`Host-captured` and `Human-attested` sub-headings, their `Reason:` lines and the
bullet order are the partition; anything else is content the judge reads.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._spec_change_tier import (
    asked_for_behaviour,
    behaviour_digest,
)
from livespec_orchestrator_beads_fabro.types import WorkItem


def _item(*, description: str) -> WorkItem:
    return WorkItem(
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


def _statement(*, description: str) -> str:
    return asked_for_behaviour(item=_item(description=description))


def _digest(*, description: str) -> str:
    return behaviour_digest(item=_item(description=description))


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


_FLAT = "## Definition of Done\n\n- First bullet.\n- Second bullet.\n"


def test_a_human_attested_sub_heading_is_partition_too() -> None:
    attested = (
        "## Definition of Done\n\n- Second bullet.\n\n### Human-attested\n\n"
        "Reason: a human must look.\n\n- First bullet.\n"
    )
    assert _digest(description=attested) == _digest(description=_FLAT)


def test_a_wrapped_bullet_and_a_wrapped_reason_are_partition_too() -> None:
    flat = "## Definition of Done\n\n- First bullet\n  wraps here.\n- Second bullet.\n"
    moved = (
        "## Definition of Done\n\n- Second bullet.\n\n### Host-captured\n\n"
        "Reason: a long reason\n  that wraps.\n\n- First bullet\n  wraps here.\n"
    )
    assert _digest(description=moved) == _digest(description=flat)


def test_a_non_proof_mode_sub_heading_is_content_the_judge_reads() -> None:
    grouped = "## Definition of Done\n\n- First bullet.\n\n### Context\n\n- Second bullet.\n"
    assert "### Context" in _statement(description=grouped)
    regrouped = grouped.replace("### Context", "### Background")
    assert _digest(description=regrouped) != _digest(description=grouped)
    ungrouped = grouped.replace("### Context\n\n", "")
    assert _digest(description=ungrouped) != _digest(description=grouped)


def test_a_reason_line_outside_a_proof_mode_sub_heading_is_content() -> None:
    under_context = (
        "## Definition of Done\n\n- First bullet.\n\n### Context\n\nReason: the history.\n"
    )
    assert "Reason: the history." in _statement(description=under_context)
    assert _digest(description=under_context.replace("history", "future")) != _digest(
        description=under_context
    )
    before_any_sub_heading = "## Definition of Done\n\nReason: why.\n\n- First bullet.\n"
    assert "Reason: why." in _statement(description=before_any_sub_heading)


def test_the_order_of_bullets_under_a_non_proof_mode_sub_heading_is_partition_too() -> None:
    grouped = (
        "## Definition of Done\n\n- Lead bullet.\n\n### Context\n\n"
        "- First bullet.\n- Second bullet.\n"
    )
    reordered = grouped.replace(
        "- First bullet.\n- Second bullet.", "- Second bullet.\n- First bullet."
    )
    assert _digest(description=reordered) == _digest(description=grouped)
    reworded = grouped.replace("Second bullet", "Third bullet")
    assert _digest(description=reworded) != _digest(description=grouped)
    moved_out = grouped.replace(
        "### Context\n\n- First bullet.\n- Second bullet.",
        "- First bullet.\n\n### Context\n\n- Second bullet.",
    )
    assert _digest(description=moved_out) != _digest(description=grouped)
