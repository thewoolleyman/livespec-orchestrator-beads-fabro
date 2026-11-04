"""Tests for the stall-watchdog cancellation telemetry signal.

The signal under test is derived from the terminal outcome the PRODUCTION
watchdog-cancel path builds (`_dispatcher_engine_journal.stalled_outcome`),
not from a hand-written status string, so a rename on either side fails
here rather than silently emitting nothing. The emitted attribute
vocabulary is asserted against `_otel_scrub.ATTRIBUTE_ALLOWLIST` because
an attribute missing from that allowlist is dropped by the enrich stage
before egress — a span that ships with its payload stripped is
indistinguishable, downstream, from a signal that was never emitted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_journal import stalled_outcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_cancel_comments import (
    release_comment,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_telemetry import (
    STALL_CAUSE_ZERO_OUTPUT,
    STALL_STATUS,
    UNKNOWN_RUN_ID,
    StallSignal,
    stall_attributes,
    stall_signals,
)
from livespec_orchestrator_beads_fabro.commands._otel_scrub import ATTRIBUTE_ALLOWLIST


@dataclass(frozen=True, kw_only=True)
class _PlanStub:
    """The one `DispatchPlan` field `stalled_outcome` reads."""

    work_item_id: str


def _watchdog_cancelled(*, item_id: str = "bd-a", run_id: str = "01M1RUN") -> DispatchOutcome:
    """The outcome the production watchdog-cancel path produces."""
    return stalled_outcome(
        outcome_type=DispatchOutcome,
        plan=cast("DispatchPlan", _PlanStub(work_item_id=item_id)),
        run_id=run_id,
    )


def _green(*, item_id: str = "bd-b") -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=item_id,
        status="green",
        stage="done",
        pr_number=7,
        merge_sha="deadbeef",
        detail="merged",
    )


def test_stall_signals_selects_only_watchdog_cancelled_outcomes() -> None:
    """A wave's stall signals name the cancelled run and nothing else."""
    outcomes = (_green(), _watchdog_cancelled(item_id="bd-a", run_id="01M1RUN"))

    signals = stall_signals(outcomes=outcomes)

    assert signals == (
        StallSignal(
            work_item_id="bd-a",
            run_id="01M1RUN",
            stage="fabro-run",
            cause=STALL_CAUSE_ZERO_OUTPUT,
        ),
    )


def test_stall_signals_recognises_the_production_stall_status() -> None:
    """The status matched is the one the production builder writes."""
    assert _watchdog_cancelled().status == STALL_STATUS


def test_stall_signals_prefer_an_observed_cause_over_the_default() -> None:
    """A more specific observed cause is carried instead of the default."""
    cancelled = _watchdog_cancelled()
    observed = DispatchOutcome(
        work_item_id=cancelled.work_item_id,
        status=cancelled.status,
        stage=cancelled.stage,
        pr_number=None,
        merge_sha=None,
        detail=cancelled.detail,
        fabro_run_id=cancelled.fabro_run_id,
        fabro_failure_cause="  acp turn produced no output  ",
    )

    signals = stall_signals(outcomes=(observed,))

    assert signals[0].cause == "acp turn produced no output"


def test_stall_signals_mark_a_run_id_the_outcome_cannot_name() -> None:
    """A stall with no run id still emits, under the legible placeholder."""
    unnamed = DispatchOutcome(
        work_item_id="bd-a",
        status=STALL_STATUS,
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail="stalled",
        fabro_run_id=None,
    )

    assert stall_signals(outcomes=(unnamed,))[0].run_id == UNKNOWN_RUN_ID


def test_stall_attributes_carry_the_run_id_and_cause_through_the_allowlist() -> None:
    """Every emitted attribute names the incident AND survives the scrub."""
    attributes = stall_attributes(
        signal=StallSignal(
            work_item_id="bd-a",
            run_id="01M1RUN",
            stage="fabro-run",
            cause=STALL_CAUSE_ZERO_OUTPUT,
        )
    )

    assert attributes == {
        "work.item.id": "bd-a",
        "fabro.run_id": "01M1RUN",
        "livespec.stage": "fabro-run",
        "livespec.outcome": STALL_STATUS,
        "livespec.stall.cause": STALL_CAUSE_ZERO_OUTPUT,
    }
    assert set(attributes) <= ATTRIBUTE_ALLOWLIST


def test_stall_outputs_name_the_server_cancel_route_and_retained_record() -> None:
    detail = _watchdog_cancelled().detail
    comment = release_comment(item_id="bd-a", row={"run_id": "01RUN", "factory": "petri"})

    assert "factory server's cancel route" in detail
    assert "record on the factory" in detail
    assert "factory server's cancel route" in comment
    assert "record is retained on the factory" in comment
