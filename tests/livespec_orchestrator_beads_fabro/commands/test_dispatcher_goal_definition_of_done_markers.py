"""The rendered goal marks where the item's own Definition of Done begins and ends.

`SPECIFICATION/contracts.md` section "Dispatch-brief lessons injection" governs the
brief; this module pins the one part of it the `dod_gate` node grades against.

WHY THE MARKS EXIST. A `dod_gate` refusal is recorded as a
`livespec-needs-human-cause` ledger comment that quotes the item's reference line
as it stood at refusal. The brief carries every ledger comment, so once the owner
corrects the line the goal holds the corrected line in the description and the old
line quoted in that comment. A node reading the whole goal graded the quoted old
line and refused again, and a ledger comment can be neither edited nor deleted,
so one refusal followed by a correct repair left the item undispatchable.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands import _dispatcher_goal as goal
from livespec_orchestrator_beads_fabro.store import WorkItemComment
from livespec_orchestrator_beads_fabro.types import WorkItem

_BEGIN = (
    "--- BEGIN ITEM DEFINITION OF DONE (the item's own section; ledger comments are outside it) ---"
)
_END = "--- END ITEM DEFINITION OF DONE ---"
_REPO = Path("/data/projects/livespec-orchestrator-beads-fabro")

_OLD_LINE = "References: ## Scenario 132 — The stale single reference"
_NEW_LINE = "References: ## Scenario 132 — The proof chain, ## Scenario 137 — The corrected pair"
_SECTION = f"## Definition of Done\n\n- The gate grades this assertion.\n\n{_NEW_LINE}\n"
_DESCRIPTION = f"{_SECTION}\n## Defect\n\nProse that follows the section.\n"


def _item(*, description: str) -> WorkItem:
    return WorkItem(
        id="bd-ib-22wwob",
        type="bug",
        status="ready",
        title="A repaired item is graded on its corrected line",
        description=description,
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-29T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _refusal_comment() -> WorkItemComment:
    return WorkItemComment(
        text=(
            "livespec-needs-human-cause\n"
            f"the Definition of Done reference line reads `{_OLD_LINE}` and names only one scenario"
        ),
        author="dispatcher",
        created_at="2026-10-29T14:47:03Z",
    )


def _render(*, description: str, comments: tuple[WorkItemComment, ...] = ()) -> str:
    return goal.render_goal(
        item=_item(description=description),
        repo=_REPO,
        branch="feat/bd-ib-22wwob",
        comments=comments,
    )


def test_the_item_own_section_stands_between_one_begin_and_one_end_mark() -> None:
    rendered = _render(description=_DESCRIPTION)

    assert rendered.count(_BEGIN) == 1
    assert rendered.count(_END) == 1
    inside = rendered.split(_BEGIN)[1].split(_END)[0]
    assert inside.strip() == _SECTION.strip()


def test_a_reference_line_quoted_in_a_refusal_comment_stands_outside_the_marks() -> None:
    rendered = _render(description=_DESCRIPTION, comments=(_refusal_comment(),))

    inside = rendered.split(_BEGIN)[1].split(_END)[0]
    after = rendered.split(_END)[1]
    assert _NEW_LINE in inside
    assert _OLD_LINE not in inside
    assert _OLD_LINE in after
    assert after.index("Ledger comments") < after.index(_OLD_LINE)


def test_prose_after_the_section_is_not_inside_the_marks() -> None:
    rendered = _render(description=_DESCRIPTION)

    inside = rendered.split(_BEGIN)[1].split(_END)[0]
    assert "Prose that follows the section." not in inside
    assert "Prose that follows the section." in rendered.split(_END)[1]


def test_an_item_with_no_section_carries_no_marks() -> None:
    rendered = _render(description="## Defect\n\nNo section is declared here.\n")

    assert _BEGIN not in rendered
    assert _END not in rendered
