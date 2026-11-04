"""Whether a recorded spec-change tier still HOLDS the item out of `ready`.

PURE, and that purity is a requirement rather than a tidiness: the autonomy-tier
bullet of `SPECIFICATION/contracts.md` says of this hold that it "is a read of
the spec history and needs no model, so it MUST fail closed". A hold that
reached a provider would have an unavailable-model arm, and every such arm in
this package fails toward the behaviour it had without the judgement — which
here is the item dispatching.

THE HOLD IS DECIDED FROM THE RECORDED CLASSIFICATION AND THE SPEC HISTORY, and
from nothing else. The plan-child-disposition clause of
`SPECIFICATION/constraints.md` requires exactly that ("The autonomy tier is
DECIDED by the spec-stated judgement and recorded on the item at
classification") and forbids the obvious substitute in as many words: an
implementation "MUST NOT substitute `spec_commitment_hint` for the missing
datum", because "those two are near-opposites" — a hint marks an implementation
follow-up to an ALREADY-RATIFIED change, which is ordinary dispatchable work.

THREE REASONS A HELD ITEM IS HELD, AND THEY ARE NOT INTERCHANGEABLE, because
each sends the operator somewhere different:

- `no-linked-topic` — the classification holds the item and names no topic, so
  there is no proposal for a ratification read to look for. The operator files
  one.
- `unratified-topic` — the topic is named and the spec history carries no
  revision record for it with decision `accept` or `modify`. The operator takes
  it through `/livespec:revise`, or it is already there.
- `awaiting-rejudgement` — the topic IS ratified and the newest recorded
  classification still says spec-change, so the judgement has not yet been
  re-run against the ratified specification. Nobody needs to do anything: the
  next intake or drain pass re-judges and releases the hold.

Collapsing the third into the second is the mistake worth naming, because it
reads as the conservative choice and is the expensive one: it tells an operator
their ratified proposal was not ratified, and the remedy it implies — ratify it
again — cannot exist.

A `none` RECORD ADMITS THE ITEM, which is how a release is expressed: the pass
that re-judges writes a fresh record, and this read simply stops holding. There
is no separate "released" state to keep in step with the tier, and so no way for
the two to disagree.

NO RECORD AT ALL ADMITS THE ITEM TOO, and that is the one arm where this read
fails OPEN. The clause ratifies it: "When the classification cannot run ...
intake MUST record that on the item and route it as it would without the
classification; the `dod_gate` node, which runs the same judgement in-run,
remains the backstop that refuses an unstated feature before any implementation
spend." Holding instead would refuse every item filed before this build existed
— the whole tenant — and the refusal would read exactly like a factory with no
work. The plan-child disposition takes the OPPOSITE direction on the same
absence, because its own clause says so; that asymmetry is deliberate and each
half is stated where it is required.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Collection

    from livespec_orchestrator_beads_fabro.commands._spec_change_tier_record import (
        RecordedSpecChangeTier,
    )

__all__: list[str] = [
    "REASON_AWAITING_REJUDGEMENT",
    "REASON_NO_LINKED_TOPIC",
    "REASON_UNRATIFIED_TOPIC",
    "SpecChangeHold",
    "spec_change_hold",
]

REASON_NO_LINKED_TOPIC = "no-linked-topic"
REASON_UNRATIFIED_TOPIC = "unratified-topic"
REASON_AWAITING_REJUDGEMENT = "awaiting-rejudgement"

_UNNAMED_TOPIC = "(none linked)"


@dataclass(frozen=True, kw_only=True)
class SpecChangeHold:
    """One item held out of `ready` for its linked proposal's ratification."""

    work_item_id: str
    reason: str
    linked_proposal_topic: str | None
    verdict_kind: str
    generalization_target: str | None

    @property
    def refusal(self) -> str:
        """The refusal a dispatch of this item renders, NAMING the topic.

        The topic is in every one of the three messages, including the arm where
        there is none to name, because the operator's next act is about that
        topic in all three cases — filing it, ratifying it, or waiting for the
        pass that re-judges against it.
        """
        topic = self.linked_proposal_topic or _UNNAMED_TOPIC
        return (
            f"REFUSED: work-item {self.work_item_id} is spec-change tier and is held"
            f" for its linked proposed-change topic {topic}; no claim was taken and"
            " no factory run was created. The spec-stated judgement reported its"
            f" asked-for behaviour {self.verdict_kind}"
            f"{self._target_clause()}. Hold reason: {self.reason}.\n"
        )

    def _target_clause(self) -> str:
        if self.generalization_target is None:
            return " and named no existing heading to generalize"
        return f" and named {self.generalization_target} as the heading to generalize"


def spec_change_hold(
    *,
    work_item_id: str,
    recorded: RecordedSpecChangeTier | None,
    ratified_topics: Collection[str],
) -> SpecChangeHold | None:
    """This item's standing hold, or `None` when nothing holds it back.

    `recorded` is the NEWEST recorded classification — see
    `_spec_change_tier_record.recorded_spec_change_tier` — and `ratified_topics`
    is the set of proposed-change topics the governed spec history carries an
    `accept` or `modify` revision record for.

    `None` is returned for an item with no record, for one whose record says the
    tier does not hold, and for one whose hold has been released. Those are one
    fact to every caller: nothing is holding this item back.
    """
    if recorded is None or not recorded.is_spec_change:
        return None
    return SpecChangeHold(
        work_item_id=work_item_id,
        reason=_reason(recorded=recorded, ratified_topics=ratified_topics),
        linked_proposal_topic=recorded.linked_proposal_topic,
        verdict_kind=recorded.verdict_kind,
        generalization_target=recorded.generalization_target,
    )


def _reason(*, recorded: RecordedSpecChangeTier, ratified_topics: Collection[str]) -> str:
    """Which of the three conditions holds this item, in the order they decide."""
    topic = recorded.linked_proposal_topic
    if topic is None:
        return REASON_NO_LINKED_TOPIC
    if topic not in ratified_topics:
        return REASON_UNRATIFIED_TOPIC
    return REASON_AWAITING_REJUDGEMENT
