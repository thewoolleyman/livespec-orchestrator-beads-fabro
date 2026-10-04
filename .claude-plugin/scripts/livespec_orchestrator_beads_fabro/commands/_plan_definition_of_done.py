"""A plan epic's Definition of Done — authored, rendered, and recorded.

The plan Definition-of-Done clause of `SPECIFICATION/contracts.md` (v115) binds
an epic whose `plan_slug` names a live `plan/<slug>/` directory: its
`description` MUST carry the section as its FIRST heading, and the `plan`
front-end MUST author it at plan creation, recording the maintainer's own
statement of what done means VERBATIM in the plan's initial research note
beside the assertions derived from it.

WHY THE STATEMENT AND THE ASSERTIONS TRAVEL AS ONE VALUE. They are two halves
of one act of authoring: the assertions are a DERIVATION of the statement, and
the clause requires the derivation to be auditable against its source. Passing
them as two independent parameters would let a caller record assertions with no
statement, or a statement with no assertions, and nothing downstream could tell
either case from a complete one — the plan's own problem statement was that the
maintainer's intent arrives per plan and never reaches a gradeable assertion.

WHY THE STATEMENT IS RENDERED AS A PLAIN PARAGRAPH. "Verbatim" has to survive a
line break. A blockquote (`> `) or list-marker rendering prefixes every
continuation line and so changes the bytes of any statement longer than one
line, while still LOOKING like a faithful record — the maintainer's words would
be quoted everywhere and byte-identical nowhere.

WHY THE ANCHOR PROSE PRECEDES THE HEADING. The work-item grammar permits prose
before the section heading, and the epic's `Plan anchor for plan/<slug>.` line
has to go somewhere. After the bullets it would fall INSIDE the section body,
where the shared segmenter starts a fresh block at a blank line and would grade
it as an assertion the maintainer never wrote.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    SUBJECT_PLAN,
    definition_of_done,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
        DefinitionOfDone,
    )

__all__: list[str] = [
    "PlanDefinitionOfDone",
    "plan_definition_of_done",
    "plan_definition_of_done_section",
    "plan_research_note",
]

# The reserved heading in its AUTHORED form. The parse matches on the
# case-folded title, so this is the form a reader sees rather than a second
# source of truth for the match; what proves the two agree is the round trip
# through the real primitive, not a shared constant.
_SECTION_HEADING = "## Definition of Done"
_STATEMENT_HEADING = "## The maintainer's statement of what done means"
_DERIVATION_HEADING = "## Definition of Done assertions derived from that statement"


@dataclass(frozen=True, kw_only=True)
class PlanDefinitionOfDone:
    """One plan's Definition of Done, as the authoring session captured it.

    `statement` is the maintainer's own words, recorded verbatim and never
    reworded. `assertions` are the behavioural assertions derived from it, one
    per bullet.

    There is deliberately NO reference-line field. Zero or one `References:`
    line is valid for a plan — a plan MAY precede the specification it will
    ratify — so a section authored without one is conforming rather than
    incomplete, and the parse reads a reference line the same way whoever
    wrote it. Authoring one is additive if a plan ever needs it.
    """

    statement: str
    assertions: tuple[str, ...]


def plan_definition_of_done(*, description: str) -> DefinitionOfDone:
    """Parse one plan epic's description through the ONE primitive, as a plan.

    Every plan-side reader goes through here rather than calling the primitive
    with a `subject` argument of its own. The clause says outright that no
    surface may parse the section by another path, and a per-caller `subject`
    is exactly how one caller would come to read a plan epic under the
    work-item rules — reporting a bare bullet as `factory_captured` and owing a
    reference line the plan never needed, both of which look like real findings.
    """
    return definition_of_done(description=description, subject=SUBJECT_PLAN)


def plan_definition_of_done_section(*, definition: PlanDefinitionOfDone) -> str:
    """Render one plan Definition of Done as the epic description's first heading."""
    return "\n".join((_SECTION_HEADING, "", *(f"- {one}" for one in definition.assertions)))


def plan_research_note(*, definition: PlanDefinitionOfDone, research_text: str) -> str:
    """Render the initial research note: the statement verbatim, then the derivation.

    The session's own research follows both, so the record of what the maintainer
    asked for leads the note rather than being appended beneath whatever analysis
    happened to be written first.
    """
    return "\n".join(
        (
            _STATEMENT_HEADING,
            "",
            definition.statement,
            "",
            _DERIVATION_HEADING,
            "",
            *(f"- {one}" for one in definition.assertions),
            "",
            research_text,
        )
    )
