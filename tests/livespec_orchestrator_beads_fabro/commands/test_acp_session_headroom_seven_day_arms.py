"""Every weekly reading that is NOT a refusal, and the dial that switches it off.

Binds the fail-open sentences of the seven-day half of
`SPECIFICATION/contracts.md` section "Dispatcher admission, WIP cap, and
post-merge acceptance", paragraph "Admission filters candidates by projected
Claude session headroom": "A seven-day status counts as exhausted only when the
provider explicitly reports that the seven-day allowance is refused (for
Claude, a seven-day status of `rejected`); a warning status, a utilization
below 100, or any other value is not exhaustion"; "An absent, unparseable or
unrecognised seven-day reading MUST NOT skip a candidate"; and "a floor of 0
disables it". The governing scenario is `SPECIFICATION/scenarios.md` Scenario
231, whose second and third blocks are these two claims.

EVERY CASE HERE IS AN ADMISSION, so every one of them is satisfied by a build
that reads no weekly window at all -- which is exactly the build this clause
replaced. The discriminator is the REFUSING reading each case is paired
against, asserted in the same file on the same fixture, differing only in the
field under test. Without it this module is a set of assertions that cannot
fail.

THE READING IS ASSERTED JOURNALED ON EVERY ARM, because the clause requires the
figures recorded whether or not they skip anything -- "the journal records the
seven-day reading, or records it as unobservable when it is absent" -- and a
build that simply stopped assessing an unrefused account would satisfy the
admission half of every case while recording nothing.

A UTILIZATION OF 100 WITH NO REFUSAL IS THE SHARPEST ARM. A weekly window
reported fully spent reads exactly like exhaustion, and inferring one from the
percentage would refuse an account the provider is still serving -- which the
clause forecloses by making the STATUS the only thing that counts.

Everything is HERMETIC: the provider read is the policy's injected seam, and no
credential value leaves this file.
"""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro.commands import _acp_candidate_preflight as preflight
from livespec_orchestrator_beads_fabro.commands import _acp_session_headroom as headroom
from livespec_orchestrator_beads_fabro.commands._acp_builtin_candidates import ANTHROPIC_DOMAIN
from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import (
    AcpCandidate,
    AcpCandidateIdentity,
)
from livespec_orchestrator_beads_fabro.commands._acp_chain_resolution import ResolvedAcpChain
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import AcpAdapter

_NOW = "2026-10-22T12:00:00Z"
_IDENTITY = "cred-weekly-arms"
_FLOOR = 20
_DISABLED_FLOOR = 0
_HORIZON = 180
_CLAUDE_PAIR = (ANTHROPIC_DOMAIN, "builtin-anthropic-0123456789abcdef")
_BUILTIN_PAIRS = frozenset({_CLAUDE_PAIR})

# The provider's own warning word, which the clause names as a non-refusal.
_WARNING = "allowed_warning"


def _chain() -> ResolvedAcpChain:
    """One covered Claude candidate and no fallback behind it."""
    covered = AcpCandidate(
        adapter=AcpAdapter(command="claude-adapter", env={}, args=()),
        identity=AcpCandidateIdentity(
            display_name=f"{_CLAUDE_PAIR[0]}/{_CLAUDE_PAIR[1]}",
            candidate_key=_CLAUDE_PAIR[1],
            availability_key=_CLAUDE_PAIR[0],
        ),
    )
    return ResolvedAcpChain(
        node="implement",
        primary=covered,
        fallbacks=(),
        enabled=True,
        primary_generation="primary-digest",
        full_chain="chain-digest",
        redacted={},
    )


def _reading(*, weekly: headroom.SevenDayReading) -> headroom.SessionHeadroomReading:
    """Ample five-hour room, so only the weekly window can decide anything.

    Every figure in this file is a PERCENTAGE, as every reading in this package
    is: the fraction the provider's own header carries is converted once, in
    the read, so a fixture spelling a fraction here would label a reading of
    one percent as a full window and the rows below would not be the rows they
    claim to be.
    """
    return headroom.session_headroom_reading(
        credential_identity=_IDENTITY, observed_at=_NOW, utilization=5, seven_day=weekly
    )


def _filtered(
    *, weekly: headroom.SevenDayReading, floor_percent: int = _FLOOR
) -> preflight.NodePreflight:
    return preflight.filter_node_candidates(
        chain=_chain(),
        inputs=preflight.PreflightInputs(
            builtin_pairs=_BUILTIN_PAIRS,
            headroom=headroom.SessionHeadroomPolicy(
                floor_percent=floor_percent,
                horizon_minutes=_HORIZON,
                read=lambda: _reading(weekly=weekly),
            ),
        ),
        assessed={},
    )


def _refused() -> headroom.SevenDayReading:
    """The one reading the clause calls exhaustion, this file's discriminator."""
    return headroom.seven_day_reading(utilization=100.0, status=headroom.SEVEN_DAY_REJECTED_STATUS)


_UNREFUSED: list[tuple[str, headroom.SevenDayReading]] = [
    # Absent: the response reported neither figure.
    ("absent", headroom.seven_day_reading(utilization=None, status=None)),
    # Unparseable: a figure that is not a number, with nothing else reported.
    ("unparseable", headroom.seven_day_reading(utilization="soon", status=None)),
    # Out of the clause's inclusive range, which is unreadable rather than a
    # reading of some other number.
    ("out-of-range", headroom.seven_day_reading(utilization=240.0, status=None)),
    # Unrecognised: a status word this build does not know.
    ("unrecognised", headroom.seven_day_reading(utilization=50.0, status="throttled_soon")),
    # The warning status the clause names outright.
    ("warning", headroom.seven_day_reading(utilization=90.0, status=_WARNING)),
    # A utilization below 100, which the clause says is not exhaustion.
    ("below-100", headroom.seven_day_reading(utilization=99.0, status="allowed")),
    # And a window reported fully spent that the provider has NOT refused.
    ("at-100-unrefused", headroom.seven_day_reading(utilization=100.0, status="allowed")),
]


@pytest.mark.parametrize(("label", "weekly"), _UNREFUSED, ids=[one[0] for one in _UNREFUSED])
def test_a_weekly_reading_that_is_not_a_refusal_skips_nothing(
    label: str, weekly: headroom.SevenDayReading
) -> None:
    """Admitted, and still assessed -- with the refusing reading as the control."""
    _ = label

    node = _filtered(weekly=weekly)

    assert node.skipped == ()
    assert [one.identity.candidate_key for one in node.candidates if one.identity is not None] == [
        _CLAUDE_PAIR[1]
    ]
    # The reading was taken and is journalable either way.
    [assessment] = node.assessments
    assert assessment.seven_day == weekly
    # The control: the SAME fixture with a refused weekly allowance empties the
    # node, so this admission is a reading of the status rather than a filter
    # that has nothing to say about the weekly window at all.
    assert _filtered(weekly=_refused()).exhausted is True


@pytest.mark.parametrize(("label", "weekly"), _UNREFUSED, ids=[one[0] for one in _UNREFUSED])
def test_an_unrefused_reading_is_observable_or_explicitly_unobservable(
    label: str, weekly: headroom.SevenDayReading
) -> None:
    """Each arm is one of the two the clause allows, never a coerced figure."""
    _ = label
    reported = weekly.utilization_percent is not None or weekly.status is not None

    assert reported is (weekly.unobservable is None)
    if not reported:
        assert weekly.unobservable == headroom.ABSENT_SEVEN_DAY_READING


def test_a_floor_of_zero_disables_the_seven_day_skip_and_keeps_the_reading() -> None:
    """The dial switches the whole filter off, the weekly arm included."""
    refused = _refused()

    node = _filtered(weekly=refused, floor_percent=_DISABLED_FLOOR)

    assert node.skipped == ()
    assert node.exhausted is False
    assert (
        headroom.seven_day_skips_candidate(
            reading=_reading(weekly=refused), floor_percent=_DISABLED_FLOOR
        )
        is False
    )
    assert (
        headroom.seven_day_skips_candidate(reading=_reading(weekly=refused), floor_percent=_FLOOR)
        is True
    )
    # The reading is STILL taken and journalable, which is what the clause asks
    # of a disabled floor: "a floor of 0 disables every kind of headroom skip
    # while retaining the bounded reading attempt and journal record".
    [assessment] = node.assessments
    assert assessment.seven_day.status == headroom.SEVEN_DAY_REJECTED_STATUS
    # The control: the identical reading at the ratified floor DOES skip, so
    # the admission above is the dial rather than a weekly arm that never
    # fires.
    assert _filtered(weekly=refused, floor_percent=_FLOOR).exhausted is True
