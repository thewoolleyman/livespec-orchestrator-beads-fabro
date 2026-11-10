"""The dispatch goal carries no Definition-of-Done judgement subject (bd-ib-tzvtgc).

Fabro injects the goal into EVERY ACP node, so a goal that embeds the judgement
subject puts the item's referenced spec sections in the prompt prefix of each
request of each node -- implement, review, fix, proof_capture and the rest --
although only `dod_gate` grades them. Measured on bd-ib-qshcwc: 24,910 characters
before v0.310.0 and 136,040 after.

THE ASSERTION IS ABOUT LENGTH, NOT ABOUT A HEADING. A goal that dropped the
subject's own heading line while still inlining the clause bodies would pass a
substring probe and keep every cost, so the case renders ONE item twice against
a spec whose referenced heading is first 5,000 characters and then 200,000, and
requires the two goals to be the same length. The repository path, the item and
its riders are identical across the two renderings, so the body is the only
variable. The `dod_gate` node's own copy of the subject is covered by
`test_dispatcher_dod_gate_subject`.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_goal import render_goal
from livespec_orchestrator_beads_fabro.store import WorkItemComment
from livespec_orchestrator_beads_fabro.types import WorkItem

_HEADING = "## Scenario 174 — The judgement runs before admission"
_RIDER = "Rider: narrow the first assertion to the admission wall."


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-7f66ar",
        type="feature",
        status="ready",
        title="Judge the Definition of Done before dispatch",
        description=(
            "## Definition of Done\n\n"
            "- The judgement runs before an item moves to ready.\n\n"
            f"References: {_HEADING}\n"
        ),
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-20T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _goal_with_heading_body_of(*, repo: Path, characters: int) -> str:
    _ = (repo / "SPECIFICATION" / "scenarios.md").write_text(
        f"{_HEADING}\n\n{'x' * characters}\n", encoding="utf-8"
    )
    return render_goal(
        item=_item(),
        repo=repo,
        branch="feat/bd-ib-7f66ar",
        comments=(WorkItemComment(text=_RIDER, author=None, created_at=None),),
    )


def test_the_goal_is_the_same_length_whatever_size_the_referenced_heading_body_is(
    tmp_path: Path,
) -> None:
    (tmp_path / "SPECIFICATION").mkdir()

    small = _goal_with_heading_body_of(repo=tmp_path, characters=5_000)
    large = _goal_with_heading_body_of(repo=tmp_path, characters=200_000)

    assert len(small) == len(large)
    assert "xxxxxxxxxx" not in large
    assert _RIDER in large
