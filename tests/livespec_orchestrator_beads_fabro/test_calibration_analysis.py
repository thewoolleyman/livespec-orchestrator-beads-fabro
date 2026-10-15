"""Paired coverage for calibration advisory analysis."""

from __future__ import annotations

import json
from pathlib import Path

from livespec_orchestrator_beads_fabro.calibration_analysis import (
    analyze_calibration,
    load_calibration_records,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_telemetry import STALL_STATUS


def test_load_calibration_records_filters_jsonl(tmp_path: Path) -> None:
    journal = tmp_path / "journal.jsonl"
    _ = journal.write_text(
        "\n".join(
            [
                json.dumps({"stage": "ignored", "acceptance_count": 1}),
                "{not-json",
                json.dumps({"stage": "calibration", "acceptance_count": 3}),
            ]
        ),
        encoding="utf-8",
    )

    assert load_calibration_records(journal_path=journal) == (
        {"stage": "calibration", "acceptance_count": 3},
    )


def test_analyze_calibration_proposes_advisory_threshold() -> None:
    records = (
        {"converged": True, "acceptance_count": 1},
        {"converged": True, "acceptance_count": 2},
        {"converged": False, "acceptance_count": 10},
        {"converged": False, "acceptance_count": 11},
    )

    proposal = analyze_calibration(records=records)

    acceptance = proposal.thresholds[0]
    assert proposal.advisory is True
    assert proposal.adopted is False
    assert proposal.total_runs == 4
    assert proposal.non_converged_runs == 2
    assert acceptance.proxy == "acceptance_count"
    assert acceptance.ceiling == 10


def test_the_declined_stall_status_is_pinned_to_the_engine_constant() -> None:
    """The status the pass spells for itself cannot drift from the engine's.

    The pass may hold no `commands.` module — that absent import is what makes
    it unable to change lifecycle state, and
    `test_calibration_analysis_repaired_proxies` asserts it structurally — so
    the stall status is spelled in `calibration_analysis` rather than imported
    from `_dispatcher_stall_telemetry`. This case is the enforcement that a
    comment cannot be: the declined record's `outcome_class` is BUILT from
    `STALL_STATUS` itself, so a local literal that no longer matches the
    constant counts a cancelled sandbox as a slice that would not converge and
    fails here.

    The converged row beside it is the control. Without it, a pass that
    declined every record would satisfy the stall half exactly as a correct one
    does, and `total_runs` would read 0 either way.
    """
    stalled: dict[str, object] = {
        "converged": False,
        "outcome_class": f"{STALL_STATUS}:fabro-run",
        "acceptance_count": 7,
    }
    converged: dict[str, object] = {
        "converged": True,
        "outcome_class": "green",
        "acceptance_count": 1,
    }

    proposal = analyze_calibration(records=(stalled, converged))

    assert (proposal.total_runs, proposal.non_converged_runs) == (1, 0)
