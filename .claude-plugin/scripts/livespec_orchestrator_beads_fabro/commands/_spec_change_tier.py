"""Whether one work-item is spec-change tier, decided by the shared judgement.

PURE. The autonomy-tier bullet of `SPECIFICATION/contracts.md` makes the tier a
DECISION rather than a declaration: it "is DECIDED by the spec-stated judgement
... never declared by the filer and never read off `spec_commitment_hint` (which
marks an implementation follow-up to an already ratified change)". This module
is that decision, and nothing else: the model call, the ledger record and the
hold each live in their own sibling, because the decision is the one part of
this feature that can be stated as a function.

THE RULE IS A CONJUNCTION AND BOTH HALVES MATTER. An item is spec-change tier
exactly when the classification is `feature` AND the judgement reports its
asked-for behaviour `partial` or `unstated`. Dropping the classification half
holds every bug whose fix the spec happens not to state, which is the exemption
the clause grants outright ("An item classified `bug`, `chore` or
`non_functional` is never spec-change tier"). Dropping the verdict half holds
every feature forever, including the implementation follow-ups to changes that
ratified years ago.

`partial` IS HELD, NOT ONLY `unstated`, and the independent review of this
plan's scoping required it (research note 005, finding 6: "`partial` needs
proposals too"). A behaviour the spec states HALF of is a behaviour whose other
half no clause governs, and the half that is missing is exactly what a
generalization would add.

THE STORED TYPE NEVER REACHES THIS DECISION. It is evidence the CLASSIFIER
weighs — `livespec_runtime.spec_stated.CLASSIFY_PROMPT` renders it and says in
as many words that it "is evidence ABOUT the item and never the answer" — so by
the time a classification arrives here the stored type has already been
weighed against the title and the description. Reading `item.type` again here
would re-admit the very datum the audit behind this plan measured wrong: 22 of
29 actionable ungoverned items were typed `bug`.

THE LINKED TOPIC IS DERIVED FROM THE ITEM, NOT FROM THE VERDICT. A
spec-change-tier item "MUST carry a linked proposed-change topic", and that
topic is the file stem a later ratification read looks for under
`<spec-root>/history/vNNN/proposed_changes/`. The generalization target is the
natural-looking source and is the wrong one: it is the judgement's own answer
and changes between judgements of one item, so a topic derived from it would
move under a proposal that had already been deposited — and the ratification
read would then look for a revision record nobody will ever write. The title is
stable for the life of the item, so the derivation is stable too.

AN ALREADY-LINKED TOPIC WINS over the derivation. Once a proposal has been
deposited the item's topic is a fact about the world rather than a name this
module may choose, and re-deriving it after a title edit would silently point
the hold at a stem that does not exist.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from livespec_runtime.spec_stated import ItemClass, StatedKind

if TYPE_CHECKING:
    from livespec_runtime.spec_stated import SpecStatedVerdict

    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "FEATURE_CLASS",
    "NO_TIER",
    "SPEC_CHANGE_KINDS",
    "SPEC_CHANGE_TIER",
    "SpecChangeTierDecision",
    "asked_for_behaviour",
    "decide_spec_change_tier",
    "proposal_topic_for",
]

# The one class the tier can apply to. The other three are exempt by the
# clause's own wording, so the exemption is this constant's complement rather
# than a second list that could disagree with it.
FEATURE_CLASS: ItemClass = "feature"

# The two verdicts that make a feature spec-change tier. `stated` is the third
# and makes it an implementation follow-up.
SPEC_CHANGE_KINDS: tuple[StatedKind, ...] = ("partial", "unstated")

# The two persisted tier values, spelled as the shared
# `livespec_runtime.spec_stated.SpecChangeTier` declares them so the two
# orchestrators store one vocabulary.
SPEC_CHANGE_TIER = "spec-change"
NO_TIER = "none"

_FIELD_ABSENT = "(none recorded)"

# A topic stem is lowercase-kebab, which is the form every proposal under
# `SPECIFICATION/proposed_changes/` already carries. The word cap keeps a long
# title from producing a stem no operator will type.
_TOPIC_WORD = re.compile(r"[a-z0-9]+")
_TOPIC_WORD_CAP = 5
_TOPIC_FALLBACK = "untitled"


@dataclass(frozen=True, kw_only=True)
class SpecChangeTierDecision:
    """One item's autonomy tier, with the judgement it was decided from.

    `verdict` and `classification` are carried rather than reduced to the
    `tier` flag, because the record this decision produces has to name them: a
    held item's operator needs the generalization target and the rationale to
    write the proposal, and `tier` alone names neither.

    `linked_proposal_topic` is `None` exactly for a decision that is not
    spec-change tier. An item nothing holds owes no proposal, and recording a
    topic for it would advertise a deposit nobody should make.
    """

    tier: Literal["spec-change", "none"]
    classification: ItemClass
    verdict: SpecStatedVerdict
    linked_proposal_topic: str | None

    @property
    def is_spec_change(self) -> bool:
        """Whether this decision puts the item in the spec-change tier."""
        return self.tier == SPEC_CHANGE_TIER


def asked_for_behaviour(*, item: WorkItem) -> str:
    """One item's ASKED-FOR behaviour, as the statement under judgement.

    The title, the description and the acceptance criteria, as one statement
    rather than three: the clause asks whether the spec states "the item's
    asked-for behaviour", and a title judged alone reports `unstated` for
    behaviour its own criteria state in full.

    The closure REASON is deliberately absent, and that is the one difference
    from the ledger-intent scan's `intent_statement`, which renders all four
    fields. That scan asks what an item RECORDED, including why it closed; this
    asks what it ASKS FOR, and a closure reason is an account of what happened
    rather than part of the request. Rendering it would make a closed item's
    post-hoc narrative part of the behaviour a proposal has to cover.
    """
    return "\n\n".join(
        [
            f"Work item {item.id}",
            f"Title: {_recorded(value=item.title)}",
            f"Description: {_recorded(value=item.description)}",
            f"Acceptance criteria: {_recorded(value=item.acceptance_criteria)}",
        ]
    )


def decide_spec_change_tier(
    *,
    item: WorkItem,
    classification: ItemClass,
    verdict: SpecStatedVerdict,
    linked_proposal_topic: str | None = None,
) -> SpecChangeTierDecision:
    """This item's tier, and the topic it must link when the tier holds.

    `linked_proposal_topic` is the topic already recorded against the item, when
    one is. It wins over the derivation for the reason the module docstring
    gives, and it is ignored entirely for a decision that is not spec-change
    tier — a released item carries no topic, so a stale one cannot be inherited
    into a record that says the item is free.
    """
    holds = classification == FEATURE_CLASS and verdict.kind in SPEC_CHANGE_KINDS
    if not holds:
        return SpecChangeTierDecision(
            tier=NO_TIER,
            classification=classification,
            verdict=verdict,
            linked_proposal_topic=None,
        )
    return SpecChangeTierDecision(
        tier=SPEC_CHANGE_TIER,
        classification=classification,
        verdict=verdict,
        linked_proposal_topic=linked_proposal_topic or proposal_topic_for(item=item),
    )


def proposal_topic_for(*, item: WorkItem) -> str:
    """The proposed-change topic stem this item's title derives.

    A title carrying no alphanumeric word at all derives the fallback stem
    rather than the empty string: an empty stem would make the ratification read
    look for `-revision.md`, which is a filename a directory listing can
    plausibly produce, so the hold would read as released the moment anyone
    deposited a proposal with no name.
    """
    words = _TOPIC_WORD.findall(item.title.casefold())[:_TOPIC_WORD_CAP]
    return "-".join(words) if words else _TOPIC_FALLBACK


def _recorded(*, value: str | None) -> str:
    """One statement field as the judge sees it, or the mark that it is unset.

    An absent field is NAMED rather than dropped, because a statement that
    simply omits the acceptance criteria is indistinguishable from one whose
    criteria the renderer failed to read — and the judge would then report
    `unstated` for the half it was never shown.
    """
    if value is None or value.strip() == "":
        return _FIELD_ABSENT
    return value.strip()
