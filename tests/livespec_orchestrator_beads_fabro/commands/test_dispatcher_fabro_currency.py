"""Tests for the PURE Fabro currency predicate: the ladder and its evidence.

`tests/integration/test_fabro_currency_admission_scenario130.py` binds the
behaviour through the real pre-dispatch wall. This module covers the rule itself
across the states that wall cannot reach cheaply — an observation holding no
releases at all, a subject whose every measurement failed — and the evidence
block's own unknown-field rendering.

THE EVIDENCE BLOCK IS ASSERTED LINE BY LINE rather than by containment. A block
that merely MENTIONED the target would satisfy an `in` check while naming neither
the base it rejected nor the remedy, and those are what an operator acts on.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_currency import (
    CONDITION_CURRENT,
    CONDITION_NO_ANCESTOR,
    CONDITION_OBSERVATION_UNOBSERVABLE,
    CONDITION_OUT_OF_WINDOW,
    CONDITION_STALE_OBSERVATION,
    CONDITION_TRANSITION_ADMITTED,
    CONDITION_UNIDENTIFIED_BUILD,
    CURRENCY_WINDOW_DAYS,
    TRANSITION_DEADLINE,
    TRANSITION_WORK_ITEM,
    FabroCurrencySubject,
    FabroRelease,
    FabroReleaseObservation,
    calendar_days_between,
    fabro_currency_verdict,
    newest_observed_release,
)

_NOW = datetime(2026, 10, 11, 9, 0, tzinfo=timezone.utc)
_NEWEST = FabroRelease(tag="v0.378.0-nightly.0", published_at=_NOW - timedelta(days=1))
_IN_WINDOW = FabroRelease(tag="v0.370.0", published_at=_NOW - timedelta(days=20))
_OUT_OF_WINDOW = FabroRelease(tag="v0.300.0", published_at=_NOW - timedelta(days=90))
# The 0.254 carrier the one non-renewable transition covers, out of window by the
# same margin as `_OUT_OF_WINDOW` — so the two differ in NOTHING but the tag, and
# any difference in verdict is the exception rather than the arithmetic.
_CARRIER = FabroRelease(tag="v0.254.0", published_at=_NOW - timedelta(days=90))


def _observation(*, releases: tuple[FabroRelease, ...]) -> FabroReleaseObservation:
    return FabroReleaseObservation(releases=releases, observed_at=_NOW)


def _subject(
    *,
    serving_commit: str | None = "8869e88",
    base: FabroRelease | None = _IN_WINDOW,
    observation: FabroReleaseObservation | None = None,
    unobservable_detail: str | None = None,
    observation_failure: str | None = None,
) -> FabroCurrencySubject:
    return FabroCurrencySubject(
        target="hp",
        serving_commit=serving_commit,
        base=base,
        observation=(
            observation
            if observation is not None
            else _observation(releases=(_NEWEST, _IN_WINDOW, _OUT_OF_WINDOW))
        ),
        unobservable_detail=unobservable_detail,
        observation_failure=observation_failure,
    )


def test_calendar_days_are_counted_across_date_boundaries_not_in_whole_days() -> None:
    """Two instants nineteen hours apart that straddle midnight are ONE day apart.

    The clause is written in CALENDAR days, and a seconds-based reading would call
    this pair zero — which widens every bound here by up to a day.
    """
    earlier = datetime(2026, 10, 10, 23, 0, tzinfo=timezone.utc)
    later = datetime(2026, 10, 11, 18, 0, tzinfo=timezone.utc)

    assert calendar_days_between(earlier=earlier, later=later) == 1


def test_calendar_days_are_read_in_utc_whatever_offset_either_instant_carries() -> None:
    """A non-UTC offset is normalized, not counted from its own local date."""
    earlier = datetime(2026, 10, 10, 23, 0, tzinfo=timezone(timedelta(hours=-5)))

    assert calendar_days_between(earlier=earlier, later=_NOW) == 0


def test_an_observation_holding_no_releases_reports_no_newest_release() -> None:
    """`None` rather than a raise: an empty surface is an answer the ladder grades."""
    assert newest_observed_release(observation=_observation(releases=())) is None


def test_the_newest_release_is_the_head_of_the_observation() -> None:
    assert (
        newest_observed_release(observation=_observation(releases=(_NEWEST, _IN_WINDOW))) == _NEWEST
    )


def test_a_base_inside_the_window_is_admitted_and_reports_its_gap() -> None:
    verdict = fabro_currency_verdict(subject=_subject(), now=_NOW)

    assert verdict.admitted is True
    assert verdict.condition == CONDITION_CURRENT
    assert "v0.370.0" in verdict.detail
    assert "19 calendar days behind" in verdict.detail


def test_a_base_exactly_at_the_window_edge_is_admitted() -> None:
    """The bound is "more than" 30 calendar days, so 30 itself is inside it.

    Asserted because an off-by-one here refuses a build the clause admits, and the
    refusal would be indistinguishable from a genuinely stale one.
    """
    edge = FabroRelease(
        tag="v0.300.0",
        published_at=_NEWEST.published_at - timedelta(days=CURRENCY_WINDOW_DAYS),
    )

    verdict = fabro_currency_verdict(
        subject=_subject(base=edge, observation=_observation(releases=(_NEWEST, edge))),
        now=_NOW,
    )

    assert verdict.admitted is True
    assert verdict.condition == CONDITION_CURRENT


def test_an_out_of_window_base_refuses_and_its_evidence_block_names_every_field() -> None:
    verdict = fabro_currency_verdict(subject=_subject(base=_OUT_OF_WINDOW), now=_NOW)

    assert verdict.admitted is False
    assert verdict.condition == CONDITION_OUT_OF_WINDOW
    lines = verdict.detail.splitlines()
    assert lines[0].startswith("ERROR: Fabro currency admission refused for factory target 'hp'")
    assert lines[1] == "  factory target: hp"
    assert lines[2] == "  serving integration commit: 8869e88"
    assert lines[3] == "  upstream base: v0.300.0 published 2026-07-13T09:00:00+00:00"
    assert lines[4] == (
        "  newest observed upstream release: v0.378.0-nightly.0"
        " published 2026-10-10T09:00:00+00:00"
    )
    assert lines[5] == "  release observation taken at: 2026-10-11T09:00:00+00:00"
    assert lines[6] == "  currency evaluated at: 2026-10-11T09:00:00+00:00"
    assert lines[7] == f"  failed currency condition: {CONDITION_OUT_OF_WINDOW}"
    assert lines[8].startswith("  corrective route: re-pin")
    assert "fabro-sh/fabro" in lines[8]


def test_an_unmeasured_subject_refuses_and_renders_every_absent_field_as_unknown() -> None:
    """The fully-blinded subject: no commit, no observation, no base.

    Fail-closed is the whole claim — a gauge that admitted here would turn the
    refusal into a pass and leave a journal record that reads exactly like a
    healthy one. The condition it reports is the OBSERVATION one, which is the
    ladder's first arm: an absent observation makes the base question
    unanswerable for every target, so naming the per-target fault while the
    shared one stands would send the operator to the wrong place.
    """
    verdict = fabro_currency_verdict(
        subject=FabroCurrencySubject(
            target="hp",
            serving_commit=None,
            base=None,
            observation=None,
            unobservable_detail=None,
            observation_failure=None,
        ),
        now=_NOW,
    )

    assert verdict.admitted is False
    assert verdict.condition == CONDITION_OBSERVATION_UNOBSERVABLE
    lines = verdict.detail.splitlines()
    assert lines[0].endswith("the currency reading could not be taken")
    assert lines[2] == "  serving integration commit: unknown"
    assert lines[3] == "  upstream base: unknown"
    assert lines[4] == "  newest observed upstream release: unknown"
    assert lines[5] == "  release observation taken at: unknown"


def test_an_unidentified_serving_build_reports_its_own_condition() -> None:
    """The observation IS readable, so the serving build is the finding.

    Distinct from the no-ancestor condition below because the remedies differ: a
    host whose engine cannot be asked its version is repaired, while a build with
    no release-tag ancestor is re-pinned.
    """
    verdict = fabro_currency_verdict(subject=_subject(serving_commit=None, base=None), now=_NOW)

    assert verdict.condition == CONDITION_UNIDENTIFIED_BUILD
    assert verdict.detail.splitlines()[2] == "  serving integration commit: unknown"
    # The newest release is still reported, which is what says the shared
    # observation was fine and the per-target reading was not.
    assert "v0.378.0-nightly.0" in verdict.detail.splitlines()[4]


def test_a_measured_build_with_no_resolvable_base_reports_the_no_ancestor_condition() -> None:
    verdict = fabro_currency_verdict(subject=_subject(base=None), now=_NOW)

    assert verdict.condition == CONDITION_NO_ANCESTOR
    assert verdict.detail.splitlines()[2] == "  serving integration commit: 8869e88"
    assert verdict.detail.splitlines()[3] == "  upstream base: unknown"


def test_a_supplied_unobservable_detail_is_the_clause_the_refusal_leads_with() -> None:
    """The gathering layer's own account of what failed is carried through verbatim.

    It has to be: the ladder cannot tell an unreachable forge from an
    unidentifiable engine, and the generic fallback above would send an operator
    to look at both.
    """
    verdict = fabro_currency_verdict(
        subject=_subject(base=None, unobservable_detail="the forge read failed"),
        now=_NOW,
    )

    assert verdict.condition == CONDITION_NO_ANCESTOR
    assert verdict.detail.splitlines()[0].endswith("the forge read failed")


def test_an_observation_with_no_releases_refuses_even_with_a_commit_and_a_base() -> None:
    """Nothing to compare the base AGAINST is as unobservable as having no base.

    The arm matters because an empty releases list is a well-formed, exit-0 forge
    answer: a reading that treated it as "nothing newer exists" would admit every
    base in the world.
    """
    verdict = fabro_currency_verdict(
        subject=_subject(observation=_observation(releases=())), now=_NOW
    )

    assert verdict.admitted is False
    assert verdict.condition == CONDITION_OBSERVATION_UNOBSERVABLE
    assert verdict.detail.splitlines()[4] == "  newest observed upstream release: unknown"


def test_a_populated_but_unusable_reading_refuses_as_stale_rather_than_as_current() -> None:
    """The fail-open this arm closed, asserted on the shape that produced it.

    The observation carries a newest release and an in-window base, so EVERY
    later arm succeeds on it and the verdict was `current` — an admitted dispatch
    on expired evidence. The failure field is therefore graded BEFORE the
    arithmetic, not alongside it.
    """
    verdict = fabro_currency_verdict(
        subject=_subject(observation_failure="the cached observation is 9 calendar days old"),
        now=_NOW,
    )

    assert verdict.admitted is False
    assert verdict.condition == CONDITION_STALE_OBSERVATION
    assert verdict.detail.splitlines()[0].endswith("the cached observation is 9 calendar days old")
    # The record is NAMED, which is what the clause asks of this refusal.
    assert (
        verdict.detail.splitlines()[5]
        == "  release observation taken at: 2026-10-11T09:00:00+00:00"
    )


def test_a_failed_reading_with_no_record_at_all_refuses_as_unobservable() -> None:
    """Told apart from the stale arm by whether a record EXISTS to be named.

    Same refusal, different remedy: this one says no reading has ever been taken
    on this host, where the stale one says the refresh path is broken while
    evidence exists.
    """
    verdict = fabro_currency_verdict(
        subject=FabroCurrencySubject(
            target="hp",
            serving_commit="8869e88",
            base=None,
            observation=None,
            unobservable_detail=None,
            observation_failure="the forge read failed and this host holds no cached observation",
        ),
        now=_NOW,
    )

    assert verdict.condition == CONDITION_OBSERVATION_UNOBSERVABLE
    assert verdict.detail.splitlines()[5] == "  release observation taken at: unknown"


def test_the_transition_admits_an_out_of_window_carrier_before_its_deadline() -> None:
    verdict = fabro_currency_verdict(subject=_subject(base=_CARRIER), now=_NOW)

    assert verdict.admitted is True
    assert verdict.condition == CONDITION_TRANSITION_ADMITTED
    assert TRANSITION_WORK_ITEM in verdict.detail
    assert TRANSITION_DEADLINE.isoformat() in verdict.detail
    # It STATES the gap it is excusing, so the record cannot be mistaken for an
    # in-window base — which is the one description the clause forbids it.
    assert "NOT as an in-window base" in verdict.detail
    assert "89 calendar days" in verdict.detail


def test_the_transition_refuses_at_the_deadline_instant_itself() -> None:
    """Strictly BEFORE, so the ratified instant already refuses.

    An inclusive comparison hands the exception one extra day, and the clause
    says the carrier may remain in service "before" that instant.
    """
    verdict = fabro_currency_verdict(subject=_subject(base=_CARRIER), now=TRANSITION_DEADLINE)

    assert verdict.admitted is False
    assert verdict.condition == CONDITION_OUT_OF_WINDOW
    assert TRANSITION_WORK_ITEM not in verdict.detail


def test_a_carrier_patch_release_is_covered_by_the_same_transition() -> None:
    """The match is on the SERIES, not on one exact tag.

    The carrier has had patch releases; an exact-tag test would quietly drop the
    exception the first time one of them became the resolved base.
    """
    patched = FabroRelease(tag="0.254.3", published_at=_NOW - timedelta(days=90))

    verdict = fabro_currency_verdict(
        subject=_subject(base=patched, observation=_observation(releases=(_NEWEST, patched))),
        now=_NOW,
    )

    assert verdict.condition == CONDITION_TRANSITION_ADMITTED


def test_a_release_whose_version_merely_starts_with_the_series_digits_is_not_the_carrier() -> None:
    """`v0.2540.0` shares the carrier's leading digits and is a different series.

    A prefix test without the dot separator would admit it, which is the shape
    that quietly widens a non-renewable exception into an open one.
    """
    impostor = FabroRelease(tag="v0.2540.0", published_at=_NOW - timedelta(days=90))

    verdict = fabro_currency_verdict(
        subject=_subject(base=impostor, observation=_observation(releases=(_NEWEST, impostor))),
        now=_NOW,
    )

    assert verdict.condition == CONDITION_OUT_OF_WINDOW


def test_a_carrier_inside_the_window_is_admitted_as_current_and_carries_no_notice() -> None:
    """The exception is asked ONLY of a base that already failed the ordinary rule.

    A carrier inside the window needs no exception, and a notice there would tell
    an operator their engine is on borrowed time when it is not.
    """
    recent_carrier = FabroRelease(tag="v0.254.0", published_at=_NOW - timedelta(days=5))

    verdict = fabro_currency_verdict(
        subject=_subject(
            base=recent_carrier, observation=_observation(releases=(_NEWEST, recent_carrier))
        ),
        now=_NOW,
    )

    assert verdict.condition == CONDITION_CURRENT
    assert TRANSITION_WORK_ITEM not in verdict.detail
