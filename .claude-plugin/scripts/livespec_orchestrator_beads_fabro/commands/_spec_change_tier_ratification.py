"""The ratification half of the spec-change-tier hold, read off the spec history.

The autonomy-tier bullet of `SPECIFICATION/contracts.md` section "Grooming and
slice-size calibration" makes half of the hold a read of the governed history:
a held item stays held until "the linked topic's revision record under
`<spec-root>/history/vNNN/proposed_changes/` carries decision `accept` or
`modify`". The clause then says what KIND of read it is — "That hold is a read
of the spec history and needs no model, so it MUST fail closed" — which is the
whole design brief of this module.

FOUR PROPERTIES AN EDITOR MUST NOT INVERT.

A REVISION RECORD IS NOT A RATIFICATION. `reject` is a decision like the other
two and writes exactly the same kind of record, so a reader that merely found a
record for the topic would release Scenario 206's rejected proposal — "the item
stays held and the refusal names the topic". The decision set is therefore
explicit and closed.

A FILED PROPOSAL IS NOT ITS OWN RATIFICATION, and the two documents share a
directory. A proposal carries `topic: <slug>` and a revision record carries
`proposal: <slug>.md` plus a `decision`, so a reader keyed on either name alone
releases every topic the moment its proposal is DEPOSITED — which is the
deposit the hold exists to make somebody act on. The topic is therefore read
off `proposal` and only where a ratifying `decision` sits beside it.

THE SCAN STOPS AT THE FRONT MATTER'S CLOSING DELIMITER, exactly as
`_ledger_intent_cut` does over the same files and for the same reason: a
revision record's prose quotes these fields routinely, so a whole-document scan
would let a record ABOUT ratification decisions supply one.

EVERY FAILURE TO MEASURE LEAVES THE HOLD STANDING. An absent history, an
unreadable record, a record naming no proposal and an item linking no topic at
all are four different absences and the clause admits one answer for all of
them. That is the fail-closed direction the clause names outright, and it is
the opposite of the fail-open direction the CLASSIFICATION takes — the two live
in different modules partly so that difference stays visible.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

if TYPE_CHECKING:
    from pathlib import Path

__all__: list[str] = [
    "RATIFYING_DECISIONS",
    "ratified_proposal_topics",
    "topic_is_ratified",
]

# The two decisions the clause names, as a closed set. `reject` is deliberately
# absent rather than tested for: a decision vocabulary that grows gains a
# NON-ratifying member by default, which is the safe direction.
RATIFYING_DECISIONS = frozenset({"accept", "modify"})

_HISTORY_DIRNAME = "history"
_PROPOSED_CHANGES_DIRNAME = "proposed_changes"
_VERSION_GLOB = "v*"
_RECORD_GLOB = "*.md"
_FRONTMATTER_DELIMITER = "---"
_DECISION_FIELD = "decision"
_PROPOSAL_FIELD = "proposal"
_DOCUMENT_SUFFIX = ".md"


def ratified_proposal_topics(*, spec_root: Path) -> frozenset[str]:
    """Every proposed-change topic the governed history records as ratified.

    The WHOLE history is the population rather than the newest version alone: a
    topic ratified three revisions ago is ratified, and a reader scanning only
    the latest directory would hold every item whose proposal landed before the
    most recent revise pass.
    """
    history = spec_root / _HISTORY_DIRNAME
    if not history.is_dir():
        return frozenset()
    topics: set[str] = set()
    for version in sorted(history.glob(_VERSION_GLOB)):
        topics.update(_ratified_in(directory=version / _PROPOSED_CHANGES_DIRNAME))
    return frozenset(topics)


def topic_is_ratified(*, spec_root: Path, topic: str | None) -> bool:
    """Whether one linked topic's revision record ratifies it.

    A `None` topic answers False BEFORE the history is read, which is the
    fail-closed answer for the state every held item starts in: an item that
    links no proposal has nothing a revision record could ratify, and reading
    the history for it would spend a directory walk on a question already
    settled.
    """
    if topic is None:
        return False
    return topic in ratified_proposal_topics(spec_root=spec_root)


def _ratified_in(*, directory: Path) -> set[str]:
    """Every topic one version's `proposed_changes/` directory ratifies."""
    if not directory.is_dir():
        return set()
    topics: set[str] = set()
    for candidate in sorted(directory.glob(_RECORD_GLOB)):
        topic = _ratified_topic(path=candidate)
        if topic is not None:
            topics.add(topic)
    return topics


def _ratified_topic(*, path: Path) -> str | None:
    """The topic one revision record ratifies, or `None` when it ratifies none.

    `UnicodeDecodeError` is caught beside `OSError` and it is the arm that
    bites: a record carrying one invalid byte raises a `ValueError` subclass
    rather than an `OSError`, so a catch naming only `OSError` lets it escape
    through the pre-dispatch wall and the intake router as a traceback.
    """
    read = attempt(
        action=lambda: path.read_text(encoding="utf-8"), exceptions=(OSError, UnicodeDecodeError)
    )
    if isinstance(read, AttemptFailure):
        return None
    fields = _front_matter(text=read)
    if fields.get(_DECISION_FIELD) not in RATIFYING_DECISIONS:
        return None
    proposal = fields.get(_PROPOSAL_FIELD)
    if proposal is None:
        return None
    return proposal.removesuffix(_DOCUMENT_SUFFIX)


def _front_matter(*, text: str) -> dict[str, str]:
    """Every `key: value` of one document's front matter, and nothing below it."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != _FRONTMATTER_DELIMITER:
        return {}
    fields: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == _FRONTMATTER_DELIMITER:
            break
        key, separator, value = line.partition(":")
        if separator and value.strip():
            fields[key.strip()] = value.strip()
    return fields
