"""The degenerate document shapes the ratification read must survive.

A sibling of `test_spec_change_tier_ratification.py`, which carries the
DECISIONS. These are the shapes a governed history can legitimately hold that
are neither a proposal nor a well-formed revision record, and every one of them
must leave the hold standing rather than unwind the read.

They sit in their own module because they were found by a coverage measurement
taken after that module's Red was authored, and a Red's test bytes are fixed
across its Red-to-Green pair — the same split
`test_plan_result_proof_subject.py` records for the same reason.

EACH CASE IS PAIRED WITH THE RATIFICATION IT MUST NOT SWALLOW. A reader that
simply stopped on an unparseable neighbour would satisfy every absence here
while holding every item in the tenant, so each fixture carries a genuine
ratified record beside the malformed one and asserts the ratification survives.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._spec_change_tier_ratification import (
    ratified_proposal_topics,
)

_TOPIC = "spec-stated-judgement-and-spec-change-tier"


def _ratified(*, spec_root: Path, version: int = 205) -> Path:
    """One genuinely ratified record, and the directory it sits in."""
    directory = spec_root / "history" / f"v{version:03d}" / "proposed_changes"
    directory.mkdir(parents=True, exist_ok=True)
    _ = (directory / f"{_TOPIC}-revision.md").write_text(
        f"---\nproposal: {_TOPIC}.md\ndecision: accept\n---\n", encoding="utf-8"
    )
    return directory


def test_a_version_directory_with_no_proposed_changes_subdirectory_is_passed_over(
    tmp_path: Path,
) -> None:
    """A half-written version directory must not stop the walk at it."""
    (tmp_path / "history" / "v204").mkdir(parents=True)
    _ = _ratified(spec_root=tmp_path)

    assert ratified_proposal_topics(spec_root=tmp_path) == frozenset({_TOPIC})


def test_a_document_carrying_no_front_matter_at_all_ratifies_nothing(tmp_path: Path) -> None:
    """A README or a note dropped beside the records is not a revision record."""
    directory = _ratified(spec_root=tmp_path)
    _ = (directory / "README.md").write_text(
        "# Notes\n\ndecision: accept\nproposal: invented.md\n", encoding="utf-8"
    )

    assert ratified_proposal_topics(spec_root=tmp_path) == frozenset({_TOPIC})


def test_front_matter_with_no_closing_delimiter_is_read_to_the_end(tmp_path: Path) -> None:
    """A truncated record still ratifies what its fields name, and nothing more.

    The walk ends at the document rather than at a delimiter that never
    arrives, which is the arm a `break`-only reader never leaves.
    """
    directory = _ratified(spec_root=tmp_path)
    _ = (directory / "truncated-revision.md").write_text(
        "---\nproposal: truncated.md\ndecision: accept\n", encoding="utf-8"
    )

    assert ratified_proposal_topics(spec_root=tmp_path) == frozenset({_TOPIC, "truncated"})


def test_front_matter_lines_carrying_no_field_are_passed_over(tmp_path: Path) -> None:
    """A blank line, a bare word and an empty value are each not a field."""
    directory = _ratified(spec_root=tmp_path)
    _ = (directory / "sparse-revision.md").write_text(
        "---\n\nnotafield\nauthor:\nproposal: sparse.md\ndecision: modify\n---\n",
        encoding="utf-8",
    )

    assert ratified_proposal_topics(spec_root=tmp_path) == frozenset({_TOPIC, "sparse"})
