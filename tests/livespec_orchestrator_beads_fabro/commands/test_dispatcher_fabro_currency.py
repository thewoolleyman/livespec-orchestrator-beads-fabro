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
    CONDITION_UNIDENTIFIED_BUILD,
    CURRENCY_WINDOW_DAYS,
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
_OUT_OF_WINDOW = FabroRelease(tag="v0.254.0", published_at=_NOW - timedelta(days=90))


def _observation(*, releases: tuple[FabroRelease, ...]) -> FabroReleaseObservation:
    return FabroReleaseObservation(releases=releases, observed_at=_NOW)


def _subject(
    *,
    serving_commit: str | None = "8869e88",
    base: FabroRelease | None = _IN_WINDOW,
    observation: FabroReleaseObservation | None = None,
    unobservable_detail: str | None = None,
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
    assert lines[3] == "  upstream base: v0.254.0 published 2026-07-13T09:00:00+00:00"
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
