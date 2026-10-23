"""With no candidate left eligible, the next look is the REPROBE CADENCE.

Binds `SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" -> "Availability is re-confirmed after expiry": "If no candidate
remains eligible, the Dispatcher MUST retry automatically after
`dispatcher.credential_reprobe_interval_seconds`; it MUST NOT busy-loop or
require a human." Scenario 60's "A scoped record expires, a completed
confirmation turn re-confirms the candidate, and admission resumes" is the
happy half; this is the half where no turn confirmed anything.

THE CADENCE IS ASSERTED AS ARITHMETIC OVER THE CONFIGURED FIGURE, not as "some
later instant". An expired observation has NO expiry left to schedule from --
that is what expiry means -- so the one wrong answer available is to schedule
from the record's own already-passed `expires_at`, which every later pass reads
as already due. That is the busy loop the clause names, and only comparing
against `now + interval` refuses it.

AND THE REFUSAL MUST SAY WHETHER A TURN WAS ACTUALLY RUN. "When no hold governs
the refusal, it MUST name the outstanding confirmation ... without inventing a
hold identity or expiry" -- which the governing condition already does. What it
does not say is whether the Dispatcher ASKED: a node emptied because no probe
seam was supplied and a node emptied because every probe was TERMINATED are
different operational states with different remedies, and both render as "a
confirmation is outstanding". So the ending each turn reached is reported
beside the condition, and the no-seam case is its control: an absent ending
must stay absent rather than being filled in with a plausible one.

Everything is HERMETIC: the verdict is built in memory and nothing reaches a
factory, a provider or a credential.
"""

from __future__ import annotations

import importlib
from datetime import timedelta
from typing import Any

import pytest

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

_NOW = "2026-10-20T12:30:00Z"
_INTERVAL = 900


def _wait_module() -> Any:
    """Import the availability wait, proving it reports a turn's ending."""
    module = importlib.import_module(f"{_PACKAGE}._acp_availability_wait")
    assert hasattr(
        module, "CONFIRMATION_ENDINGS_FIELD"
    ), "the availability wait does not report confirmation-turn endings yet"
    return module


def _verdict(*, conditions: tuple[str | None, ...]) -> Any:
    """An exhausted verdict whose node was emptied by owed confirmations alone."""
    skips = importlib.import_module(f"{_PACKAGE}._acp_preflight_skips")
    verdicts = importlib.import_module(f"{_PACKAGE}._acp_preflight_verdict")
    skipped = tuple(
        skips.SkippedCandidate(
            availability_key="anthropic",
            candidate_key=f"candidate-{index}",
            reason=skips.OUTSTANDING_CONFIRMATION_SKIP,
            condition=condition,
            confirmation_observation_ids=(f"acp-{index}",),
        )
        for index, condition in enumerate(conditions)
    )
    node = skips.NodePreflight(node="implement", enabled=True, candidates=(), skipped=skipped)
    return verdicts.AcpPreflightVerdict(
        fallback_enabled=True,
        nodes=(node,),
        admission_required=("implement",),
        exhausted=("implement",),
    )


def _scheduled(*, module: Any, verdict: Any) -> Any:
    return module.availability_wait(
        verdict=verdict, holds=(), now_iso=_NOW, reprobe_interval_seconds=_INTERVAL
    )


def test_a_chain_emptied_by_unconfirmed_turns_is_reevaluated_after_the_cadence() -> None:
    """The cadence, as arithmetic: an expired record has no expiry to schedule from."""
    module = _wait_module()
    outcome = importlib.import_module(f"{_PACKAGE}._acp_availability_probe_outcome")
    skips = importlib.import_module(f"{_PACKAGE}._acp_preflight_skips")
    hold_records = importlib.import_module(f"{_PACKAGE}._acp_hold_records")

    wait = _scheduled(
        module=module,
        verdict=_verdict(conditions=(outcome.PROBE_TIMED_OUT, outcome.PROBE_REFUSED)),
    )

    assert wait is not None
    expected = hold_records.parse_hold_instant(text=_NOW)
    assert expected is not None
    assert wait.reevaluate_at == (expected + timedelta(seconds=_INTERVAL)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    assert wait.governing_condition == skips.OUTSTANDING_CONFIRMATION_SKIP
    # No hold governs it, and none is invented.
    assert wait.holds == ()


def test_the_refusal_names_the_ending_each_confirmation_turn_reached() -> None:
    """A node nobody probed and a node whose probes were terminated differ."""
    module = _wait_module()
    outcome = importlib.import_module(f"{_PACKAGE}._acp_availability_probe_outcome")

    wait = _scheduled(
        module=module,
        verdict=_verdict(conditions=(outcome.PROBE_TIMED_OUT, outcome.PROBE_REFUSED)),
    )

    assert wait is not None
    assert list(wait.confirmation_endings) == [
        outcome.PROBE_TIMED_OUT,
        outcome.PROBE_REFUSED,
    ]
    fields = module.availability_wait_refusal_fields(wait=wait)
    assert fields[module.CONFIRMATION_ENDINGS_FIELD] == [
        outcome.PROBE_TIMED_OUT,
        outcome.PROBE_REFUSED,
    ]


def test_a_node_no_turn_was_run_for_names_no_ending_at_all() -> None:
    """The control: an absent ending stays absent rather than being filled in."""
    module = _wait_module()

    wait = _scheduled(module=module, verdict=_verdict(conditions=(None, None)))

    assert wait is not None
    assert wait.confirmation_endings == ()
    fields = module.availability_wait_refusal_fields(wait=wait)
    assert fields[module.CONFIRMATION_ENDINGS_FIELD] == []
    # The cadence is unchanged by whether a turn was run.
    assert wait.reevaluate_at == "2026-10-20T12:45:00Z"


def test_one_ending_is_reported_once_however_many_candidates_reached_it() -> None:
    """Three terminated probes are one condition, not three rows of the same word."""
    module = _wait_module()
    outcome = importlib.import_module(f"{_PACKAGE}._acp_availability_probe_outcome")

    wait = _scheduled(
        module=module,
        verdict=_verdict(
            conditions=(
                outcome.PROBE_TIMED_OUT,
                outcome.PROBE_TIMED_OUT,
                outcome.PROBE_SESSION_CREATED,
            )
        ),
    )

    assert wait is not None
    assert list(wait.confirmation_endings) == [
        outcome.PROBE_TIMED_OUT,
        outcome.PROBE_SESSION_CREATED,
    ]


def test_a_live_hold_still_governs_and_still_schedules_at_its_own_expiry() -> None:
    """The control for the cadence: a LIVE record has an expiry, so it wins."""
    module = _wait_module()
    skips = importlib.import_module(f"{_PACKAGE}._acp_preflight_skips")
    verdicts = importlib.import_module(f"{_PACKAGE}._acp_preflight_verdict")
    classifier = importlib.import_module(f"{_PACKAGE}._acp_failure_classifier")
    hold_records = importlib.import_module(f"{_PACKAGE}._acp_hold_records")

    built = hold_records.hold_observation_record(
        failure=classifier.AcpAvailabilityFailure(
            cause="quota",
            scope="availability-domain",
            hold_key="anthropic",
            availability_key="anthropic",
            candidate_key=None,
            source="protocol.message",
        ),
        evidence_kind="candidate-attempt",
        evidence_id="hp:01MRUN:implement",
        occurred_at="2026-10-20T12:28:00Z",
        work_item_id="bd-ib-n3pzcl",
        node="implement",
    )
    assert isinstance(built, dict)
    live = hold_records.parse_hold_record(record=built)
    assert not isinstance(live, str), live

    node = skips.NodePreflight(
        node="implement",
        enabled=True,
        candidates=(),
        skipped=(
            skips.SkippedCandidate(
                availability_key="anthropic",
                candidate_key="claude-opus-5-high",
                reason=skips.TYPED_HOLD_SKIP,
                cause="quota",
                scope="availability-domain",
                hold_key="anthropic",
            ),
        ),
    )
    wait = module.availability_wait(
        verdict=verdicts.AcpPreflightVerdict(
            fallback_enabled=True,
            nodes=(node,),
            admission_required=("implement",),
            exhausted=("implement",),
        ),
        holds=(live,),
        now_iso=_NOW,
        reprobe_interval_seconds=_INTERVAL,
    )

    assert wait is not None
    assert wait.governing_condition == skips.TYPED_HOLD_SKIP
    assert wait.reevaluate_at == live.expires_at
    assert wait.reevaluate_at != "2026-10-20T12:45:00Z"
    assert wait.confirmation_endings == ()


@pytest.mark.parametrize("interval", [60, 900, 3600])
def test_the_cadence_is_the_configured_figure_and_not_a_constant(interval: int) -> None:
    """Three configured intervals must produce three different instants."""
    module = _wait_module()
    outcome = importlib.import_module(f"{_PACKAGE}._acp_availability_probe_outcome")

    wait = module.availability_wait(
        verdict=_verdict(conditions=(outcome.PROBE_TIMED_OUT,)),
        holds=(),
        now_iso=_NOW,
        reprobe_interval_seconds=interval,
    )

    assert wait is not None
    hold_records = importlib.import_module(f"{_PACKAGE}._acp_hold_records")
    scheduled = hold_records.parse_hold_instant(text=wait.reevaluate_at)
    now = hold_records.parse_hold_instant(text=_NOW)
    assert scheduled is not None
    assert now is not None
    assert int((scheduled - now).total_seconds()) == interval
    assert module.availability_wait_delay_seconds(wait=wait, now_iso=_NOW) == interval
