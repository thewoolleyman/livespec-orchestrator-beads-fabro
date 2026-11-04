"""A weekly-exhausted candidate leaves the set, and selection carries on past it.

Binds the skip sentences of the seven-day half of
`SPECIFICATION/contracts.md` section "Dispatcher admission, WIP cap, and
post-merge acceptance", paragraph "Admission filters candidates by projected
Claude session headroom": "With a positive floor, a covered candidate whose
seven-day status is exhausted MUST be skipped for this admission evaluation.
This seven-day skip is a headroom skip with exactly the semantics of a floor
skip." The governing scenario is `SPECIFICATION/scenarios.md` Scenario 231,
whose first block ends "the candidate is skipped by a seven-day skip and
per-node selection continues to the next eligible candidate".

THE FIVE-HOUR READING IS DELIBERATELY AMPLE, which is the whole point of the
clause: an account refused its WEEKLY allowance reports five-hour room, so
every existing arm of the filter admits it and the run is launched into a
refusal it cannot avoid. The reading below therefore sits far above the floor
and carries no projection at all, and each case asserts the kind the skip
reports -- so a skip produced by the floor or the projection arm fails here
instead of passing for the right reason.

TWO CASES, PULLING IN OPPOSITE DIRECTIONS, because the claim is a DISCRIMINATION
rather than a refusal. A filter that skipped every covered candidate would
satisfy the positive case perfectly and would idle the factory on every healthy
account; the admitted case is the only thing that can catch it, and it differs
from the positive one in the weekly STATUS and nothing else.

THE CONTINUED SELECTION IS READ OFF THE SURVIVING CANDIDATE, not off the skip.
"Per-node selection continues to the next eligible candidate" is a claim about
what the node still holds, and a node that merely recorded the skip while
emptying its chain would satisfy every assertion about the skip itself.

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
_IDENTITY = "cred-weekly"
_FLOOR = 20
_HORIZON = 180
_CLAUDE_PAIR = (ANTHROPIC_DOMAIN, "builtin-anthropic-0123456789abcdef")
_BUILTIN_PAIRS = frozenset({_CLAUDE_PAIR})
_UNCOVERED_PAIR = ("codex", "gpt-5-5")

# Spelled as a LITERAL and bound to the exported name by the first case,
# because this file's Red predates the constant and a Red's test bytes are
# fixed across its Red-to-Green pair.
_SEVEN_DAY_KIND = "seven-day"

_ALLOWED = "allowed"


def _candidate(*, pair: tuple[str, str]) -> AcpCandidate:
    return AcpCandidate(
        adapter=AcpAdapter(command=f"{pair[0]}-adapter", env={}, args=()),
        identity=AcpCandidateIdentity(
            display_name=f"{pair[0]}/{pair[1]}",
            candidate_key=pair[1],
            availability_key=pair[0],
        ),
    )


def _chain() -> ResolvedAcpChain:
    """A covered Claude primary with an UNCOVERED fallback behind it."""
    return ResolvedAcpChain(
        node="implement",
        primary=_candidate(pair=_CLAUDE_PAIR),
        fallbacks=(_candidate(pair=_UNCOVERED_PAIR),),
        enabled=True,
        primary_generation="primary-digest",
        full_chain="chain-digest",
        redacted={},
    )


def _reading(*, status: str) -> headroom.SessionHeadroomReading:
    """Ample five-hour room, and a spent weekly window the status decides on.

    Both figures are PERCENTAGES, as every reading in this package is: the
    fraction the provider's own header carries is converted once, in the read,
    so a fixture spelling a fraction here would be a reading of one percent
    wearing the look of a full window.
    """
    return headroom.session_headroom_reading(
        credential_identity=_IDENTITY,
        observed_at=_NOW,
        utilization=5,
        seven_day=headroom.seven_day_reading(utilization=100.0, status=status),
    )


def _filtered(*, status: str) -> preflight.NodePreflight:
    reading = _reading(status=status)
    # The premise of the clause, asserted rather than assumed: this reading is
    # far above the floor, so neither existing arm has anything to skip on.
    assert reading.remaining_percent == 95.0
    assert headroom.headroom_skips_candidate(reading=reading, floor_percent=_FLOOR) is False
    return preflight.filter_node_candidates(
        chain=_chain(),
        inputs=preflight.PreflightInputs(
            builtin_pairs=_BUILTIN_PAIRS,
            headroom=headroom.SessionHeadroomPolicy(
                floor_percent=_FLOOR, horizon_minutes=_HORIZON, read=lambda: reading
            ),
        ),
        assessed={},
    )


def test_a_weekly_refusal_skips_the_covered_candidate_and_selection_continues() -> None:
    """The skip names itself, and the uncovered fallback is what gets selected."""
    assert getattr(preflight, "SEVEN_DAY_SKIP_KIND", None) == _SEVEN_DAY_KIND

    node = _filtered(status=headroom.SEVEN_DAY_REJECTED_STATUS)

    [skip] = node.skipped
    assert skip.candidate_key == _CLAUDE_PAIR[1]
    assert skip.reason == preflight.HEADROOM_SKIP
    assert skip.headroom_skip_kind == _SEVEN_DAY_KIND
    # Neither existing shortfall produced it, so the kind is a reading of the
    # weekly window rather than a relabelling of a floor or projection skip.
    assert skip.headroom_skip_kind not in {
        preflight.FLOOR_SKIP_KIND,
        preflight.PROJECTION_SKIP_KIND,
    }
    # The skip carries the reading a journal joins it to the assessment by.
    assert skip.headroom is not None
    assert skip.headroom.credential_identity == _IDENTITY
    assert skip.headroom_floor_percent == _FLOOR
    # Per-node selection continued: the next eligible candidate is selected,
    # and the node is not exhausted.
    assert [one.identity.candidate_key for one in node.candidates if one.identity is not None] == [
        _UNCOVERED_PAIR[1]
    ]
    assert node.exhausted is False


def test_a_weekly_allowance_the_provider_has_not_refused_skips_nothing() -> None:
    """The control: a FULLY SPENT weekly window the provider still serves.

    The sharpest form of the control, since the reading differs from the
    refused one in the status and in nothing else: a build inferring exhaustion
    from the percentage would skip this candidate too, and the clause's "a
    utilization below 100, or any other value is not exhaustion" forecloses
    exactly that.
    """
    node = _filtered(status=_ALLOWED)

    assert node.skipped == ()
    assert [one.identity.candidate_key for one in node.candidates if one.identity is not None] == [
        _CLAUDE_PAIR[1],
        _UNCOVERED_PAIR[1],
    ]
    # The reading was still taken and is still journalable, which is what tells
    # an admitted candidate apart from one the filter never assessed.
    [assessment] = node.assessments
    assert assessment.seven_day.status == _ALLOWED


@pytest.mark.parametrize("status", ["rejected", "allowed"])
def test_the_weekly_reading_is_taken_once_for_both_chain_positions(status: str) -> None:
    """One assessment per credential per evaluation, whatever it decides."""
    reads: list[str] = []
    reading = _reading(status=status)

    def _read() -> headroom.SessionHeadroomReading:
        reads.append(_IDENTITY)
        return reading

    node = preflight.filter_node_candidates(
        chain=_chain(),
        inputs=preflight.PreflightInputs(
            builtin_pairs=_BUILTIN_PAIRS,
            headroom=headroom.SessionHeadroomPolicy(
                floor_percent=_FLOOR, horizon_minutes=_HORIZON, read=_read
            ),
        ),
        assessed={},
    )

    # Only the COVERED position owes a reading, so the uncovered fallback adds
    # none -- and the one reading taken is the one the node journals.
    assert reads == [_IDENTITY]
    assert len(node.assessments) == 1
