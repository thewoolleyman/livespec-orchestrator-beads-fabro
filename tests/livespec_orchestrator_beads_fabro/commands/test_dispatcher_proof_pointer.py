"""Tests for the Proof of Done pointer section: the splice and the read-back.

`test_proof_of_done_acceptance_scenarios132_133.py` binds the pointer write
through a real dispatch, which is where the ratified behaviour lives. This module
covers the shapes a healthy dispatch cannot produce — a description with no
Definition of Done section, a non-reserved heading level, an existing pointer
being replaced, and the malformed sections the staleness reader has to decline.

THE REPLACEMENT CASE IS THE LOAD-BEARING ONE. A pointer is written more than once
for the same item — again when the human-attested record lands — and an appending
writer would leave two `Proof of Done` sections. Both would look right in
isolation; the staleness fact would then have two run ids to compare and no rule
for choosing. The assertion is therefore on the COUNT of pointer headings, not on
the presence of the new one.
"""

from __future__ import annotations

import textwrap

from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    definition_of_done,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_pointer import (
    ProofPointer,
    description_with_pointer,
    description_with_updated_pointer,
    pointer_in,
)

_RECORD_URL = "https://example.test/owner/repo/pull/7#issuecomment-900"
_HUMAN_URL = "https://example.test/owner/repo/pull/7#issuecomment-901"


def _pointer(*, human: str | None = None) -> ProofPointer:
    return ProofPointer(
        pull_request=7,
        record_url=_RECORD_URL,
        run_id="01M3RUN",
        timestamp="2026-10-01T09:00:00Z",
        verdict="verified",
        human_attested_url=human,
    )


def _description(*, heading: str = "##", trailer: str = "") -> str:
    return (
        textwrap.dedent(f"""\
        Implement the slice.

        {heading} Definition of Done

        - The projection carries the parent field.

        References: ## Scenario 132 — A factory-captured proof
        """)
        + trailer
    )


def test_the_pointer_lands_after_the_definition_of_done_section() -> None:
    spliced = description_with_pointer(description=_description(), pointer=_pointer())

    assert spliced is not None
    head, _, pointer = spliced.partition("## Proof of Done")
    assert head.rstrip("\n") == _description().rstrip("\n")
    assert pointer.splitlines()[1:] == [
        "",
        "- Pull request: #7",
        f"- Verified record: {_RECORD_URL}",
        "- Run: 01M3RUN",
        "- Timestamp: 2026-10-01T09:00:00Z",
        "- Verdict: verified",
    ]


def test_the_human_attested_link_rides_only_when_the_pointer_carries_one() -> None:
    with_link = description_with_pointer(
        description=_description(), pointer=_pointer(human=_HUMAN_URL)
    )

    assert with_link is not None
    assert f"- Human-attested record: {_HUMAN_URL}" in with_link


def test_the_pointer_bullets_never_become_definition_of_done_assertions() -> None:
    """The heading level is inherited, so the pointer is a SIBLING section.

    The control is a `#`-level Definition of Done, where a hard-coded `##`
    pointer would nest INSIDE the section and its five bullets would parse as
    five new gradeable assertions. The assertion count is read through the
    production parser, which is the surface that would actually be fooled.
    """
    for heading in ("#", "##", "###"):
        spliced = description_with_pointer(
            description=_description(heading=heading), pointer=_pointer()
        )

        assert spliced is not None
        assert f"{heading} Proof of Done" in spliced
        section = definition_of_done(description=spliced)
        assert [one.text for one in section.assertions] == [
            "The projection carries the parent field."
        ]


def test_a_later_section_survives_the_splice_and_an_existing_pointer_is_replaced() -> None:
    first = description_with_pointer(
        description=_description(trailer="\n## Context\n\nSome notes.\n"),
        pointer=_pointer(),
    )

    assert first is not None
    second = description_with_pointer(description=first, pointer=_pointer(human=_HUMAN_URL))

    assert second is not None
    assert second.count("## Proof of Done") == 1
    assert f"- Human-attested record: {_HUMAN_URL}" in second
    assert second.rstrip("\n").endswith("## Context\n\nSome notes.")


def test_a_description_with_no_definition_of_done_section_is_refused() -> None:
    """Both arms: a first heading that is something else, and no heading at all."""
    assert (
        description_with_pointer(description="## Context\n\nNotes.\n", pointer=_pointer()) is None
    )
    assert description_with_pointer(description="Just prose.\n", pointer=_pointer()) is None


def test_a_section_body_already_ending_in_a_blank_line_gains_no_second_one() -> None:
    spliced = description_with_pointer(
        description="## Definition of Done\n\n- It works.\n\n", pointer=_pointer()
    )

    assert spliced == (
        "## Definition of Done\n"
        "\n"
        "- It works.\n"
        "\n"
        "## Proof of Done\n"
        "\n"
        "- Pull request: #7\n"
        f"- Verified record: {_RECORD_URL}\n"
        "- Run: 01M3RUN\n"
        "- Timestamp: 2026-10-01T09:00:00Z\n"
        "- Verdict: verified\n"
    )


def test_the_pointer_reads_back_from_the_description_it_was_written_into() -> None:
    spliced = description_with_pointer(
        description=_description(), pointer=_pointer(human=_HUMAN_URL)
    )

    assert spliced is not None
    assert pointer_in(description=spliced) == _pointer(human=_HUMAN_URL)


def test_an_unusable_pointer_section_reads_back_as_none() -> None:
    """A description with no section, and a section whose pull request is unusable.

    The pull request is the one field every consumer needs — the staleness fact
    reads the pull request's records off it — so a section carrying everything
    else is still not a usable pointer.
    """
    missing = "## Definition of Done\n\n- It works.\n"
    unnumbered = (
        "## Definition of Done\n\n- It works.\n\n"
        "## Proof of Done\n\n- Verified record: u\n- Run: r\n"
    )
    not_a_number = (
        "## Definition of Done\n\n- It works.\n\n## Proof of Done\n\n- Pull request: #seven\n"
    )

    assert pointer_in(description=missing) is None
    assert pointer_in(description=unnumbered) is None
    assert pointer_in(description=not_a_number) is None


def test_a_pointer_section_carrying_only_the_pull_request_reads_back_with_empty_fields() -> None:
    """A truncated section is still a pointer: the fields it lacks read as empty.

    This is the shape an older build's pointer has after a field is added, and it
    must not read back as "no pointer at all" — the staleness fact would then stop
    reporting on exactly the items whose pointers are oldest.
    """
    read = pointer_in(
        description=(
            "## Definition of Done\n\n- It works.\n\n"
            "## Proof of Done\n\nSome prose, not a bullet.\n\n- Pull request: 7\n"
        )
    )

    assert read == ProofPointer(pull_request=7, record_url="", run_id="", timestamp="", verdict="")


def test_the_in_place_update_rewrites_a_standing_pointer_and_nothing_else() -> None:
    """Total where the splice is partial, and both arms of that totality.

    The accept valve updates a pointer it has just READ BACK, so it needs no
    Definition of Done anchor — only the section's own position. The second
    assertion is the arm that makes "total" mean something: a description with no
    pointer section comes back unchanged rather than gaining one somewhere.
    """
    standing = description_with_pointer(
        description=_description(trailer="\n## Context\n\nSome notes.\n"), pointer=_pointer()
    )

    assert standing is not None
    updated = description_with_updated_pointer(
        description=standing, pointer=_pointer(human=_HUMAN_URL)
    )

    assert updated.count("## Proof of Done") == 1
    assert f"- Human-attested record: {_HUMAN_URL}" in updated
    assert f"- Verified record: {_RECORD_URL}" in updated
    assert updated.rstrip("\n").endswith("## Context\n\nSome notes.")
    assert updated.startswith(_description().rstrip("\n").split("## Definition of Done")[0])

    untouched = _description()

    assert description_with_updated_pointer(description=untouched, pointer=_pointer()) == untouched
