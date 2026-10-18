"""The dispatcher-owned admission-gates section of `AGENTS.md`, graded as ONE section.

Each test here grades ONE assertion of `bd-ib-zygea5`'s Definition of Done. On
2026-10-18 nine launching sessions each hand-rolled a "master ci-green" pre-check in
front of `drive`, read the pending latest default-branch run's empty conclusion as a
refusal, and held the launch -- in front of the bounded wait built for exactly that
state. The spec clause that forbids it was ratified separately as v160; what was
missing was a single place in this repository's agent-orientation surface that says
which admission conditions the Dispatcher owns, which gates a launch loop may add
itself, and which clause governs. This file grades that place.

WHY EVERY ASSERTION IS SCOPED TO ONE SECTION rather than to the whole file. The
Definition of Done asks for ONE section carrying all three facts, and `AGENTS.md` is
136 KB of prose in which each fact already appears somewhere -- the preflight numbers
under the factory section, the headroom clause in the spec, the build-currency
warning in the stale-build trap. A whole-file assertion would therefore pass on the
SCATTERED state this item exists to retire, which is the "instrument that cannot
return the other answer" failure the repository's own verification discipline names.
So the helper below extracts the single matching H2 and asserts the count is exactly
one, and every content assertion runs against that section's body alone.

Content assertions run against the WHITESPACE-FLATTENED section, because a phrase
`AGENTS.md` wraps across a line would otherwise be absent as a literal while present
as prose -- a silent pass for the wrong reason.

The fourth Definition-of-Done assertion -- that the pull request description records
the result of the wording review -- is not gradeable from the tree: the pull-request
body is rendered host-side and applied by the scripted `pr` stage, so it is carried
on the publication channel and in the commit message, not here.
"""

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_AGENT_INSTRUCTIONS = (_REPO_ROOT / "AGENTS.md").read_text()

# The distinguishing phrase of the section's own H2 heading. Matched on the heading
# LINE rather than anywhere in the body, so a section merely mentioning the subject
# cannot stand in for the section that owns it.
_HEADING_MARKER = "owns three dispatch-admission conditions"


def _section() -> str:
    """The one `AGENTS.md` H2 section carrying the dispatcher-owned admission gates.

    Fails as a genuine assertion -- not a collection or lookup error -- when the
    section is absent or when more than one heading matches, since "one section
    carries this" is itself an assertion of the Definition of Done.
    """
    chunks = ("\n" + _AGENT_INSTRUCTIONS).split("\n## ")
    matches = [chunk for chunk in chunks if _HEADING_MARKER in chunk.split("\n", 1)[0]]
    assert len(matches) == 1, (
        f"expected exactly one AGENTS.md H2 heading containing {_HEADING_MARKER!r}, "
        f"found {len(matches)}"
    )
    return " ".join(matches[0].split())


def test_section_lists_the_three_admission_conditions_the_dispatcher_owns() -> None:
    section = _section()

    # Condition 1: the bounded master-CI preflight wait, named as a WAIT so a reader
    # cannot carry away "the dispatcher checks master CI" and re-add a pre-check.
    assert "bounded master-CI preflight wait" in section
    assert "waits on a pending run" in section

    # Condition 2: the admission session-headroom assessment.
    assert "admission session-headroom assessment" in section

    # Condition 3: plugin build currency -- surfaced, and refused only below a
    # committed floor. Both halves are asserted, because a section naming only the
    # refusal would read as a blocking staleness gate, which is what the ratified
    # clause forbids.
    assert "Plugin build currency" in section
    assert "surfaced as a warning" in section
    assert "`dispatcher.minimum_release`" in section

    # Named as the set a caller must not duplicate, which is the whole point of
    # listing them together.
    assert "three admission conditions" in section


def test_section_lists_what_a_launch_loop_may_add_on_its_own() -> None:
    section = _section()

    # The three caller-owned gates, asserted one by one rather than as a single
    # sentence fragment, so a section keeping only some of them cannot pass.
    for gate in (
        "capacity on the factory host",
        "a launch slot the loop schedules itself",
        "the spacing between launches",
    ):
        assert gate in section, gate

    # And the boundary that keeps those three from growing back into the owned set.
    assert "MUST NOT re-implement, pre-empt or stand in for" in section


def test_section_names_the_governing_contracts_clause() -> None:
    section = _section()

    assert "`SPECIFICATION/contracts.md`" in section
    assert '"A caller does not gate a dispatch on the default branch\'s CI"' in section
