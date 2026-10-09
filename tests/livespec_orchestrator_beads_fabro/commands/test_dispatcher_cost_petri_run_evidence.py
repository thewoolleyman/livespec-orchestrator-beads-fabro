"""The candidate's run evidence reaches the audit record the reflection pass reads.

Plan `fabro-currency` P4 (`bd-ib-227cbw`). A dispatched run's evidence travels to
the reflection and audit paths through the `cost-gate` journal record, which the
mechanical reflection scan reads back per item: it is where the run IDENTITY and
the per-run COST are recorded for a green outcome. The Petri-era `ps --json`
record carries one more measurement the pinned build never emitted —
`wall_time_ms`, beside `total_usd_micros` (research note 006 and the P3 rider on
the work-item) — and the port dropped it on the floor, so the engine's own
wall-clock figure for a run reached nothing.

Why the engine's figure is worth carrying at all, given the dispatcher already
times its own wall clock: the trap catalogue records that a run's
`conclusion.timing.wall_time_ms` reproduces the configured node TIMEOUT to the
millisecond on a timed-out run, i.e. it is a constant stamped at finalisation
rather than a measurement — so a figure read from the run's own record has to
be recorded as what it is, and the `ps` field is the one the candidate reports
per run.

ABSENCE IS `None`, NEVER `0`. A zero wall time is a measurement, and a run that
took no time is not a thing the engine reports; manufacturing one for the pinned
build — which emits no such field at all — would put a measurement into the
audit record that no engine made.

There is no token-usage field to carry: the measured candidate key sets for
`ps`, `inspect` and `events` contain none (research note 006), so token usage
still reaches the cost path exactly as it does today, through the host OTLP
receiver's derived per-dispatch cost. What the candidate emits is identity and
cost; those are what the port carries.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_cost import gate_wave
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._fabro_port import (
    fabro_run_summaries_from_stdout,
)

_RUN_ID = "01M4DCQPCX6Z"
_WORK_ITEM_ID = "bd-ib-227cbw"
_WALL_TIME_MS = 41231
_USD_MICROS = 1250


@dataclass(kw_only=True)
class _RecordingJournal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _candidate_ps_json() -> str:
    """One `fabro ps -a --json` record as the candidate writes it."""
    record: dict[str, Any] = {
        "goal": f"Work-item: {_WORK_ITEM_ID}\nRepo: /x",
        "labels": [],
        "parent_id": None,
        "run_id": _RUN_ID,
        "source_directory": "/home/cwoolley/src",
        "start_time": "2026-10-08T12:34:14.182000000Z",
        "status": {"kind": "succeeded", "reason": "completed"},
        "total_usd_micros": _USD_MICROS,
        "wall_time_ms": _WALL_TIME_MS,
        "workflow_graph_name": "ImplementWorkItem",
        "workflow_name": "implement-work-item",
        "workflow_slug": "implement-work-item",
    }
    return json.dumps([record])


def _pinned_ps_json() -> str:
    """The pinned build's record: the reader field set, with no wall time."""
    return json.dumps(
        [
            {
                "run_id": _RUN_ID,
                "status": {"kind": "succeeded"},
                "goal": f"Work-item: {_WORK_ITEM_ID}\nRepo: /x",
                "total_usd_micros": _USD_MICROS,
            }
        ]
    )


def _green() -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=_WORK_ITEM_ID,
        status="green",
        stage="done",
        pr_number=2686,
        merge_sha="9bcd4faa",
        detail="merged, post-merge janitor green",
    )


def test_the_run_summary_carries_the_candidates_wall_time_beside_its_cost() -> None:
    summaries = fabro_run_summaries_from_stdout(stdout=_candidate_ps_json())

    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.run_id == _RUN_ID
    assert summary.total_usd_micros == _USD_MICROS
    assert getattr(summary, "wall_time_ms", None) == _WALL_TIME_MS


def test_a_pinned_run_summary_reports_an_unemitted_wall_time_as_absent() -> None:
    summaries = fabro_run_summaries_from_stdout(stdout=_pinned_ps_json())

    assert len(summaries) == 1
    assert getattr(summaries[0], "wall_time_ms", 0) is None


def test_the_cost_gate_audit_record_carries_identity_cost_and_wall_time() -> None:
    journal = _RecordingJournal()

    refusals = gate_wave(
        unattended=False,
        outcomes=(_green(),),
        ps_json=_candidate_ps_json(),
        journal=journal,
    )

    assert refusals == ()
    record = next(r for r in journal.records if r.get("stage") == "cost-gate")
    assert record["run_id"] == _RUN_ID
    assert record["work_item_id"] == _WORK_ITEM_ID
    assert record["usd_micros"] == _USD_MICROS
    assert record["wall_time_ms"] == _WALL_TIME_MS


def test_the_audit_record_reports_an_unemitted_wall_time_as_absent() -> None:
    journal = _RecordingJournal()

    _ = gate_wave(
        unattended=False,
        outcomes=(_green(),),
        ps_json=_pinned_ps_json(),
        journal=journal,
    )

    record = next(r for r in journal.records if r.get("stage") == "cost-gate")
    assert record["usd_micros"] == _USD_MICROS
    assert record["wall_time_ms"] is None
