"""The LEDGER RECORD of one spec-change-tier classification, written and read back.

The autonomy-tier bullet of `SPECIFICATION/contracts.md` requires the tier to be
"recorded on the item at classification", and the plan-child-disposition clause
of `SPECIFICATION/constraints.md` then makes that record the ONLY admissible
source of the tier: an implementation "MUST fail CLOSED: where it cannot
determine a child's autonomy tier from that recorded classification, it MUST
refuse the disposition". A record that cannot be read back is therefore not a
record at all, so the render and the parse live together here.

WHY THE LEDGER COMMENT IS THE STORE. Ledger writers here may share nothing but
the Beads server (`.ai/ledger-writers-are-multi-host.md`), so a tier cached
under a host state root would be invisible to the next writer — and the next
writer is routinely a different host from the one that filed the item. The
comment is the only durable, append-only record every writer can see. It is the
same choice `_dispatcher_dod_judgement_record` made, for the same reason.

WHY THE RECORD NAMES A SPEC VERSION. "A new revision under `<spec-root>/history/`
invalidates every earlier verdict, so the judgement that releases a held
spec-change-tier item always runs against the ratified specification". A record
naming the version it was taken against retires itself the moment a revision
lands, which is exactly the reuse rule that clause states — and it is what makes
a release a re-judgement rather than a re-read of the verdict that held the item
in the first place.

WHY IT NAMES A BEHAVIOUR DIGEST TOO. The other half of the same reuse rule: a
verdict is reusable "only while its input ... [is] unchanged since it was
taken". An item whose title or criteria were edited after a held verdict is an
item whose asked-for behaviour nobody has judged, and reusing the old verdict
would hold it on a reading of text it no longer carries.

WHY A RECORD MISSING EITHER FIELD IS NOT A RECORD. It cannot name the subject or
the specification it was taken against, so it supports no comparison; treating
it as current would reuse a verdict for text and a spec it may never have read.
That is the fail-closed reading, and it retires every record an earlier build
wrote in a shape this one cannot compare, once rather than forever.

WHY AN ABSENT OPTIONAL FIELD IS NAMED RATHER THAN LEFT EMPTY. The parse has to
tell "this classification named no generalization target" from "the target line
is missing", because the second is an unreadable record and the first is a sound
one. An empty value reads as a field the writer forgot, which collapses the two.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._spec_change_tier import SPEC_CHANGE_TIER

if TYPE_CHECKING:
    from collections.abc import Sequence

    from livespec_orchestrator_beads_fabro.commands._spec_change_tier import (
        SpecChangeTierDecision,
    )

__all__: list[str] = [
    "SPEC_CHANGE_TIER_MARKER",
    "STAGE_DISPATCH",
    "STAGE_FILING",
    "STAGE_GROOM",
    "RecordedSpecChangeTier",
    "recorded_spec_change_tier",
    "spec_change_tier_comment",
]

SPEC_CHANGE_TIER_MARKER = "livespec-spec-change-tier"

# The three cadence points the clause names, as self-describing values rather
# than numbered positions: the record says WHERE the classification happened,
# which is what tells an operator reading the item whether a filing, a groom
# draft or a dispatch produced the tier it carries.
STAGE_FILING = "filing"
STAGE_GROOM = "groom"
STAGE_DISPATCH = "dispatch"

_WORK_ITEM_FIELD = "work-item"
_STAGE_FIELD = "stage"
_TIER_FIELD = "tier"
_CLASSIFICATION_FIELD = "classification"
_VERDICT_KIND_FIELD = "verdict-kind"
_GENERALIZATION_TARGET_FIELD = "generalization-target"
_LINKED_TOPIC_FIELD = "linked-proposal-topic"
_SPEC_VERSION_FIELD = "spec-version"
_DIGEST_FIELD = "behaviour-digest"
_RATIONALE_FIELD = "rationale"
_FIELD_SEPARATOR = ": "
_ABSENT_VALUE = "(none)"


@dataclass(frozen=True, kw_only=True)
class RecordedSpecChangeTier:
    """One classification read back off the item, as every consumer compares it.

    `spec_version` and `digest` are carried as the strings the record holds
    rather than parsed into an integer and a hash, because the only question
    asked of them is equality with the current pair — and a parse that could
    fail would need a third answer for "the record names a version I cannot
    read", which is the same fact as "it names a different one".
    """

    tier: str
    classification: str
    verdict_kind: str
    generalization_target: str | None
    linked_proposal_topic: str | None
    spec_version: str
    digest: str

    @property
    def is_spec_change(self) -> bool:
        """Whether the recorded tier puts the item in the spec-change tier."""
        return self.tier == SPEC_CHANGE_TIER


def spec_change_tier_comment(
    *,
    item_id: str,
    stage: str,
    decision: SpecChangeTierDecision,
    spec_version: str,
    digest: str,
) -> str:
    """The ledger comment recording one tier decision, verdict and all.

    The GENERALIZATION TARGET and the RATIONALE are recorded for every decision
    rather than only for a held one, which looks like waste and is not: a
    `partial` verdict that released on its second judgement leaves a reader
    asking which clause the first one named, and the record is the only place
    that answer survives.
    """
    verdict = decision.verdict
    target = _rendered(value=verdict.generalization_target)
    topic = _rendered(value=decision.linked_proposal_topic)
    return "\n".join(
        (
            SPEC_CHANGE_TIER_MARKER,
            "",
            f"{_WORK_ITEM_FIELD}{_FIELD_SEPARATOR}{item_id}",
            f"{_STAGE_FIELD}{_FIELD_SEPARATOR}{stage}",
            f"{_TIER_FIELD}{_FIELD_SEPARATOR}{decision.tier}",
            f"{_CLASSIFICATION_FIELD}{_FIELD_SEPARATOR}{decision.classification}",
            f"{_VERDICT_KIND_FIELD}{_FIELD_SEPARATOR}{verdict.kind}",
            f"{_GENERALIZATION_TARGET_FIELD}{_FIELD_SEPARATOR}{target}",
            f"{_LINKED_TOPIC_FIELD}{_FIELD_SEPARATOR}{topic}",
            f"{_SPEC_VERSION_FIELD}{_FIELD_SEPARATOR}{spec_version}",
            f"{_DIGEST_FIELD}{_FIELD_SEPARATOR}{digest}",
            f"{_RATIONALE_FIELD}{_FIELD_SEPARATOR}{verdict.rationale}",
        )
    )


def recorded_spec_change_tier(*, comments: Sequence[str]) -> RecordedSpecChangeTier | None:
    """The NEWEST recorded classification, whatever it was taken against.

    The record every fail-closed consumer reads: the plan-child-disposition
    clause asks for "that recorded classification" and not for a current one,
    because a tier that was spec-change against an older specification is still
    the last thing anybody decided about the item.

    `None` means no classification is recorded at all — NOT that one says the
    item is free. The two are different answers and the consumers take them in
    opposite directions: the plan-child disposition refuses on `None` while the
    pre-dispatch wall proceeds on it, each as its own clause requires.
    """
    for body in reversed(tuple(comments)):
        if _marker_of(body=body) != SPEC_CHANGE_TIER_MARKER:
            continue
        return _recorded_from(body=body)
    return None


def _recorded_from(*, body: str) -> RecordedSpecChangeTier | None:
    """One record parsed, or `None` when it omits a field a comparison needs."""
    fields = _fields_of(body=body)
    tier = fields.get(_TIER_FIELD)
    spec_version = fields.get(_SPEC_VERSION_FIELD)
    digest = fields.get(_DIGEST_FIELD)
    if tier is None or spec_version is None or digest is None:
        return None
    return RecordedSpecChangeTier(
        tier=tier,
        classification=fields.get(_CLASSIFICATION_FIELD, ""),
        verdict_kind=fields.get(_VERDICT_KIND_FIELD, ""),
        generalization_target=_parsed(value=fields.get(_GENERALIZATION_TARGET_FIELD)),
        linked_proposal_topic=_parsed(value=fields.get(_LINKED_TOPIC_FIELD)),
        spec_version=spec_version,
        digest=digest,
    )


def _marker_of(*, body: str) -> str:
    """The marker line one comment opens with, or the empty string for none."""
    first = body.strip().splitlines()[:1]
    return first[0].strip() if first else ""


def _fields_of(*, body: str) -> dict[str, str]:
    """Every `key: value` line of one record, LAST occurrence winning."""
    fields: dict[str, str] = {}
    for raw in body.splitlines():
        key, separator, value = raw.strip().partition(_FIELD_SEPARATOR)
        if separator:
            fields[key] = value
    return fields


def _rendered(*, value: str | None) -> str:
    """One optional field as the record carries it, absence named not empty."""
    return _ABSENT_VALUE if value is None or value.strip() == "" else value.strip()


def _parsed(*, value: str | None) -> str | None:
    """One optional field read back, with the absent mark read as absence."""
    if value is None or value.strip() in ("", _ABSENT_VALUE):
        return None
    return value.strip()
