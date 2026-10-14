"""The per-node headroom filter: who it covers, who it skips, who it selects.

Binds the headroom clause of the Per-node selection eligibility predicate in
`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority", and these arms of `SPECIFICATION/scenarios.md` Scenario 60: "Low
session headroom on the primary selects an uncovered fallback", "Unobservable
headroom skips a covered primary without defeating a viable fallback",
"Equality passes the headroom filter without overriding another gate", and "A
passing usage reading cannot clear observed availability evidence".

THE CONTROLS THAT CARRY THE WEIGHT:

- COVERAGE follows the resolved agent id. The uncovered-fallback cases are the
  only ones that can fail for a filter that skips on the READING alone, which
  would empty every chain the moment headroom dipped and is indistinguishable
  from a correct filter on a chain whose candidates are all covered.
- CONFIGURED ORDER survives the skip. A filter that returned the surviving set
  in any other order would still "select a fallback", so the assertion is on
  the whole retained sequence rather than on the head.
- EQUALITY passes. Strictly-below is one character away from at-or-below, and
  every below-floor case passes either way.
- A live hold still skips a candidate the reading would have admitted. That is
  the only case that can fail for a filter that treats a passing reading as
  availability evidence.
"""

from __future__ import annotations

import importlib
from typing import Any

import pytest

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_NOW = "2026-10-14T12:00:00Z"
_CLAUDE = "claude-acp"


def _module(*, name: str) -> Any:
    return importlib.import_module(f"{_PACKAGE}.{name}")


def _candidate(*, candidate_key: str, agent_id: str | None = _CLAUDE) -> Any:
    schema = _module(name="_acp_candidate_schema")
    adapters = _module(name="_acp_node_adapters")
    return schema.AcpCandidate(
        adapter=adapters.AcpAdapter(command="adapter", env={}, args=()),
        identity=schema.AcpCandidateIdentity(
            display_name=candidate_key,
            candidate_key=candidate_key,
            availability_key="anthropic" if agent_id == _CLAUDE else "other",
        ),
        agent_id=agent_id,
    )


def _chain(*, candidates: tuple[Any, ...]) -> Any:
    resolution = _module(name="_acp_chain_resolution")
    return resolution.ResolvedAcpChain(
        node="implement",
        primary=candidates[0],
        fallbacks=tuple(candidates[1:]),
        enabled=True,
        primary_generation="primary-digest",
        full_chain="chain-digest",
        redacted={},
    )


def _gate(*, floor: int, utilization: float | None, unobservable: str | None = None) -> Any:
    headroom = _module(name="_acp_session_headroom")
    return headroom.SessionHeadroomGate(
        reading=headroom.SessionHeadroomReading(
            credential_identity="claude-oauth-aaaaaaaaaaaaaaaa",
            observed_at=_NOW,
            utilization_percent=utilization,
            unobservable_reason=unobservable,
        ),
        floor=floor,
    )


def _filter(*, chain: Any, gate: Any, holds: tuple[Any, ...] = ()) -> Any:
    preflight = _module(name="_acp_candidate_preflight")
    return preflight.filter_node_candidates(
        chain=chain,
        inputs=preflight.PreflightInputs(session_headroom=gate, holds=holds),
        assessed={},
    )


def _retained(*, result: Any) -> list[str | None]:
    return [
        None if candidate.identity is None else candidate.identity.candidate_key
        for candidate in result.candidates
    ]


@pytest.mark.parametrize(
    ("utilization", "unobservable"),
    [
        pytest.param(85.0, None, id="below-floor"),
        pytest.param(None, "transport-failed", id="unobservable"),
    ],
)
def test_a_skipped_covered_primary_leaves_the_uncovered_fallback_selected(
    utilization: float | None, unobservable: str | None
) -> None:
    """Selection continues in CONFIGURED ORDER to the next eligible candidate.

    The fallback is deliberately UNCOVERED, which is what makes this case able
    to fail: a filter that skipped on the reading without asking coverage would
    empty the chain instead of selecting the fallback, and no below-floor case
    on an all-covered chain can tell the two apart.
    """
    preflight = _module(name="_acp_candidate_preflight")
    chain = _chain(
        candidates=(
            _candidate(candidate_key="claude-opus"),
            _candidate(candidate_key="codex-gpt", agent_id="codex-acp"),
            _candidate(candidate_key="claude-sonnet"),
        )
    )

    result = _filter(
        chain=chain, gate=_gate(floor=20, utilization=utilization, unobservable=unobservable)
    )

    assert _retained(result=result) == ["codex-gpt"]
    assert result.exhausted is False
    assert [skip.candidate_key for skip in result.skipped] == ["claude-opus", "claude-sonnet"]
    # The skip reports its own token and NO hold identity, cause or expiry: the
    # reading minted no hold, and representing it as one is what the selection
    # record clause forbids in as many words.
    for skip in result.skipped:
        assert skip.reason == preflight.HEADROOM_SKIP
        assert (skip.cause, skip.scope, skip.hold_key, skip.condition) == (None, None, None, None)


def test_remaining_headroom_equal_to_the_floor_is_not_skipped() -> None:
    """Equality passes: the comparison is strictly below, not at-or-below."""
    chain = _chain(candidates=(_candidate(candidate_key="claude-opus"),))

    result = _filter(chain=chain, gate=_gate(floor=20, utilization=80.0))

    assert _retained(result=result) == ["claude-opus"]
    assert result.skipped == ()


def test_a_passing_reading_does_not_clear_a_live_hold() -> None:
    """A reading above the floor is not availability evidence.

    The hold case is the only one that can fail for a filter that let a healthy
    reading admit a held candidate, and the retained set is asserted alongside
    so the hold is not merely reported while the candidate still runs.
    """
    preflight = _module(name="_acp_candidate_preflight")
    records = _module(name="_acp_hold_records")
    hold = records.AcpAvailabilityHold(
        schema_version=1,
        observation_id="obs-held",
        scope="availability-domain",
        hold_key="anthropic",
        candidate_key=None,
        cause="quota",
        occurred_at=_NOW,
        expires_at="2099-01-01T00:00:00Z",
    )
    chain = _chain(candidates=(_candidate(candidate_key="claude-opus"),))

    result = _filter(chain=chain, gate=_gate(floor=20, utilization=5.0), holds=(hold,))

    assert _retained(result=result) == []
    assert [skip.reason for skip in result.skipped] == [preflight.TYPED_HOLD_SKIP]


def test_no_gate_and_no_coverage_each_skip_nothing() -> None:
    """Both fail-open guards, which add no restriction in opposite situations.

    Absent gate: no usage request was made, so there is no reading to grade.
    Uncovered candidate: the clause does not reach it. Neither is evidence
    against a candidate, and a filter that skipped on either would refuse work
    on a measurement nobody took.
    """
    headroom = _module(name="_acp_session_headroom")
    covered = _chain(candidates=(_candidate(candidate_key="claude-opus"),))
    uncovered = _chain(candidates=(_candidate(candidate_key="manual-adapter", agent_id=None),))

    assert _retained(result=_filter(chain=covered, gate=None)) == ["claude-opus"]
    assert _retained(result=_filter(chain=uncovered, gate=_gate(floor=20, utilization=99.0))) == [
        "manual-adapter"
    ]
    assert headroom.candidate_is_covered(candidate=covered.primary) is True
    assert headroom.candidate_is_covered(candidate=uncovered.primary) is False


def test_the_usage_request_is_only_warranted_where_a_covered_candidate_renders() -> None:
    """`any_covered_candidate` is what keeps the clause off the no-op path.

    A DISABLED chain of covered candidates answers False, which is the arm that
    matters: a repository on the pre-fallback path is never filtered at all, so
    a reading taken for it would be an external call added to a dispatch the
    clause cannot govern.
    """
    headroom = _module(name="_acp_session_headroom")
    resolution = _module(name="_acp_chain_resolution")
    covered = _chain(candidates=(_candidate(candidate_key="claude-opus"),))
    uncovered = _chain(candidates=(_candidate(candidate_key="codex-gpt", agent_id="codex-acp"),))
    disabled = resolution.ResolvedAcpChain(
        node="implement",
        primary=covered.primary,
        fallbacks=(),
        enabled=False,
        primary_generation="primary-digest",
        full_chain="chain-digest",
        redacted={},
    )

    assert headroom.any_covered_candidate(chains={"implement": covered}) is True
    assert headroom.any_covered_candidate(chains={"implement": uncovered}) is False
    assert headroom.any_covered_candidate(chains={"implement": disabled}) is False
