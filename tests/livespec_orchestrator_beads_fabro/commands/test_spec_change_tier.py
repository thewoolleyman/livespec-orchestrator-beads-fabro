"""Tests for the spec-change-tier DECISION and the ledger record that carries it.

The autonomy-tier bullet of `SPECIFICATION/contracts.md` section "Grooming and
slice-size calibration" and Scenario 206 are the subject. Three claims are
graded here, each one an arm an implementation falls out of:

THE TIER IS THE JUDGEMENT'S, NOT THE FILER'S AND NOT THE HINT'S. A feature the
judgement reports `partial` or `unstated` is spec-change tier whatever
`spec_commitment_hint` says, and a feature it reports `stated` is not — which is
the hint-carrying pair of Scenario 206. The field is deliberately absent from
the decision's inputs, so the case is stated by passing the same verdict with
and without a linked topic rather than by threading a hint nothing reads.

A `stated` VERDICT IS NOT ON ITS OWN A RELEASE. An item whose own proposal was
rejected stays held, which is Scenario 206's "A rejected or narrowed proposal
does not release the hold". That arm is reachable only through the linked
topic, so the two topic cases are graded separately.

THE RECORD ROUND-TRIPS. The clause requires the verdict, the generalization
target and the topic the item must link to be recorded ON THE ITEM, and the
mechanical hold reads them back, so a render whose parse loses a field is a
hold that cannot name what it is holding for.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._spec_change_tier import (
    TIER_NONE,
    TIER_SPEC_CHANGE,
    SpecChangeTierVerdict,
    linked_proposal_topic,
    recorded_spec_change_tier,
    spec_change_tier_comment,
)

_TARGET = "## Dispatcher admission, WIP cap, and post-merge acceptance"
_TOPIC = "spec-stated-judgement-and-spec-change-tier"


def test_a_feature_whose_behaviour_is_unstated_is_spec_change_tier() -> None:
    """The decision the whole clause rests on, and the one a stub cannot fake."""
    verdict = SpecChangeTierVerdict(item_class="feature", stated_kind="unstated")

    assert verdict.holds is True
    assert verdict.tier == TIER_SPEC_CHANGE


def test_a_feature_whose_behaviour_is_partially_stated_is_spec_change_tier() -> None:
    """`partial` is named beside `unstated` by the clause and is graded beside it."""
    assert SpecChangeTierVerdict(item_class="feature", stated_kind="partial").holds is True


def test_a_bug_a_chore_and_a_non_functional_item_are_never_spec_change_tier() -> None:
    """The exemption, over every class the shared judgement can return.

    Each is asserted with NO stated kind at all, because none is taken for a
    non-feature: a decision that consulted one would be reading a field nobody
    measured, and the absence is what proves it does not.
    """
    for item_class in ("bug", "chore", "non_functional"):
        verdict = SpecChangeTierVerdict(item_class=item_class)

        assert verdict.holds is False
        assert verdict.tier == TIER_NONE


def test_a_feature_the_judgement_states_and_that_links_no_topic_is_not_held() -> None:
    """Scenario 206's "A follow-up to a ratified change is not held"."""
    assert SpecChangeTierVerdict(item_class="feature", stated_kind="stated").holds is False


def test_a_stated_feature_whose_linked_topic_is_unratified_stays_held() -> None:
    """Scenario 206's rejected-or-narrowed proposal: `stated` alone is no release."""
    verdict = SpecChangeTierVerdict(
        item_class="feature",
        stated_kind="stated",
        linked_proposal_topic=_TOPIC,
        topic_ratified=False,
    )

    assert verdict.holds is True


def test_a_stated_feature_whose_linked_topic_is_ratified_is_released() -> None:
    """Both conditions met is the ONLY release the clause admits."""
    verdict = SpecChangeTierVerdict(
        item_class="feature",
        stated_kind="stated",
        linked_proposal_topic=_TOPIC,
        topic_ratified=True,
    )

    assert verdict.holds is False
    assert verdict.tier == TIER_NONE


def test_the_linked_topic_is_read_off_the_items_own_labels() -> None:
    """How an item CARRIES the topic the clause requires it to link."""
    assert (
        linked_proposal_topic(raw_labels=("intake:triaged", f"proposal-topic:{_TOPIC}")) == _TOPIC
    )


def test_an_item_declaring_no_topic_label_links_none() -> None:
    """An empty declaration is no declaration, which the hold must read as absent."""
    assert linked_proposal_topic(raw_labels=("intake:triaged", "proposal-topic:   ")) is None


def test_the_newest_topic_declaration_wins_over_an_older_one() -> None:
    """A replaced proposal is the name a refusal must send an operator to."""
    labels = ("proposal-topic:retired-topic", f"proposal-topic:{_TOPIC}")

    assert linked_proposal_topic(raw_labels=labels) == _TOPIC


def test_a_recorded_verdict_round_trips_every_field_the_hold_reads_back() -> None:
    """The verdict, the generalization target and the topic, as the clause requires."""
    verdict = SpecChangeTierVerdict(
        item_class="feature",
        stated_kind="unstated",
        generalization_target=_TARGET,
        linked_proposal_topic=_TOPIC,
    )
    body = spec_change_tier_comment(item_id="bd-ib-57ss2n", stage="pre-admission", verdict=verdict)

    assert recorded_spec_change_tier(comments=(body,)) == verdict


def test_a_recorded_verdict_naming_no_optional_field_round_trips_as_absent() -> None:
    """The explicit absence is read back as `None`, never as the literal word."""
    verdict = SpecChangeTierVerdict(item_class="chore")
    body = spec_change_tier_comment(item_id="bd-ib-57ss2n", stage="pre-dispatch", verdict=verdict)

    assert recorded_spec_change_tier(comments=(body,)) == verdict


def test_the_newest_recorded_classification_governs() -> None:
    """A classification is retired by any later one, so the last reading wins."""
    held = spec_change_tier_comment(
        item_id="bd-ib-57ss2n",
        stage="pre-admission",
        verdict=SpecChangeTierVerdict(item_class="feature", stated_kind="unstated"),
    )
    released = spec_change_tier_comment(
        item_id="bd-ib-57ss2n",
        stage="pre-dispatch",
        verdict=SpecChangeTierVerdict(item_class="feature", stated_kind="stated"),
    )

    recorded = recorded_spec_change_tier(comments=(held, released))

    assert recorded is not None
    assert recorded.holds is False


def test_a_comment_that_is_not_a_classification_record_is_not_read_as_one() -> None:
    """An operator rider must not be able to decide an item's tier."""
    assert recorded_spec_change_tier(comments=("A rider.\n\nitem-class: feature\n",)) is None


def test_a_classification_record_naming_no_class_supports_no_decision() -> None:
    """A record that cannot name the class is passed over, never read as one."""
    body = "livespec-spec-change-tier\n\nwork-item: bd-ib-57ss2n\nstage: pre-admission\n"

    assert recorded_spec_change_tier(comments=(body,)) is None


def test_an_item_with_no_comments_at_all_carries_no_recorded_classification() -> None:
    """The absence a first filing presents, which is not a `tier: none` verdict."""
    assert recorded_spec_change_tier(comments=()) is None
