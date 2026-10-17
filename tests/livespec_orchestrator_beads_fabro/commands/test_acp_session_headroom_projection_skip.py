"""A covered candidate projected to empty inside the horizon leaves the set.

Binds the projection-skip sentences of `SPECIFICATION/contracts.md` section
"Dispatcher admission, WIP cap, and post-merge acceptance", paragraph
"Admission filters candidates by projected Claude session headroom": "The
candidate MUST be skipped for this admission evaluation when its projected
exhaustion instant is strictly earlier than the observation time plus the
horizon"; "A horizon of 0 disables projection skips while retaining the
computation and its journal record"; and "A projection skip has exactly the
semantics of a floor skip: it is ephemeral and candidate-local to this
evaluation; per-node selection MUST continue to the next eligible candidate."

THE CONTROL IS WHAT GIVES THE SKIP MEANING, and it is the same chain with a
slower drain. A filter that skipped every covered candidate carrying a
measurable projection would satisfy the positive case exactly as well as a
correct one, and the record it wrote would read identically -- the rate and the
exhaustion instant are both there either way, and only the comparison against
the horizon says which answer was earned.

PER-NODE SELECTION CONTINUING IS ASSERTED ON THE SURVIVING CANDIDATE RATHER
THAN ON THE SKIP. The chain's second candidate is UNCOVERED, which is the only
shape that can show continuation: every covered candidate shares the one
reading, so a chain of two covered candidates empties whole and could not tell
"selection continued" from "selection had nowhere to go".

THE HORIZON-0 DISABLE NEEDS A FIXTURE THE ARITHMETIC CANNOT SETTLE. With a
horizon of 0 the comparison instant IS the observation instant, and a projected
exhaustion computed from a positive rate is never before the observation it was
computed from -- so an ordinary fixture passes whether or not the ratified
disable is implemented at all. The discriminating reading carries a NEGATIVE
rate, which nothing in the drain measurement can produce (it returns null for a
window that did not rise) and which is used here precisely because it is the one
input that drives the comparison to the wrong side of a zero horizon. Its
positive control, the same reading under a positive horizon, skips -- so the
pair separates "the guard is there" from "this fixture skips nothing anywhere".
"""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro.commands import _acp_candidate_preflight as preflight
from livespec_orchestrator_beads_fabro.commands import _acp_session_headroom as headroom
from livespec_orchestrator_beads_fabro.commands import (
    _acp_session_headroom_projection as projection,
)
from livespec_orchestrator_beads_fabro.commands._acp_builtin_candidates import ANTHROPIC_DOMAIN
from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import (
    AcpCandidate,
    AcpCandidateIdentity,
)
from livespec_orchestrator_beads_fabro.commands._acp_chain_resolution import ResolvedAcpChain
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import AcpAdapter
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom_drain import (
    SessionHeadroomBaseline,
)

_NOW = "2026-10-16T12:00:00Z"
_EARLIER = "2026-10-16T11:30:00Z"
_IDENTITY = "cred-1"
_FLOOR = 20
_HORIZON = 180
_CLAUDE_PAIR = (ANTHROPIC_DOMAIN, "builtin-anthropic-0123456789abcdef")
_BUILTIN_PAIRS = frozenset({_CLAUDE_PAIR})


def _identity(*, availability_key: str, candidate_key: str) -> AcpCandidateIdentity:
    return AcpCandidateIdentity(
        display_name=f"{availability_key}/{candidate_key}",
        candidate_key=candidate_key,
        availability_key=availability_key,
    )


def _covered() -> AcpCandidate:
    return AcpCandidate(
        adapter=AcpAdapter(command="claude-adapter", env={}, args=()),
        identity=_identity(availability_key=_CLAUDE_PAIR[0], candidate_key=_CLAUDE_PAIR[1]),
    )


def _uncovered() -> AcpCandidate:
    return AcpCandidate(
        adapter=AcpAdapter(command="codex-adapter", env={}, args=()),
        identity=_identity(availability_key="codex", candidate_key="gpt-5-5"),
    )


def _baseline() -> SessionHeadroomBaseline:
    return SessionHeadroomBaseline(
        utilization_percent=10.0, observed_at=_EARLIER, elapsed_hours=0.5
    )


def _reading(*, rate: float | None = 25.0) -> headroom.SessionHeadroomReading:
    """A reading 50 points from empty, draining at `rate` points an hour."""
    return headroom.SessionHeadroomReading(
        credential_identity=_IDENTITY,
        observed_at=_NOW,
        utilization_percent=50.0,
        remaining_percent=50.0,
        five_hour_drain_percent_per_hour=rate,
    )


def _assessed(
    *, rate: float | None = 25.0, horizon_minutes: int = _HORIZON
) -> headroom.SessionHeadroomReading:
    """That reading, carrying the projection this evaluation's dials imply."""
    reading = _reading(rate=rate)
    return projection.reading_with_projection(
        reading=reading,
        projection=projection.session_headroom_projection(
            reading=reading,
            baseline=_baseline(),
            floor_percent=_FLOOR,
            horizon_minutes=horizon_minutes,
        ),
    )


def _filter(
    *, reading: headroom.SessionHeadroomReading, horizon_minutes: int = _HORIZON
) -> preflight.NodePreflight:
    policy = headroom.SessionHeadroomPolicy(
        floor_percent=_FLOOR, horizon_minutes=horizon_minutes, read=lambda: reading
    )
    chain = ResolvedAcpChain(
        node="implement",
        primary=_covered(),
        fallbacks=(_uncovered(),),
        enabled=True,
        primary_generation="primary-digest",
        full_chain="chain-digest",
        redacted={},
    )
    return preflight.filter_node_candidates(
        chain=chain,
        inputs=preflight.PreflightInputs(builtin_pairs=_BUILTIN_PAIRS, headroom=policy),
        assessed={},
    )


def test_a_projection_inside_the_horizon_skips_and_selection_continues() -> None:
    """50 points at 25 an hour empties in two hours, inside a three-hour horizon."""
    node = _filter(reading=_assessed())

    assert [candidate.identity for candidate in node.candidates] == [_uncovered().identity]
    [skip] = node.skipped
    assert skip.reason == preflight.HEADROOM_SKIP
    assert skip.availability_key == _CLAUDE_PAIR[0]
    assert skip.candidate_key == _CLAUDE_PAIR[1]
    assert skip.headroom is not None
    assert skip.headroom.projection is not None
    assert skip.headroom.projection.skip_applied is True
    # The reading is journalable whether or not it refused anything.
    assert node.assessments == (_assessed(),)


def test_a_projection_beyond_the_horizon_leaves_the_candidate_selectable() -> None:
    """The control: the same chain and reading, draining five times slower."""
    node = _filter(reading=_assessed(rate=5.0))

    assert len(node.candidates) == 2
    assert node.skipped == ()
    assert node.assessments == (_assessed(rate=5.0),)


def test_a_horizon_of_zero_skips_nobody_while_the_projection_is_still_journaled() -> None:
    """The dial switches the SKIP off and leaves the computation standing."""
    reading = _assessed(horizon_minutes=0)

    node = _filter(reading=reading, horizon_minutes=0)

    assert len(node.candidates) == 2
    assert node.skipped == ()
    assert reading.projection is not None
    assert reading.projection.result == headroom.PROJECTED_RESULT
    assert reading.projection.five_hour_drain_percent_per_hour == 25.0
    assert reading.projection.projected_exhaustion_at == "2026-10-16T14:00:00Z"
    assert reading.projection.horizon_minutes == 0
    assert reading.projection.skip_applied is False


@pytest.mark.parametrize(("horizon_minutes", "expected_skips"), [(0, 0), (_HORIZON, 1)])
def test_the_horizon_zero_disable_is_a_guard_and_not_an_arithmetic_accident(
    horizon_minutes: int, expected_skips: int
) -> None:
    """A negative rate puts the exhaustion BEFORE its own observation instant.

    Only an explicit horizon-0 test refuses to skip there, so this pair is what
    separates the ratified disable from a property of the division.
    """
    reading = _assessed(rate=-25.0, horizon_minutes=horizon_minutes)

    node = _filter(reading=reading, horizon_minutes=horizon_minutes)

    assert reading.projection is not None
    assert reading.projection.projected_exhaustion_at == "2026-10-16T10:00:00Z"
    assert reading.projection.skip_applied is (expected_skips == 1)
    assert len(node.skipped) == expected_skips


def test_a_reading_carrying_no_projection_refuses_nothing() -> None:
    """The arm every policy-less surface takes: no projection, so no skip.

    Wait attention and idle-factory compose a verdict with no policy and take
    no reading at all, so a projection predicate that treated an absent result
    as a skip would empty every chain they graded while spending no request to
    justify it.
    """
    node = _filter(reading=_reading())

    assert len(node.candidates) == 2
    assert node.skipped == ()
