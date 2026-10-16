"""The plan operation prose's release-rule paragraph, after the v148 plan-record clause.

The clause moved the release rule's subject off the governed repository and onto
each record — "The release rule is judged against the RELEASE REPOSITORY of each
record ... named by the first whitespace-delimited word of the first installed
build identifier the record names" — and named the venue the tags come from:
"Every repository's release tags — the governed repository's included — MUST be
read by an authenticated read of its remote on the forge that hosts the governed
repository, and MUST NOT be read from any local clone or worktree."

WHY THE PROSE IS THE SUBJECT AND NOT A SECOND READING OF THE GATE. This paragraph
is what a session planning a plan record reads BEFORE it captures one, and it is
the only place that tells a publisher which repository its record will be judged
against. A publisher following the retired paragraph records a release of a
sibling repository and reads that the gate will judge it against the governed
one — so it either omits the identifier or expects a refusal, and the behaviour
the gate now ships is unreachable from the instructions. The gate's own behaviour
is bound by `tests/livespec_orchestrator_beads_fabro/commands/`; nothing there can
observe what the operator was told.

EVERY NEEDLE IS READ FROM A WHITESPACE-COLLAPSED PARAGRAPH. The prose is
hard-wrapped, so a needle straddling a line break fails while the paragraph says
exactly the thing — a probe that can only fail SILENTLY. Collapsing first is what
makes these assertions able to return the other answer.

EACH CASE CARRIES THE RETIRED CLAIM IT REPLACES. "The paragraph mentions the
release repository" is otherwise equally consistent with a paragraph that
mentions it while still telling a publisher the governed repository's tags decide
the verdict, which is the claim that has to be gone rather than merely joined.
"""

from __future__ import annotations

import re
from pathlib import Path

_PROSE = Path(".claude-plugin") / "prose" / "plan.md"


def _release_paragraph() -> str:
    """The release-rule paragraph, whitespace-collapsed to one line.

    Located by the released-artifact requirement rather than by line number, so the
    paragraph stays findable as the file around it changes. The paragraph is the
    blank-line-delimited block that sentence sits in, which is what keeps a needle
    from matching a neighbouring paragraph and reporting the rule as stated when
    the words are somewhere else entirely.

    THAT ANCHOR IS DELIBERATELY ONE THE RETIRED PARAGRAPH ALSO CARRIED. It is the
    half of the rule v148 left standing, so this locator finds the pre-v148
    paragraph too and the needles below then FAIL on it. An anchor taken from the
    new wording would instead make the locator itself the assertion — it would
    raise on the old paragraph rather than report which claim is missing, and it
    could never distinguish a paragraph that states the rule from one that merely
    contains the phrase the locator searched for.
    """
    assert _PROSE.is_file(), _PROSE
    blocks = _PROSE.read_text(encoding="utf-8").split("\n\n")
    matching = [one for one in blocks if "installed through its normal installation path" in one]
    assert len(matching) == 1, matching
    return re.sub(r"\s+", " ", matching[0]).strip()


def test_the_release_paragraph_names_the_record_s_own_release_repository() -> None:
    paragraph = _release_paragraph()

    # The subject of the rule: the repository the record's OWN installed build
    # identifier names, which is what a publisher needs in order to know that
    # naming a sibling's release is a supported thing to do.
    assert "release repository" in paragraph
    assert "installed build identifier" in paragraph
    # The retired paragraph attached the rule's condition to the governed
    # repository; that is the claim this change had to remove, not merely join.
    assert "the governed repository carries at least one release tag" not in paragraph


def test_the_release_paragraph_states_the_tags_are_read_from_the_forge_remote() -> None:
    paragraph = _release_paragraph()

    # The venue. A publisher reading only "the repository does not carry it" cannot
    # tell whether an unpushed local tag counts, and the answer is that it does not.
    assert "forge" in paragraph
    assert "remote" in paragraph
    # The fail-closed half, which the retired reading inverted: an unreadable forge
    # rejects rather than reading as "no release applies".
    assert "reject" in paragraph
