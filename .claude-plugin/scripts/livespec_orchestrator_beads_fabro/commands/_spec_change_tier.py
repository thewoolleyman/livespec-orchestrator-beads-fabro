"""Whether one work-item is SPEC-CHANGE TIER, and the ledger record that says so.

PURE. The autonomy-tier bullet of `SPECIFICATION/contracts.md` section
"Grooming and slice-size calibration" puts the tier on ONE authority — "the
spec-change tier is DECIDED by the spec-stated judgement ..., never declared by
the filer and never read off `spec_commitment_hint` (which marks an
implementation follow-up to an already ratified change)" — and Scenario 206
exercises it. This module owns the DECISION and the RECORD, and no opinion
about where either is spent.

WHY `spec_commitment_hint` IS NOT AN INPUT, AND THE READING IT REPLACES. Two
predicates in this package read that field as though it MEANT spec-change tier:
`_dispatcher_policy_overrides` pinned every hint-carrying item to the manual
admission floor, and `_plan_disposition` refused to dispose one. Both are
INVERTED — the hint marks a follow-up to a change that has ALREADY ratified,
which is the one kind of item the tier is never about. The field is therefore
absent from this module's inputs entirely, which is what makes the inversion
unrepeatable rather than merely corrected.

FIVE PROPERTIES AN EDITOR MUST NOT INVERT.

THE CLASS DECIDES FIRST, AND THE CLASS IS THE JUDGEMENT'S, with the stored type
as evidence. An item the judgement classifies `bug`, `chore` or `non_functional`
"is never spec-change tier and routes as every other factory-dispatchable
item", so `holds` answers False for it WITHOUT consulting the stated kind — not
as an optimization but because no stated kind is taken for such an item, and a
decision that read one would be reading a field nobody measured.

A `stated` VERDICT IS NOT ON ITS OWN A RELEASE. The hold stands "until BOTH
hold": the linked topic's revision record carries decision `accept` or `modify`,
AND the judgement returns `stated`. So a feature whose behaviour the ratified
tree now states while its OWN proposal was rejected or narrowed stays held —
Scenario 206's "A rejected or narrowed proposal does not release the hold". That
is the `linked_proposal_topic is not None` arm, and it is the arm most easily
deleted as redundant.

AN ITEM CARRYING NO LINKED TOPIC AND A `stated` VERDICT IS NOT HELD, which is
the mirror of the arm above and is what keeps the rule from holding every
feature there is. Such an item is Scenario 206's "A follow-up to a ratified
change is not held": nothing was ever proposed for it because the ratified text
already states what it asks for.

`topic_ratified` IS CARRIED ON THE VERDICT rather than asked at read time,
because the record is what a mechanical hold reads between passes and a reader
that re-derived it would be a second authority on a question the recording pass
already answered. The hold's own freshness comes from the ratification read the
gate takes BESIDE the record, not from this value.

THE RECORD IS A LEDGER COMMENT, for the reason `_dispatcher_dod_judgement_record`
gives for its own: ledger writers here may share nothing but the Beads server
(`.ai/ledger-writers-are-multi-host.md`), so a tier cached under a host state
root would be invisible to the next writer and every pass would re-classify.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

__all__: list[str] = [
    "CLASS_FEATURE",
    "KIND_STATED",
    "LINKED_TOPIC_LABEL_PREFIX",
    "SPEC_CHANGE_TIER_COMMENT_MARKER",
    "TIER_NONE",
    "TIER_SPEC_CHANGE",
    "SpecChangeTierVerdict",
    "linked_proposal_topic",
    "recorded_spec_change_tier",
    "spec_change_tier_comment",
]

TIER_SPEC_CHANGE = "spec-change"
TIER_NONE = "none"

# The one class the tier is ever about, and the one verdict kind that can
# release it. Both are the shared judgement's own vocabulary
# (`livespec_runtime.spec_stated`), named here so the decision below reads as
# the clause reads rather than as two bare string comparisons.
CLASS_FEATURE = "feature"
KIND_STATED = "stated"

# How an item CARRIES the linked proposed-change topic the clause requires of a
# spec-change-tier item. A beads label, which is how every other per-item
# property this store has no native column for is carried, so the topic lives
# in the one place every writer on every host can see it.
LINKED_TOPIC_LABEL_PREFIX = "proposal-topic:"

SPEC_CHANGE_TIER_COMMENT_MARKER = "livespec-spec-change-tier"

_WORK_ITEM_FIELD = "work-item"
_STAGE_FIELD = "stage"
_TIER_FIELD = "tier"
_CLASS_FIELD = "item-class"
_KIND_FIELD = "stated-kind"
_GENERALIZATION_FIELD = "generalization-target"
_TOPIC_FIELD = "linked-proposal-topic"
_RATIFIED_FIELD = "topic-ratified"
_FIELD_SEPARATOR = ": "
_TRUE = "true"
_FALSE = "false"
# What stands where an optional field has no value. A SELF-DESCRIBING word
# rather than an empty value, because a trailing separator reads as a field the
# writer forgot rather than as one the verdict genuinely had nothing for.
_ABSENT = "(none)"


@dataclass(frozen=True, kw_only=True)
class SpecChangeTierVerdict:
    """One classification of one item, and the tier it decides.

    `stated_kind` is optional because it is NOT TAKEN for a non-feature: the
    clause exempts `bug`, `chore` and `non_functional` outright, so spending the
    behaviour judgement on one would buy a field no decision reads. `None` is
    therefore "no stated kind was measured", never "the behaviour is unstated".
    """

    item_class: str
    stated_kind: str | None = None
    generalization_target: str | None = None
    linked_proposal_topic: str | None = None
    topic_ratified: bool = False

    @property
    def holds(self) -> bool:
        """Whether this verdict makes the item spec-change tier."""
        if self.item_class != CLASS_FEATURE:
            return False
        if self.stated_kind != KIND_STATED:
            return True
        return self.linked_proposal_topic is not None and not self.topic_ratified

    @property
    def tier(self) -> str:
        """The persisted tier word, as both orchestrators store it."""
        return TIER_SPEC_CHANGE if self.holds else TIER_NONE


def linked_proposal_topic(*, raw_labels: Sequence[str]) -> str | None:
    """The proposed-change topic one item's labels declare, or `None` for none.

    The LAST declaration wins, which is the direction a re-filed proposal needs:
    a label set carrying an older topic beside a newer one describes an item
    whose proposal was replaced, and the newer name is the one a refusal has to
    send an operator to.
    """
    found: str | None = None
    for label in raw_labels:
        if label.startswith(LINKED_TOPIC_LABEL_PREFIX):
            value = label[len(LINKED_TOPIC_LABEL_PREFIX) :].strip()
            if value:
                found = value
    return found


def spec_change_tier_comment(*, item_id: str, stage: str, verdict: SpecChangeTierVerdict) -> str:
    """The ledger comment recording one classification, tier and all."""
    return "\n".join(
        (
            SPEC_CHANGE_TIER_COMMENT_MARKER,
            "",
            f"{_WORK_ITEM_FIELD}{_FIELD_SEPARATOR}{item_id}",
            f"{_STAGE_FIELD}{_FIELD_SEPARATOR}{stage}",
            f"{_TIER_FIELD}{_FIELD_SEPARATOR}{verdict.tier}",
            f"{_CLASS_FIELD}{_FIELD_SEPARATOR}{verdict.item_class}",
            f"{_KIND_FIELD}{_FIELD_SEPARATOR}{verdict.stated_kind or _ABSENT}",
            f"{_GENERALIZATION_FIELD}{_FIELD_SEPARATOR}{verdict.generalization_target or _ABSENT}",
            f"{_TOPIC_FIELD}{_FIELD_SEPARATOR}{verdict.linked_proposal_topic or _ABSENT}",
            f"{_RATIFIED_FIELD}{_FIELD_SEPARATOR}{_TRUE if verdict.topic_ratified else _FALSE}",
        )
    )


def recorded_spec_change_tier(*, comments: Sequence[str]) -> SpecChangeTierVerdict | None:
    """The NEWEST recorded classification, or `None` when none is readable.

    The NEWEST rather than the earliest, which is the opposite of the
    Definition-of-Done record's reuse rule and deliberately so: that rule asks
    which verdict BINDS and must answer the same way however often it is asked,
    while this asks what the last classification SAW — and a classification is
    retired by any revision under `<spec-root>/history/`, so an older reading is
    evidence about a specification that no longer stands.

    A record naming no class is passed over rather than read as a verdict: it
    supports no decision, and reading it as one would decide `tier: none` for an
    item nobody classified.
    """
    for body in reversed(tuple(comments)):
        if _marker_of(body=body) != SPEC_CHANGE_TIER_COMMENT_MARKER:
            continue
        fields = _fields_of(body=body)
        item_class = fields.get(_CLASS_FIELD)
        if item_class is None:
            continue
        return SpecChangeTierVerdict(
            item_class=item_class,
            stated_kind=_optional(value=fields.get(_KIND_FIELD)),
            generalization_target=_optional(value=fields.get(_GENERALIZATION_FIELD)),
            linked_proposal_topic=_optional(value=fields.get(_TOPIC_FIELD)),
            topic_ratified=fields.get(_RATIFIED_FIELD) == _TRUE,
        )
    return None


def _marker_of(*, body: str) -> str:
    """One comment's leading line, which is where a marker sits.

    Written branchlessly over the STRIPPED body rather than as a walk to the
    first non-empty line, because the two readings differ on a body whose
    marker sits under a blank opening line and nothing downstream would
    announce the divergence. `"".partition` yields the empty string, so a
    comment with nothing in it names no marker and decides nothing.
    """
    return body.strip().partition("\n")[0].strip()


def _fields_of(*, body: str) -> dict[str, str]:
    """Every `key: value` line of one record, last occurrence winning."""
    fields: dict[str, str] = {}
    for raw in body.splitlines():
        key, separator, value = raw.strip().partition(_FIELD_SEPARATOR)
        if separator:
            fields[key] = value
    return fields


def _optional(*, value: str | None) -> str | None:
    """One recorded field, with the explicit absence read back as `None`."""
    return None if value is None or value == _ABSENT else value
