"""Tests for the RATIFICATION half of the spec-change-tier hold.

The clause makes the hold a read of the spec history: an item stays held until
"the linked topic's revision record under `<spec-root>/history/vNNN/
proposed_changes/` carries decision `accept` or `modify`". That read "needs no
model, so it MUST fail closed", which is what every case here grades.

THE THREE DECISIONS ARE NOT TWO. `accept` and `modify` both ratify and `reject`
does not, which is Scenario 206's "A rejected or narrowed proposal does not
release the hold" — so a reader that merely looked for a revision record, or
one that keyed on `accept` alone, is wrong in opposite directions and each
needs its own case.

EVERY ABSENCE IS NOT-RATIFIED. An item linking no topic at all, a topic no
revision record names, a spec root carrying no history, and a record whose
front matter cannot be read are four different ways of failing to measure, and
the clause admits exactly one answer for all of them: the hold stands.

THE POSITIVE CASE IS WHAT MAKES THEM EVIDENCE. Without a topic this reader
genuinely ratifies, a reader answering False unconditionally satisfies every
absence in the module — and would hold every item in the tenant for ever.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._spec_change_tier_ratification import (
    ratified_proposal_topics,
    topic_is_ratified,
)

_TOPIC = "spec-stated-judgement-and-spec-change-tier"


def _revision(*, spec_root: Path, version: int, topic: str, decision: str) -> None:
    directory = spec_root / "history" / f"v{version:03d}" / "proposed_changes"
    directory.mkdir(parents=True, exist_ok=True)
    _ = (directory / f"{topic}-revision.md").write_text(
        "---\n"
        f"proposal: {topic}.md\n"
        f"decision: {decision}\n"
        "revised_at: 2026-10-24T00:00:00Z\n"
        "---\n\n"
        "## Decision and Rationale\n\nSomething was decided.\n",
        encoding="utf-8",
    )


def test_an_accepted_topic_is_ratified(tmp_path: Path) -> None:
    """The positive case, without which every absence below is free."""
    _revision(spec_root=tmp_path, version=205, topic=_TOPIC, decision="accept")

    assert topic_is_ratified(spec_root=tmp_path, topic=_TOPIC) is True


def test_a_modified_topic_is_ratified(tmp_path: Path) -> None:
    """`modify` ratifies beside `accept`, which the clause names in one breath."""
    _revision(spec_root=tmp_path, version=205, topic=_TOPIC, decision="modify")

    assert topic_is_ratified(spec_root=tmp_path, topic=_TOPIC) is True


def test_a_rejected_topic_is_not_ratified(tmp_path: Path) -> None:
    """Scenario 206's rejected proposal: a revision record is not a ratification."""
    _revision(spec_root=tmp_path, version=205, topic=_TOPIC, decision="reject")

    assert topic_is_ratified(spec_root=tmp_path, topic=_TOPIC) is False


def test_a_topic_no_revision_record_names_is_not_ratified(tmp_path: Path) -> None:
    """A filed proposal nobody has revised yet, which is the ordinary held state."""
    _revision(spec_root=tmp_path, version=205, topic="some-other-topic", decision="accept")

    assert topic_is_ratified(spec_root=tmp_path, topic=_TOPIC) is False


def test_an_item_linking_no_topic_at_all_is_not_ratified(tmp_path: Path) -> None:
    """The fail-closed answer for the one state a held item starts in."""
    _revision(spec_root=tmp_path, version=205, topic=_TOPIC, decision="accept")

    assert topic_is_ratified(spec_root=tmp_path, topic=None) is False


def test_a_spec_root_carrying_no_history_ratifies_nothing(tmp_path: Path) -> None:
    """A read that cannot be taken holds, rather than releasing on an empty set."""
    assert ratified_proposal_topics(spec_root=tmp_path / "absent") == frozenset()
    assert topic_is_ratified(spec_root=tmp_path / "absent", topic=_TOPIC) is False


def test_a_revision_record_naming_no_proposal_ratifies_nothing(tmp_path: Path) -> None:
    """A record that cannot name what it revised supports no release."""
    directory = tmp_path / "history" / "v205" / "proposed_changes"
    directory.mkdir(parents=True)
    _ = (directory / "orphan-revision.md").write_text(
        "---\ndecision: accept\n---\n\nNothing names a proposal.\n", encoding="utf-8"
    )

    assert ratified_proposal_topics(spec_root=tmp_path) == frozenset()


def test_a_proposal_document_is_not_read_as_its_own_ratification(tmp_path: Path) -> None:
    """A filed proposal names its topic and carries no decision; it ratifies nothing.

    The two documents sit in the same directory, so a reader keying on the
    `topic` field would read every filed proposal as ratified the moment it was
    deposited — which releases the hold the deposit exists to earn.
    """
    directory = tmp_path / "history" / "v205" / "proposed_changes"
    directory.mkdir(parents=True)
    _ = (directory / f"{_TOPIC}.md").write_text(
        f"---\ntopic: {_TOPIC}\nauthor: someone\n---\n\n## Proposal\n", encoding="utf-8"
    )

    assert topic_is_ratified(spec_root=tmp_path, topic=_TOPIC) is False


def test_a_decision_in_the_prose_rather_than_the_front_matter_ratifies_nothing(
    tmp_path: Path,
) -> None:
    """A revision record's narration quotes these fields routinely.

    The scan therefore stops at the closing delimiter, exactly as the
    cut-instant reader does and for the same reason: a record ABOUT ratification
    decisions would otherwise supply one.
    """
    directory = tmp_path / "history" / "v205" / "proposed_changes"
    directory.mkdir(parents=True)
    _ = (directory / f"{_TOPIC}-revision.md").write_text(
        f"---\nproposal: {_TOPIC}.md\nrevised_at: 2026-10-24T00:00:00Z\n---\n\n"
        "The reviewer wrote decision: accept in their note.\n",
        encoding="utf-8",
    )

    assert topic_is_ratified(spec_root=tmp_path, topic=_TOPIC) is False


def test_a_ratification_anywhere_in_the_history_releases_its_topic(tmp_path: Path) -> None:
    """The whole history is the population, not only the newest version.

    A topic ratified three revisions ago is ratified, and a reader scanning only
    the latest directory would hold every item whose proposal landed before the
    most recent revise pass.
    """
    _revision(spec_root=tmp_path, version=100, topic=_TOPIC, decision="accept")
    _revision(spec_root=tmp_path, version=205, topic="later-topic", decision="accept")

    assert ratified_proposal_topics(spec_root=tmp_path) == frozenset({_TOPIC, "later-topic"})


def test_a_record_that_cannot_be_read_as_utf8_ratifies_nothing(tmp_path: Path) -> None:
    """One invalid byte must not unwind the dispatch path, nor release a hold."""
    directory = tmp_path / "history" / "v205" / "proposed_changes"
    directory.mkdir(parents=True)
    _ = (directory / f"{_TOPIC}-revision.md").write_bytes(
        b"---\nproposal: " + _TOPIC.encode() + b".md\ndecision: \xff\xfe\n---\n"
    )

    assert topic_is_ratified(spec_root=tmp_path, topic=_TOPIC) is False
