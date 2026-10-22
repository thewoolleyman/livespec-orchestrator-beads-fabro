"""What a factory-recorded success does and does not confirm after expiry.

Binds `SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": "A successful confirmation satisfies the expired observations it
names for that candidate. It MUST NOT satisfy a newer observation." Scenario 94
grades the retirement rule this projection reuses, and Scenario 60's
confirmation sub-scenario grades the selection the projection feeds.

`test_acp_expired_confirmation_admission.py` drives the SAME evidence through
the production admission preflight, which is where the wiring is proved. This
file grades the three answers the projection owes that one success cannot
exercise, each of which is a different way of CONFIRMING NOTHING -- and all
three are invisible at the admission surface, because a candidate that stays
skipped looks identical whichever of them produced the empty confirmation set.

THE THREE NEGATIVE ANSWERS, and why each is a distinct assertion rather than a
restatement. A success whose factory row recorded NO CANDIDATE KEY confirms
nothing for anybody, because availability is confirmed only by a turn whose
candidate identity is known. A success that STARTED BEFORE the observation
occurred confirms nothing, which is the clause's own "MUST NOT satisfy a newer
observation" read through the retirement predicate's time ordering. And a
success on ANOTHER allowance confirms nothing, because the coverage rule is the
hold key's and not the run's.

The positive control is the same shape in reverse, and it is what keeps the
three negatives from passing on a projection that confirms nothing at all: two
successes by ONE candidate identity, across two expired observations, produce
ONE confirmation naming BOTH -- so a per-success grouping, which satisfies every
negative assertion here, fails on the count.
"""

from __future__ import annotations

import importlib
from typing import Any

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

# The observation, and the two instants that straddle it. `_AFTER` is a run
# that began after the outage was seen; `_BEFORE` is one already executing when
# it was, which the contract says proves nothing about it.
_OCCURRED_AT = "2026-10-16T11:40:00Z"
_EXPIRES_AT = "2026-10-16T11:55:00Z"
_AFTER = "2026-10-16T11:56:00Z"
_BEFORE = "2026-10-16T11:30:00Z"

_SECOND_OCCURRED_AT = "2026-10-16T11:42:00Z"
_SECOND_EXPIRES_AT = "2026-10-16T11:57:00Z"


def _module(name: str) -> Any:
    return importlib.import_module(f"{_PACKAGE}.{name}")


def _hold(
    *,
    observation_id: str,
    hold_key: str = "codex",
    occurred_at: str = _OCCURRED_AT,
    expires_at: str = _EXPIRES_AT,
) -> Any:
    """One EXPIRED domain observation, exactly as the journal fold yields it."""
    records = _module("_acp_hold_records")
    return records.AcpAvailabilityHold(
        schema_version=1,
        observation_id=observation_id,
        scope="availability-domain",
        hold_key=hold_key,
        candidate_key=None,
        cause="quota",
        occurred_at=occurred_at,
        expires_at=expires_at,
    )


def _success(
    *,
    run_id: str,
    availability_key: str = "codex",
    candidate_key: str | None = "primary",
    started_at: str = _AFTER,
) -> Any:
    """One SUCCEEDED node attempt as the host-wide factory read derives it."""
    records = _module("_acp_factory_success_records")
    return records.FactorySuccessObservation(
        factory="hp",
        repository="livespec-console-beads-fabro",
        run_id=run_id,
        node_attempt="implement",
        availability_key=availability_key,
        candidate_key=candidate_key,
        started_at=started_at,
    )


def _candidate(*, availability_key: str | None = "codex", candidate_key: str = "primary") -> Any:
    schema = _module("_acp_candidate_schema")
    adapters = _module("_acp_node_adapters")
    identity = (
        None
        if availability_key is None
        else schema.AcpCandidateIdentity(
            display_name=f"{availability_key}/{candidate_key}",
            candidate_key=candidate_key,
            availability_key=availability_key,
        )
    )
    return schema.AcpCandidate(
        adapter=adapters.AcpAdapter(command="adapter", env={}, args=()),
        identity=identity,
        signatures=(),
    )


def _confirmations(*, expired: tuple[Any, ...], successes: tuple[Any, ...]) -> tuple[Any, ...]:
    confirmation = _module("_acp_availability_confirmation")
    return confirmation.confirmations_for_successes(expired_holds=expired, successes=successes)


def _outstanding(
    *, expired: tuple[Any, ...], confirmations: tuple[Any, ...], candidate: Any
) -> Any:
    confirmation = _module("_acp_availability_confirmation")
    return confirmation.outstanding_confirmation_holds(
        expired_holds=expired, confirmations=confirmations, candidate=candidate
    )


def test_one_candidate_identity_yields_one_confirmation_naming_every_observation() -> None:
    """Two successes by one identity confirm both expired observations at once."""
    older = _hold(observation_id="older-observation")
    newer = _hold(
        observation_id="newer-observation",
        occurred_at=_SECOND_OCCURRED_AT,
        expires_at=_SECOND_EXPIRES_AT,
    )

    confirmations = _confirmations(
        expired=(older, newer),
        successes=(_success(run_id="run-one"), _success(run_id="run-two")),
    )

    assert len(confirmations) == 1
    assert (confirmations[0].availability_key, confirmations[0].candidate_key) == (
        "codex",
        "primary",
    )
    assert confirmations[0].observation_ids == frozenset({"older-observation", "newer-observation"})
    assert (
        _outstanding(expired=(older, newer), confirmations=confirmations, candidate=_candidate())
        == ()
    )


def test_a_success_recording_no_candidate_key_confirms_nothing() -> None:
    """An attempt whose row named no candidate establishes no candidate's turn."""
    expired = (_hold(observation_id="older-observation"),)

    confirmations = _confirmations(
        expired=expired, successes=(_success(run_id="run-one", candidate_key=None),)
    )

    assert confirmations == ()
    assert [
        hold.observation_id
        for hold in _outstanding(
            expired=expired, confirmations=confirmations, candidate=_candidate()
        )
    ] == ["older-observation"]


def test_a_success_that_started_before_the_observation_confirms_nothing() -> None:
    """A run already executing when the outage was seen proves nothing about it."""
    expired = (_hold(observation_id="older-observation"),)

    confirmations = _confirmations(
        expired=expired, successes=(_success(run_id="run-one", started_at=_BEFORE),)
    )

    assert confirmations == ()
    assert [
        hold.observation_id
        for hold in _outstanding(
            expired=expired, confirmations=confirmations, candidate=_candidate()
        )
    ] == ["older-observation"]


def test_a_success_on_another_allowance_confirms_nothing() -> None:
    """Coverage is the hold key's, so a success elsewhere leaves this one due."""
    expired = (_hold(observation_id="older-observation"),)

    confirmations = _confirmations(
        expired=expired,
        successes=(_success(run_id="run-one", availability_key="anthropic"),),
    )

    assert confirmations == ()
    assert [
        hold.observation_id
        for hold in _outstanding(
            expired=expired, confirmations=confirmations, candidate=_candidate()
        )
    ] == ["older-observation"]


def test_an_identity_less_candidate_carries_no_outstanding_confirmation() -> None:
    """The one adapter shape allowed to carry no identity is not stranded."""
    expired = (_hold(observation_id="older-observation"),)

    assert (
        _outstanding(
            expired=expired,
            confirmations=(),
            candidate=_candidate(availability_key=None),
        )
        == ()
    )
