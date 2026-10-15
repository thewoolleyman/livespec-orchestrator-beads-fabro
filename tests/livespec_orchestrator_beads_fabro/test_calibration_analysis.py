"""Paired coverage for calibration advisory analysis."""

from __future__ import annotations

import json
from pathlib import Path

from livespec_orchestrator_beads_fabro.calibration_analysis import (
    analyze_calibration,
    load_calibration_records,
)


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
