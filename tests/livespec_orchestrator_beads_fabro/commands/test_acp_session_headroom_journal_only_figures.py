"""The two journal-only figures DECIDE NOTHING, and are never coerced to numbers.

Binds the last two assertions of work-item `bd-ib-rszkjc`: "The seven-day
figure and the drain rate are journaled only and change no admission decision",
and "An assessment record whose headers or history lack either figure carries
null for that field rather than a coerced number".

NEITHER ASSERTION NEEDED A PRODUCT CHANGE, which is why this file arrives as a
behaviour-PRESERVING addition rather than through a Red. Both are properties
the earlier slices already hold: the skip predicate reads `remaining_percent`
and the floor, so no value either figure could take is an input to a decision,
and every null arm was built as a null arm. A test that passed the moment it
was written is the honest shape for an invariant -- authoring a Red for it
would mean first BREAKING one of the two, and the thing being asserted is
exactly that neither can be broken by accident.

WHY ASSERT A NEGATIVE AT ALL, since a passing test proves only today's build.
Because the clause's whole licence rests on it. Keeping both figures
journal-only is what made this change implementable without a specification
change; the moment either one reaches a decision, the floor's ratified
behaviour has silently changed and the admission contract says something it was
never ratified to say. So the invariant is asserted at the surface where it
would break -- the real node filter, over a matrix of figure values -- rather
than left to a reader of the predicate to notice.

THE MATRIX IS THE DISCRIMINATOR. One reading carrying one dire figure proves
little: a filter that happened to ignore that one value would pass. Each case
below pairs a decision-relevant `remaining_percent` with the most alarming
journal-only figures available and asserts the verdict is the one the
five-hour reading ALONE earns -- and the below-floor row is in the matrix too,
so a filter that had stopped deciding anything at all would fail rather than
pass.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace

import pytest
from livespec_orchestrator_beads_fabro.commands import _acp_candidate_preflight as preflight
from livespec_orchestrator_beads_fabro.commands import _acp_session_headroom as headroom
from livespec_orchestrator_beads_fabro.commands import _acp_session_headroom_records as records
from livespec_orchestrator_beads_fabro.commands._acp_builtin_candidates import ANTHROPIC_DOMAIN
from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import (
    AcpCandidate,
    AcpCandidateIdentity,
)
from livespec_orchestrator_beads_fabro.commands._acp_chain_resolution import ResolvedAcpChain
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import AcpAdapter

_NOW = "2026-10-15T12:00:00Z"
_FLOOR = 20
_IDENTITY = "cred-1"
_CLAUDE_PAIR = (ANTHROPIC_DOMAIN, "builtin-anthropic-0123456789abcdef")
_BUILTIN_PAIRS = frozenset({_CLAUDE_PAIR})

# The most alarming values either journal-only figure can take: a credential
# all but through its seven-day allowance, and one losing 90 points of its
# five-hour window per hour. If either could reach a decision, these are the
# values that would make it.
_DIRE_SEVEN_DAY = 99.9
_DIRE_DRAIN = 90.0


def _reading(
    *, utilization: float, seven_day: float | None = None, drain: float | None = None
) -> headroom.SessionHeadroomReading:
    """One graded reading, then the drain rate the gate would have attached."""
    graded = headroom.session_headroom_reading(
        credential_identity=_IDENTITY,
        observed_at=_NOW,
        utilization=utilization,
        seven_day_utilization_percent=seven_day,
    )
    return replace(graded, five_hour_drain_percent_per_hour=drain)


def _covered() -> AcpCandidate:
    return AcpCandidate(
        adapter=AcpAdapter(command="claude-adapter", env={}, args=()),
        identity=AcpCandidateIdentity(
            display_name="built-in Anthropic ACP adapter",
            candidate_key=_CLAUDE_PAIR[1],
            availability_key=_CLAUDE_PAIR[0],
        ),
    )


def _chain() -> ResolvedAcpChain:
    return ResolvedAcpChain(
        node="implement",
        primary=_covered(),
        fallbacks=(),
        enabled=True,
        primary_generation="primary-digest",
        full_chain="chain-digest",
        redacted={},
    )


def _surviving_keys(*, reading: headroom.SessionHeadroomReading) -> list[str]:
    """Which candidates the REAL node filter leaves selectable for this reading."""
    node = preflight.filter_node_candidates(
        chain=_chain(),
        inputs=preflight.PreflightInputs(
            builtin_pairs=_BUILTIN_PAIRS,
            headroom=headroom.SessionHeadroomPolicy(floor_percent=_FLOOR, read=lambda: reading),
        ),
        assessed={},
    )
    return [
        candidate.identity.candidate_key
        for candidate in node.candidates
        if candidate.identity is not None
    ]


# ---------------------------------------------------------------------------
# Journaled only: no value either figure takes reaches an admission decision.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("utilization", "expected"),
    [
        # 25 percent remaining, above the floor of 20: selectable.
        (75.0, [_CLAUDE_PAIR[1]]),
        # Exactly at the floor: equality passes, so still selectable.
        (80.0, [_CLAUDE_PAIR[1]]),
        # 10 percent remaining, below the floor: skipped. This row is the
        # positive control -- without it, a filter that had stopped deciding
        # anything would satisfy every other row in the matrix.
        (90.0, []),
    ],
)
def test_the_journal_only_figures_do_not_move_the_filters_verdict(
    utilization: float, expected: list[str]
) -> None:
    """The dire figures earn the SAME verdict the five-hour reading alone does."""
    bare = _surviving_keys(reading=_reading(utilization=utilization))
    dire = _surviving_keys(
        reading=_reading(utilization=utilization, seven_day=_DIRE_SEVEN_DAY, drain=_DIRE_DRAIN)
    )

    assert bare == expected
    assert dire == expected


@pytest.mark.parametrize("seven_day", [None, 0.0, 50.0, _DIRE_SEVEN_DAY])
@pytest.mark.parametrize("drain", [None, 0.0, 2.0, _DIRE_DRAIN])
def test_the_skip_predicate_is_indifferent_to_both_figures(
    seven_day: float | None, drain: float | None
) -> None:
    """Sixteen combinations, one verdict: the predicate's inputs exclude both.

    A credential well above the floor stays unskipped whatever either figure
    says, and the companion below-floor reading stays skipped -- so the
    indifference is asserted in both directions rather than only on the arm
    that happens to pass.
    """
    ample = _reading(utilization=10.0, seven_day=seven_day, drain=drain)
    short = _reading(utilization=95.0, seven_day=seven_day, drain=drain)

    assert headroom.headroom_skips_candidate(reading=ample, floor_percent=_FLOOR) is False
    assert headroom.headroom_skips_candidate(reading=short, floor_percent=_FLOOR) is True


def test_a_dire_seven_day_window_still_journals_its_reading() -> None:
    """The figure is RECORDED where it decides nothing, which is the whole point."""
    reading = _reading(utilization=10.0, seven_day=_DIRE_SEVEN_DAY, drain=_DIRE_DRAIN)

    record = records.session_headroom_assessment_record(
        work_item_id="bd-ib-item", floor_percent=_FLOOR, assessments=(reading,)
    )

    assert record["assessments"] == [
        {
            "credential_identity": _IDENTITY,
            "utilization_percent": 10.0,
            "remaining_percent": 90.0,
            "unobservable": None,
            "observed_at": _NOW,
            "seven_day_utilization_percent": _DIRE_SEVEN_DAY,
            "five_hour_drain_percent_per_hour": _DIRE_DRAIN,
        }
    ]


# ---------------------------------------------------------------------------
# Null, never a coerced number -- asserted on the RENDERED record.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "reading_factory",
    [
        pytest.param(lambda: _reading(utilization=10.0), id="observable"),
        pytest.param(
            lambda: headroom.unobservable_session_headroom(
                credential_identity=_IDENTITY, observed_at=_NOW, reason="timed-out"
            ),
            id="timed-out",
        ),
        pytest.param(
            lambda: headroom.unobservable_session_headroom(
                credential_identity="absent", observed_at=_NOW, reason="absent-credential"
            ),
            id="absent-credential",
        ),
        pytest.param(
            lambda: headroom.session_headroom_reading(
                credential_identity=_IDENTITY, observed_at=_NOW, utilization="not-a-number"
            ),
            id="unreadable-utilization",
        ),
    ],
)
def test_a_lacking_figure_renders_as_null_and_not_as_a_number(
    reading_factory: Callable[[], headroom.SessionHeadroomReading],
) -> None:
    """The keys are PRESENT and hold JSON null, on every reading shape.

    Asserted on the RENDERED line rather than on the mapping, because that is
    the byte sequence an operator and a later reader actually see. The two
    failure directions are opposite and both would be invisible in the
    mapping: an OMITTED key reads as a record from a build predating this
    clause, and a zero reads as a measurement -- 0.0 is exactly what an
    untouched seven-day window and an unspent credential genuinely report.
    """
    record = records.session_headroom_assessment_record(
        work_item_id="bd-ib-item", floor_percent=_FLOOR, assessments=(reading_factory(),)
    )

    rendered = json.dumps(record, sort_keys=True)

    assert '"five_hour_drain_percent_per_hour": null' in rendered
    assert '"seven_day_utilization_percent": null' in rendered


def test_a_present_figure_is_the_positive_control_for_that_rendering() -> None:
    """Without this, a projection that wrote null UNCONDITIONALLY would pass above."""
    record = records.session_headroom_assessment_record(
        work_item_id="bd-ib-item",
        floor_percent=_FLOOR,
        assessments=(_reading(utilization=10.0, seven_day=95.0, drain=30.0),),
    )

    rendered = json.dumps(record, sort_keys=True)

    assert '"five_hour_drain_percent_per_hour": 30.0' in rendered
    assert '"seven_day_utilization_percent": 95.0' in rendered


def test_a_zero_figure_is_journaled_as_zero_rather_than_as_null() -> None:
    """0.0 is a READING, and the record must keep it apart from an absence.

    This is the mirror of the null cases and the reason they are worth
    asserting: an untouched seven-day window genuinely reports 0.0, and a
    credential nobody is spending genuinely drains at 0.0, so a projection that
    collapsed falsy figures to null would erase two real measurements.
    """
    record = records.session_headroom_assessment_record(
        work_item_id="bd-ib-item",
        floor_percent=_FLOOR,
        assessments=(_reading(utilization=10.0, seven_day=0.0, drain=0.0),),
    )

    rendered = json.dumps(record, sort_keys=True)

    assert '"five_hour_drain_percent_per_hour": 0.0' in rendered
    assert '"seven_day_utilization_percent": 0.0' in rendered
