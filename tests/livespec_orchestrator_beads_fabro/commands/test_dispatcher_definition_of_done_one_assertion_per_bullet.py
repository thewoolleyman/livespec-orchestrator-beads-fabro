"""The projected assertions of a conforming section are one per bullet.

The Definition-of-Done-section clause of `SPECIFICATION/contracts.md` fixes the
body as "one or more `- ` bullets, each carrying exactly one gradeable
assertion", optionally grouped under the two opt-out sub-headings with their
`Reason:` lines, plus exactly one `References:` line. So the BULLET is the unit
of grading, and the set projected to the `proof_grade` node must carry exactly
one entry per bullet, in the section's own order.

THE DISCRIMINATING CASE IS A BULLET CARRYING TWO SENTENCES. The shared
segmenter the two legacy criteria sources use splits a block into sentences,
which is right for a free-form criteria field and wrong here: a bullet is one
assertion whatever punctuation it contains, and a split one is graded twice —
once against evidence that answers the whole bullet and once against half of it.
Measured on `livespec-overseer`'s `overseer-uzvcbn.5`, that split is what made
the deterministic projection and every pre-spend check disagree about what the
section asserts.

The projection is read through `factory_captured_assertions`, the function whose
value the Dispatcher base64-encodes into `LIVESPEC_PROOF_GRADE_ASSERTIONS`, so
this is the set the sandbox's own per-assertion grade reads rather than a
rendering of it.
"""

from __future__ import annotations

from dataclasses import replace

from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    definition_of_done,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_grade_program import (
    factory_captured_assertions,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

# Three factory bullets and one host bullet. The first factory bullet carries
# TWO sentences and the second carries a parenthesized abbreviation plus a
# version string, which are the two shapes the sentence splitter treats
# differently from each other — so a projection that still segments by sentence
# cannot match this expectation by accident.
_SECTION = (
    "## Definition of Done\n"
    "\n"
    "- The wall refuses the item. It names the offending line verbatim.\n"
    "- The record names both digests (for example v0.88.0) and nothing else.\n"
    "- The drain excludes the refused item.\n"
    "\n"
    "### Host-captured\n"
    "\n"
    "Reason: the proof needs the released build installed on an operator host.\n"
    "\n"
    "- The preflight script passes its judge the same rubric bytes.\n"
    "\n"
    "References: ## Effective acceptance criteria\n"
)


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id="bd-ib-gob6gl",
        type="bug",
        status="ready",
        title="One assertion per bullet",
        description=_SECTION,
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-22T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )
    return replace(base, **overrides)


def test_the_projected_assertions_are_exactly_one_per_factory_bullet_in_order() -> None:
    assert factory_captured_assertions(item=_item()) == (
        "The wall refuses the item. It names the offending line verbatim.",
        "The record names both digests (for example v0.88.0) and nothing else.",
        "The drain excludes the refused item.",
    )


def test_every_bullet_of_the_section_yields_exactly_one_assertion_in_order() -> None:
    # The control for the projection above: the host bullet must be present in
    # the parse and absent from the factory projection, so a parse that dropped
    # every opt-out bullet could not satisfy both expectations at once.
    section = definition_of_done(description=_SECTION)

    assert [(one.text, one.proof_mode) for one in section.assertions] == [
        (
            "The wall refuses the item. It names the offending line verbatim.",
            "factory_captured",
        ),
        (
            "The record names both digests (for example v0.88.0) and nothing else.",
            "factory_captured",
        ),
        ("The drain excludes the refused item.", "factory_captured"),
        ("The preflight script passes its judge the same rubric bytes.", "host_captured"),
    ]


def test_a_wrapped_bullet_is_one_assertion_carrying_its_continuation() -> None:
    # A bullet hard-wrapped across physical lines is still one bullet, so the
    # continuation joins it rather than being graded on its own.
    description = (
        "## Definition of Done\n"
        "\n"
        "- The wall refuses an item whose section carries a line that is\n"
        "  neither a bullet nor the reference line.\n"
        "\n"
        "References: ## Effective acceptance criteria\n"
    )

    section = definition_of_done(description=description)

    assert tuple(one.text for one in section.assertions) == (
        "The wall refuses an item whose section carries a line that is"
        " neither a bullet nor the reference line.",
    )
