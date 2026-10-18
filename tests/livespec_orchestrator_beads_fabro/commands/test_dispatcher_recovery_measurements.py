"""The four reads recovery routing takes, and which of them went unanswered.

`unobservable_measurements` is pure over one `ResumeObservation`, and each of its
four arms fires on a DIFFERENT shape of that value — so this is the tier where
all four, and the short-circuit between the two forge reads, can be stated at
once. The wave-level modules drive two of them end to end; neither can reach the
other two, because a gather that failed its first forge read never produces an
observation carrying the later ones.

WHY THE DETAIL IS ASSERTED AGAINST THE ARM'S OWN TEXT. The clause requires a held
item's record to carry the measurement's own account, and the whole point of
borrowing it is that there is ONE rendering. Asserting a substring of the arm's
prose is what would catch a classifier that had started writing its own.

WHY THE ALL-OBSERVED CASE IS FIRST. It is the control every other case rests on:
a classifier that reported a measurement for every observation would satisfy all
four positives and would hold every item in the fleet forever.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_measurements import (
    MEASUREMENT_FACTORY_RUN_LIVENESS,
    MEASUREMENT_FORGE_PULL_REQUEST,
    MEASUREMENT_FORGE_PULL_REQUEST_HEAD,
    MEASUREMENT_FORGE_PULL_REQUEST_RECORDS,
    unobservable_measurements,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_refusals import (
    ResumeObservation,
)

_ITEM_ID = "bd-ib-qgcpoc"
_HEAD = "db9feb3900000000000000000000000000000001"
_PR = 3001


def _observed(**overrides: object) -> ResumeObservation:
    """A `ready` observation whose every read ANSWERED, with named overrides.

    Built from the all-answered shape so each case states only the read it
    blinds: an observation assembled per case would differ in more than the one
    field under test, and the arm that fired would then be ambiguous.
    """
    fields: dict[str, object] = {
        "work_item_id": _ITEM_ID,
        "status": "ready",
        "anchor_head": _HEAD,
        "forge_observed": True,
        "pull_request": _PR,
        "pull_request_state": "OPEN",
        "pull_request_head": _HEAD,
        "records_observed": True,
        "liveness_observed": True,
    }
    fields.update(overrides)
    return ResumeObservation(**fields)  # pyright: ignore[reportArgumentType]


def test_an_observation_whose_every_read_answered_names_no_measurement() -> None:
    """The control: every other case here is a departure from this one shape."""
    assert unobservable_measurements(observation=_observed()) == ()


def test_an_unobservable_forge_listing_names_the_pull_request_read_alone() -> None:
    """And it SHORT-CIRCUITS the record read, which was never attempted.

    `anchor_refusals` returns on the unobservable listing before it looks at the
    record list, so reporting the records read too would name a read nobody took —
    and would send an operator to check the pull request's comments when the
    listing that would have identified the pull request is what failed.
    """
    found = unobservable_measurements(
        observation=_observed(forge_observed=False, records_observed=False)
    )

    assert [one.name for one in found] == [MEASUREMENT_FORGE_PULL_REQUEST]
    assert "whether this item's publish branch carries" in found[0].detail


def test_an_unreadable_record_list_names_the_records_read() -> None:
    """The narrower forge outage: the listing answered, only the records did not."""
    found = unobservable_measurements(observation=_observed(records_observed=False))

    assert [one.name for one in found] == [MEASUREMENT_FORGE_PULL_REQUEST_RECORDS]
    assert "Proof of Done records on pull request" in found[0].detail


def test_an_unreported_pull_request_head_names_the_head_read() -> None:
    """A degraded read of ONE field rather than a different kind of pull request."""
    found = unobservable_measurements(observation=_observed(pull_request_head=None))

    assert [one.name for one in found] == [MEASUREMENT_FORGE_PULL_REQUEST_HEAD]
    assert "could not report the head of pull request" in found[0].detail


def test_an_absent_head_with_no_anchor_is_not_a_failed_head_read() -> None:
    """With no anchor there is no head to compare, so no read was owed.

    This is the arm that distinguishes "the forge did not answer" from "there was
    nothing to ask": an item whose publish branch carries no pull request reaches
    the ladder with both fields absent, and reporting a failed head read there
    would hold every unpublished item in the fleet.
    """
    assert (
        unobservable_measurements(
            observation=_observed(anchor_head=None, pull_request=None, pull_request_head=None)
        )
        == ()
    )


def test_an_unobservable_factory_names_the_liveness_read() -> None:
    """The read whose failure is most easily mistaken for an answer.

    A factory that cannot be asked and a factory holding nothing alive carry the
    same empty live-run set, and one authorizes a recovery while the other forbids
    it.
    """
    found = unobservable_measurements(observation=_observed(liveness_observed=False))

    assert [one.name for one in found] == [MEASUREMENT_FACTORY_RUN_LIVENESS]
    assert "could not report the earlier run's liveness" in found[0].detail


def test_two_failed_reads_are_both_named_in_the_ladders_own_order() -> None:
    """A hold names every measurement it could not take, not the first.

    The resume's own conjunction rule, carried through: an operator told only
    about the forge retries the forge and meets the factory they were never told
    about.
    """
    found = unobservable_measurements(
        observation=_observed(pull_request_head=None, liveness_observed=False)
    )

    assert [one.name for one in found] == [
        MEASUREMENT_FORGE_PULL_REQUEST_HEAD,
        MEASUREMENT_FACTORY_RUN_LIVENESS,
    ]
