"""The tier is decided by the judgement, and the record names what a proposal needs.

Assertion 1 of `bd-ib-57ss2n`: "At filing, at groom and on each dispatch path,
every implement-kind item is classified by the spec-stated judgement, with the
stored type as evidence, and a `partial` or `unstated` verdict on a feature
records the verdict, the generalization target and the proposed-change topic the
item must link on the item."

The cases are each other's controls, because any one of them alone is satisfied
by a build that always answers the same way.

An item the classifier calls a FEATURE whose asked-for behaviour the judgement
reports `unstated` is spec-change tier, and the record it writes carries the
three things the clause names — the verdict, the generalization target and the
topic the item must link. The item under test is STORED as a `bug`, which is the
measured population this plan exists for: the audit behind it found 22 of 29
actionable ungoverned items typed `bug`, so a decision that read the stored type
would exempt exactly the items that need holding.

The same item with a `stated` verdict is NOT spec-change tier and its record
names no topic. A released item owes no proposal, and a topic recorded against
it would advertise a deposit nobody should make.

`partial` is asserted beside `unstated` because the independent review of this
plan's scoping required it (research note 005, finding 6): a behaviour the spec
states half of has a half no clause governs.

The last case is the RECORD's own fail-closed direction. A comment that is not a
record, and a record missing the fields a comparison needs, must both read as
"no classification is recorded" rather than as a classification saying the item
is free — the two are opposite answers to every consumer downstream.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._spec_change_tier import (
    NO_TIER,
    SPEC_CHANGE_TIER,
    asked_for_behaviour,
    decide_spec_change_tier,
    proposal_topic_for,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_record import (
    SPEC_CHANGE_TIER_MARKER,
    STAGE_FILING,
    recorded_spec_change_tier,
    spec_change_tier_comment,
)
from livespec_orchestrator_beads_fabro.types import WorkItem
from livespec_runtime.spec_stated import SpecStatedVerdict

_SPEC_VERSION = "170"
_DIGEST = "a-behaviour-digest"
_TARGET = "## A governing clause"


def _item(**overrides: object) -> WorkItem:
    base: dict[str, object] = {
        "id": "bd-ib-one",
        # STORED as a bug while the classifier calls it a feature: the stored
        # type is evidence the classifier weighs, never the tier's input.
        "type": "bug",
        "status": "backlog",
        "title": "Hold an unstated feature for its proposal",
        "description": "A description of new observable behaviour.",
        "origin": "freeform",
        "gap_id": None,
        "rank": "m",
        "assignee": None,
        "depends_on": (),
        "captured_at": "2026-01-01T00:00:00Z",
        "resolution": None,
        "reason": None,
        "audit": None,
        "superseded_by": None,
    }
    base.update(overrides)
    return WorkItem(**base)  # pyright: ignore[reportArgumentType]


def _verdict(*, kind: str, target: str | None) -> SpecStatedVerdict:
    return SpecStatedVerdict(
        kind=kind,  # pyright: ignore[reportArgumentType]
        stated_by=() if kind == "unstated" else (_TARGET,),
        generalization_target=target,
        rationale="the ratified text does not state the whole of it",
    )


def test_an_unstated_feature_is_spec_change_tier_and_records_the_three_fields() -> None:
    item = _item(acceptance_criteria="- It does the new thing.")
    decision = decide_spec_change_tier(
        item=item, classification="feature", verdict=_verdict(kind="unstated", target=_TARGET)
    )

    assert decision.tier == SPEC_CHANGE_TIER
    assert decision.is_spec_change is True
    assert decision.linked_proposal_topic == proposal_topic_for(item=item)

    recorded = recorded_spec_change_tier(
        comments=(
            spec_change_tier_comment(
                item_id=item.id,
                stage=STAGE_FILING,
                decision=decision,
                spec_version=_SPEC_VERSION,
                digest=_DIGEST,
            ),
        )
    )
    assert recorded is not None
    assert recorded.is_spec_change is True
    assert recorded.verdict_kind == "unstated"
    assert recorded.generalization_target == _TARGET
    assert recorded.linked_proposal_topic == proposal_topic_for(item=item)
    assert (recorded.spec_version, recorded.digest) == (_SPEC_VERSION, _DIGEST)
    assert recorded.classification == "feature"


def test_a_partial_feature_is_held_and_a_stated_one_is_not() -> None:
    item = _item()
    partial = decide_spec_change_tier(
        item=item, classification="feature", verdict=_verdict(kind="partial", target=_TARGET)
    )
    assert partial.tier == SPEC_CHANGE_TIER

    stated = decide_spec_change_tier(
        item=item, classification="feature", verdict=_verdict(kind="stated", target=None)
    )
    assert stated.tier == NO_TIER
    assert stated.is_spec_change is False
    assert stated.linked_proposal_topic is None

    recorded = recorded_spec_change_tier(
        comments=(
            spec_change_tier_comment(
                item_id=item.id,
                stage=STAGE_FILING,
                decision=stated,
                spec_version=_SPEC_VERSION,
                digest=_DIGEST,
            ),
        )
    )
    assert recorded is not None
    assert recorded.is_spec_change is False
    assert recorded.generalization_target is None
    assert recorded.linked_proposal_topic is None


def test_a_bug_is_never_spec_change_tier_whatever_the_verdict_says() -> None:
    item = _item()
    for classification in ("bug", "chore", "non_functional"):
        decision = decide_spec_change_tier(
            item=item,
            classification=classification,  # pyright: ignore[reportArgumentType]
            verdict=_verdict(kind="unstated", target=_TARGET),
        )
        assert decision.tier == NO_TIER
        assert decision.linked_proposal_topic is None


def test_an_already_linked_topic_wins_over_the_derivation() -> None:
    item = _item()
    decision = decide_spec_change_tier(
        item=item,
        classification="feature",
        verdict=_verdict(kind="unstated", target=_TARGET),
        linked_proposal_topic="a-deposited-topic",
    )
    assert decision.linked_proposal_topic == "a-deposited-topic"
    assert proposal_topic_for(item=item) == "hold-an-unstated-feature-for"
    assert proposal_topic_for(item=_item(title="!!!")) == "untitled"


def test_the_statement_names_an_absent_field_rather_than_dropping_it() -> None:
    stated = asked_for_behaviour(item=_item(acceptance_criteria="- It does the new thing."))
    assert "It does the new thing." in stated
    assert "Hold an unstated feature for its proposal" in stated

    absent = asked_for_behaviour(item=_item(acceptance_criteria="   "))
    assert "Acceptance criteria: (none recorded)" in absent
    # The closure reason is deliberately not part of the asked-for behaviour.
    assert "Closure reason" not in absent


def test_a_non_record_comment_and_an_incomplete_record_both_read_as_absence() -> None:
    assert recorded_spec_change_tier(comments=("", "an operator rider")) is None
    assert (
        recorded_spec_change_tier(
            comments=(f"{SPEC_CHANGE_TIER_MARKER}\n\nwork-item: bd-ib-one\nstage: filing",)
        )
        is None
    )
