"""An outstanding confirmation schedules the cadence, never a provider's claim.

Binds `SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": "If no candidate remains eligible, the Dispatcher MUST retry
automatically after `dispatcher.credential_reprobe_interval_seconds` ... A
provider's own advertised reset instant MUST NOT schedule, shorten, or replace
the probe; it MAY be recorded only as unverified provenance." It also binds
section "Provider spend containment" -> "No silent containment", which requires
the containment refusal to name the governing condition and forbids it to
"invent a hold identity or expiry": "When no hold governs the refusal, it MUST
name the outstanding confirmation ... instead."

AN EXPIRED OBSERVATION HAS NO EXPIRY LEFT TO WAIT FOR, which is why this is the
one emptied-chain shape whose instant can only come from the cadence. A live
hold supplies its own `expires_at` and the wait takes the earliest of them; an
expired record has already passed that instant, so the confirmation's schedule
is the cadence and nothing else -- and the ONLY other instant in the evaluation
is the one the provider asserted.

SO THE CLAIM IS PUT WHERE IT WOULD WIN IF ANYTHING READ IT. The assessment the
emptied node carries claims a reset TEN minutes out against a FIVE-minute
cadence, so a build that adopted, shortened or replaced the schedule with the
provider's figure reads a different instant rather than the same one by
coincidence. The claim's own journal projection is asserted in the same case,
under the key that says it is unverified, because "recorded only as unverified
provenance" and "ignored when scheduling" are two halves of one assertion and a
build that merely dropped the claim satisfies the second alone.

THE TWO CONTROLS ARE HOLDS, and the contract's own wording is why. "When no hold
governs the refusal" makes a durable record outrank the confirmation, so a node
emptied by a typed hold beside a confirmation must still name that hold and take
its expiry, and the legacy blanket must do the same -- without both, a precedence
that simply put the confirmation first satisfies the positive case while
reporting a confirmation for a chain an operator can clear today.
"""

from __future__ import annotations

import importlib
from typing import Any

import pytest

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

_NOW = "2026-10-15T12:00:00Z"
_INTERVAL = 300
# `_NOW` plus `_INTERVAL`, spelled out rather than computed, so the expected
# value cannot be produced by the same arithmetic the implementation uses.
_NOW_PLUS_INTERVAL = "2026-10-15T12:05:00Z"

# The provider's own figure, TEN minutes out: later than the cadence, so
# adopting it is observable, and earlier than the hold expiry below, so
# shortening to it is observable too.
_CLAIMED_RESET = "2026-10-15T12:10:00Z"
_HOLD_EXPIRY = "2026-10-15T12:40:00Z"

_DOMAIN = "availability-domain"
_OBSERVATION_ID = "expired-observation"


def _module(*, name: str) -> Any:
    return importlib.import_module(f"{_PACKAGE}.{name}")


def _reading_claiming_a_reset() -> Any:
    """One assessment carrying the ONE field the provider itself asserts."""
    headroom = _module(name="_acp_session_headroom")
    return headroom.SessionHeadroomReading(
        credential_identity="opaque-identity",
        observed_at=_NOW,
        utilization_percent=40.0,
        remaining_percent=60.0,
        provider_reset_claim=_CLAIMED_RESET,
    )


def _confirmation_skip() -> Any:
    """One skip an EXPIRED observation's outstanding confirmation decided."""
    preflight = _module(name="_acp_candidate_preflight")
    return preflight.SkippedCandidate(
        availability_key="codex",
        candidate_key="primary",
        reason=preflight.OUTSTANDING_CONFIRMATION_SKIP,
        confirmation_observation_ids=(_OBSERVATION_ID,),
    )


def _hold_skip(*, reason_attribute: str) -> Any:
    """One skip a DURABLE record decided, typed or legacy, as the filter writes it."""
    preflight = _module(name="_acp_candidate_preflight")
    return preflight.SkippedCandidate(
        availability_key="codex",
        candidate_key="fallback",
        reason=getattr(preflight, reason_attribute),
        cause="quota",
        scope=_DOMAIN,
        hold_key="codex",
    )


def _live_hold() -> Any:
    records = _module(name="_acp_hold_records")
    return records.AcpAvailabilityHold(
        schema_version=1,
        observation_id="live-observation",
        scope=_DOMAIN,
        hold_key="codex",
        candidate_key=None,
        cause="quota",
        occurred_at=_NOW,
        expires_at=_HOLD_EXPIRY,
    )


def _verdict(*, skipped: tuple[Any, ...], assessments: tuple[Any, ...]) -> Any:
    preflight = _module(name="_acp_candidate_preflight")
    node = preflight.NodePreflight(
        node="implement",
        enabled=True,
        candidates=(),
        skipped=skipped,
        assessments=assessments,
    )
    return _module(name="_acp_preflight_verdict").AcpPreflightVerdict(
        fallback_enabled=True,
        nodes=(node,),
        success_critical=("implement",),
        admission_required=("implement",),
        exhausted=("implement",),
    )


def _wait(*, verdict: Any, holds: tuple[Any, ...] = ()) -> Any:
    return _module(name="_acp_availability_wait").availability_wait(
        verdict=verdict,
        holds=holds,
        now_iso=_NOW,
        reprobe_interval_seconds=_INTERVAL,
    )


def test_a_confirmation_emptied_node_waits_the_cadence_and_records_the_claim() -> None:
    """The cadence schedules it; the provider's instant is provenance only."""
    preflight = _module(name="_acp_candidate_preflight")
    reading = _reading_claiming_a_reset()
    verdict = _verdict(skipped=(_confirmation_skip(),), assessments=(reading,))

    wait = _wait(verdict=verdict)

    assert wait is not None
    assert wait.governing_condition == preflight.OUTSTANDING_CONFIRMATION_SKIP
    assert wait.node == "implement"
    assert wait.reevaluate_at == _NOW_PLUS_INTERVAL
    # The provider's own figure, which nothing may schedule, shorten or replace
    # the cadence with.
    assert wait.reevaluate_at != _CLAIMED_RESET
    # "It MUST NOT invent a hold identity or expiry": an expired observation is
    # no longer a live record, so the refusal names none.
    assert wait.holds == ()
    fields = _module(name="_acp_availability_wait").availability_wait_refusal_fields(wait=wait)
    assert fields["governing_condition"] == preflight.OUTSTANDING_CONFIRMATION_SKIP
    assert fields["scheduled_reevaluation_at"] == _NOW_PLUS_INTERVAL
    assert fields["governing_hold_observations"] == []
    # Recorded, and recorded as UNVERIFIED, which is the only thing the clause
    # permits a provider's advertised reset instant to be.
    records = _module(name="_acp_session_headroom_records")
    assert (
        records.session_headroom_reading_fields(reading=reading)["unverified_provider_reset_claim"]
        == _CLAIMED_RESET
    )


@pytest.mark.parametrize(
    ("reason_attribute", "expected_instant"),
    [("TYPED_HOLD_SKIP", _HOLD_EXPIRY), ("LEGACY_HOLD_SKIP", _NOW_PLUS_INTERVAL)],
)
def test_a_durable_hold_still_governs_a_node_that_also_owes_a_confirmation(
    reason_attribute: str, expected_instant: str
) -> None:
    """ "When no hold governs the refusal" is what ranks the confirmation below one.

    The two arms expect DIFFERENT instants, and the difference is the existing
    rule rather than a quirk of this fixture: a TYPED record carries the scope,
    key and expiry the wait matches it by, so its expiry wins, while a LEGACY
    record carries none of them and the refusal is forbidden to invent one -- so
    that arm falls to the cadence, exactly as the confirmation does. The
    governing CONDITION is therefore what the precedence decides here, and it is
    what each arm is graded on.
    """
    preflight = _module(name="_acp_candidate_preflight")
    verdict = _verdict(
        skipped=(_confirmation_skip(), _hold_skip(reason_attribute=reason_attribute)),
        assessments=(_reading_claiming_a_reset(),),
    )

    wait = _wait(verdict=verdict, holds=(_live_hold(),))

    assert wait is not None
    assert wait.governing_condition == getattr(preflight, reason_attribute)
    assert wait.reevaluate_at == expected_instant
    # Neither arm may take the provider's own figure.
    assert wait.reevaluate_at != _CLAIMED_RESET
