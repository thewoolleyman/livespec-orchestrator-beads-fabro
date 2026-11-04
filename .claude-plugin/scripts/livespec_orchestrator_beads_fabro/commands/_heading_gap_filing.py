"""The gap-tied work-item record `capture-impl-gaps` files for one heading.

Per `SPECIFICATION/contracts.md` and Scenario 205 of
`SPECIFICATION/scenarios.md`, a consented gap capture creates a work-item
carrying the `origin:gap-tied` and `gap-id:<stable-id>` labels, "whose title
names the uncovered heading verbatim and whose description names the coverage
entry the implementing change MUST fill with the exercising test".

WHY THIS IS A PRIMITIVE RATHER THAN A SNIPPET IN THE OPERATION PROSE. The
record is composed by whichever front-end the operator reaches — the Claude,
Codex and pi bindings all read one prose file, and the `orchestrator`
contract CLI files through its own path — so a composition written as prose
is a composition each one can get subtly differently. It is also the only
way the four properties above are GRADEABLE: a prose block cannot be run,
and the two labels do not exist until the store writes the record.

WHY THE TITLE CARRIES THE HEADING VERBATIM AND NOT A PARAPHRASE. The heading
is the KEY the coverage entry matches on, so a reworded title leaves an
operator unable to find the registry row the item is about — and the match is
exact, so even a trimmed `## ` marker breaks it.

WHY THE DESCRIPTION NAMES ALL THREE IDENTIFYING FIELDS. The registry holds 252
rows here, several of which legitimately carry the same heading text under
different files. A description naming only the heading would leave the
implementing change guessing which row it owes a test value to.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro._ids import new_work_item_id
from livespec_orchestrator_beads_fabro.commands._heading_coverage_map import (
    COVERAGE_RELATIVE_PATH,
    TODO_SENTINEL,
)
from livespec_orchestrator_beads_fabro.commands._heading_gaps import SpecHeading
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "heading_gap_description",
    "heading_gap_title",
    "heading_gap_work_item",
]

# The create-time shell every capture front-end files into. The intake
# Definition-of-Ready router transitions it immediately afterwards, so this is
# never the state the operator sees.
_CREATE_TIME_STATUS = "pending-approval"


def heading_gap_title(*, gap: SpecHeading) -> str:
    """The drafted title: what the implementing change delivers, naming the heading."""
    return f"Bind an exercising test to {gap.spec_root}/{gap.spec_file} {gap.heading}"


def heading_gap_description(*, gap: SpecHeading) -> str:
    """The drafted description: the registry row to fill, named field by field."""
    registry = COVERAGE_RELATIVE_PATH.as_posix()
    return (
        f"No test exercises the H2 heading {gap.heading} of "
        f"{gap.spec_root}/{gap.spec_file}.\n\n"
        f"Fill the {registry} entry identified by "
        f"spec_root {gap.spec_root}, spec_file {gap.spec_file} and heading "
        f"{gap.heading}: replace its `test` value — absent, the "
        f"{TODO_SENTINEL} sentinel, or a test that no longer exists — with the "
        f"node id of the test this change adds. Add the entry when the registry "
        f"carries none."
    )


def heading_gap_work_item(
    *,
    gap: SpecHeading,
    prefix: str,
    rank: str,
    captured_at: str,
) -> WorkItem:
    """The gap-tied record for one uncovered heading.

    `rank` and `captured_at` are the CALLER's to supply: a multi-gap pass
    threads successive ranks so its items land in filing order, and the clock
    is the front-end's so this composition stays a pure function of its
    inputs.
    """
    return WorkItem(
        id=new_work_item_id(prefix=prefix),
        type="task",
        status=_CREATE_TIME_STATUS,
        title=heading_gap_title(gap=gap),
        description=heading_gap_description(gap=gap),
        origin="gap-tied",
        gap_id=gap.gap_id,
        rank=rank,
        assignee=None,
        depends_on=(),
        captured_at=captured_at,
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        spec_commitment_hint=None,
    )
