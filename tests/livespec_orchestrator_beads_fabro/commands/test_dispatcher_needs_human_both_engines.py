"""A needs-human ending routes the item to `blocked` on BOTH engines.

Scenario 103 of `SPECIFICATION/scenarios.md` governs the ending; this file
binds the two DIFFERENT CHANNELS the marker arrives on, which is what the
Petri-era rebase changed.

- On the pinned 0.254 build the `needs_human` node's sentinel reaches the
  Dispatcher on the run's raw stderr, and the structured failure block carries
  nothing about it.
- On the Petri-era build (0.378.0-nightly.0, measured 2026-10-08 — research
  notes 006 and 007 of `plan/fabro-currency`) a goal-gated script node's stderr
  is folded into `conclusion.failure.detail.message` instead, and the raw
  `fabro run` stderr carries no marker at all.

Both must reach the same rest state, because the ledger valve a human answers
with is the same one either way. The Petri route works only because the failure
reader reads the nested `detail` block — before that it returned `None`, the
detail fell back to a tail of an empty stderr, and the marker reached the
routing text from neither channel. So this is the end-to-end assertion that the
unit tests beside the reader cannot make: it is the only place that says the
PARSE and the ROUTING are wired to each other.

No product change accompanies this file. The routing was delivered by the
nested-`detail` reader, and manufacturing a failing Red for behaviour that
already holds would assert a gap that does not exist; the test is here so the
wiring cannot regress silently, which is the failure mode that would otherwise
strand a run's question where no human is looking for it.
"""

from __future__ import annotations

from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_terminal import (
    fabro_run_terminal_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import NEEDS_HUMAN_MARKER
from livespec_orchestrator_beads_fabro.commands._fabro_port_failure import (
    fabro_failure_detail_from_payload,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_types import FabroInspectResult

_QUESTION = "the acceptance criteria name a scenario this slice cannot bind"
_PETRI_RUN_ID = "01M4DCSSJM6C"
_LEGACY_RUN_ID = "01M0EFZND0Z7K2SY1H21Q59GVF"


class _Command:
    """The three `FabroCommand` fields the terminal reader consumes."""

    exit_code = 1
    stdout = ""
    stderr = ""


class _Plan:
    work_item_id = "bd-ib-227cbw"
    fabro_factory_server = None


def _petri_inspect() -> FabroInspectResult:
    """A Petri-era failed-run record whose marker is ONLY in the nested detail."""
    payload: list[dict[str, Any]] = [
        {
            "run_id": _PETRI_RUN_ID,
            "status": {"kind": "failed", "reason": "node_failed"},
            "checkpoint": {},
            "conclusion": {
                "status": "failed",
                "total_retries": 0,
                "failure": {
                    "reason": "script exited with status 1",
                    "detail": {
                        "message": f"{NEEDS_HUMAN_MARKER}: {_QUESTION}\nscript exited with status 1",
                        "category": "node_failure",
                    },
                },
            },
        }
    ]
    return FabroInspectResult(
        command=_Command(),
        payload=payload,
        status_kind="failed",
        failure=fabro_failure_detail_from_payload(payload=payload),
    )


def test_the_petri_marker_in_the_nested_detail_blocks_the_item() -> None:
    outcome = fabro_run_terminal_outcome(
        outcome_type=DispatchOutcome,
        plan=_Plan(),
        run_id=_PETRI_RUN_ID,
        inspect=_petri_inspect(),
        exit_code=1,
        # Deliberately EMPTY: on this engine the marker reaches the Dispatcher
        # through the inspect payload alone, so a stderr-only reader finds
        # nothing and the item would come to rest as an ordinary failure.
        stderr="",
    )

    assert outcome is not None
    assert outcome.status == "blocked"
    assert outcome.fabro_run_id == _PETRI_RUN_ID
    assert f"resolve-blocked:{_Plan.work_item_id}:ready" in outcome.detail


def test_the_legacy_stderr_sentinel_blocks_the_item() -> None:
    outcome = fabro_run_terminal_outcome(
        outcome_type=DispatchOutcome,
        plan=_Plan(),
        run_id=_LEGACY_RUN_ID,
        # No structured failure block at all — the pinned build surfaced the
        # node's own stderr nowhere inside `inspect`.
        inspect=None,
        exit_code=1,
        stderr=f"{NEEDS_HUMAN_MARKER}: {_QUESTION}\n",
    )

    assert outcome is not None
    assert outcome.status == "blocked"
    assert outcome.fabro_run_id == _LEGACY_RUN_ID
    assert f"resolve-blocked:{_Plan.work_item_id}:ready" in outcome.detail


def test_a_failed_run_with_no_marker_on_either_channel_stays_failed() -> None:
    """The discriminator: `blocked` must mean a marker was actually read.

    Without this, a reader that routed every failed run to `blocked` would pass
    both assertions above while telling every human that every failure is a
    question for them.
    """
    payload: list[dict[str, Any]] = [
        {
            "run_id": _PETRI_RUN_ID,
            "status": {"kind": "failed", "reason": "node_failed"},
            "conclusion": {
                "failure": {
                    "reason": "script exited with status 1",
                    "detail": {
                        "message": "script exited with status 1",
                        "category": "node_failure",
                    },
                }
            },
        }
    ]
    outcome = fabro_run_terminal_outcome(
        outcome_type=DispatchOutcome,
        plan=_Plan(),
        run_id=_PETRI_RUN_ID,
        inspect=FabroInspectResult(
            command=_Command(),
            payload=payload,
            status_kind="failed",
            failure=fabro_failure_detail_from_payload(payload=payload),
        ),
        exit_code=1,
        stderr="",
    )

    assert outcome is not None
    assert outcome.status == "failed"
    assert outcome.fabro_failure_category == "node_failure"
