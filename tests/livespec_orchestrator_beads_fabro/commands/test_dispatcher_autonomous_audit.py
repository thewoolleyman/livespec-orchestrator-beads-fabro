"""Unit coverage for the autonomous-mode per-decision audit record + read surface (S2).

Covers `livespec_orchestrator_beads_fabro.commands._dispatcher_autonomous_audit`,
the published per-decision audit CONTRACT for full autonomous mode: the journal
record builder every decision stage calls (no auto-resolution may be silent)
and the fail-open read surface the Control-Plane console reads each
auto-resolution and each truly-unresolvable escalation from.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_autonomous_audit import (
    AUTONOMOUS_DECISION_STAGE,
    AutonomousAudit,
    AutonomousDecision,
    autonomous_decision_journal_record,
    read_autonomous_decisions,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile

# ---------------------------------------------------------------------------
# autonomous_decision_journal_record — the record contract
# ---------------------------------------------------------------------------


def test_record_carries_stage_and_all_fields() -> None:
    record = autonomous_decision_journal_record(
        work_item_id="bd-ib-9",
        gate="approve",
        decision="auto-approved manual admission",
        disposition="auto-resolved",
    )
    assert record == {
        "stage": AUTONOMOUS_DECISION_STAGE,
        "work_item_id": "bd-ib-9",
        "gate": "approve",
        "decision": "auto-approved manual admission",
        "disposition": "auto-resolved",
    }


def test_record_escalated_disposition() -> None:
    record = autonomous_decision_journal_record(
        work_item_id="bd-ib-9",
        gate="needs-human",
        decision="left for human",
        disposition="escalated",
    )
    assert record["disposition"] == "escalated"
    assert record["gate"] == "needs-human"


def test_record_rejects_unknown_gate() -> None:
    with pytest.raises(ValueError, match="unknown gate"):
        _ = autonomous_decision_journal_record(
            work_item_id="bd-ib-9", gate="admit", decision="x", disposition="auto-resolved"
        )


def test_record_rejects_unknown_disposition() -> None:
    with pytest.raises(ValueError, match="unknown disposition"):
        _ = autonomous_decision_journal_record(
            work_item_id="bd-ib-9", gate="approve", decision="x", disposition="maybe"
        )


# ---------------------------------------------------------------------------
# read_autonomous_decisions — the published read surface (fail-open)
# ---------------------------------------------------------------------------


def test_read_missing_journal_is_empty(tmp_path: Path) -> None:
    audit = read_autonomous_decisions(journal_path=tmp_path / "absent.jsonl")
    assert audit == AutonomousAudit(auto_resolutions=(), escalations=())


def test_read_unreadable_journal_fails_open(tmp_path: Path) -> None:
    # An exists-but-unreadable journal path — here a directory in the file's
    # place, so `read_text` raises `IsADirectoryError` (an `OSError`) — fails
    # open to an empty audit rather than raising, honoring the docstring.
    journal_path = tmp_path / "journal.jsonl"
    journal_path.mkdir()
    audit = read_autonomous_decisions(journal_path=journal_path)
    assert audit == AutonomousAudit(auto_resolutions=(), escalations=())


def test_read_round_trips_and_splits_by_disposition(tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.jsonl"
    journal = JournalFile(path=journal_path)
    journal.append(
        record=autonomous_decision_journal_record(
            work_item_id="bd-ib-1",
            gate="approve",
            decision="auto-approved",
            disposition="auto-resolved",
        )
    )
    journal.append(
        record=autonomous_decision_journal_record(
            work_item_id="bd-ib-2",
            gate="acceptance",
            decision="ai-accepted",
            disposition="auto-resolved",
        )
    )
    journal.append(
        record=autonomous_decision_journal_record(
            work_item_id="bd-ib-3",
            gate="needs-human",
            decision="left for human",
            disposition="escalated",
        )
    )

    audit = read_autonomous_decisions(journal_path=journal_path)

    assert [d.work_item_id for d in audit.auto_resolutions] == ["bd-ib-1", "bd-ib-2"]
    assert audit.auto_resolutions[0].gate == "approve"
    assert audit.escalations == (
        AutonomousDecision(
            work_item_id="bd-ib-3",
            gate="needs-human",
            decision="left for human",
            disposition="escalated",
        ),
    )


def test_read_ignores_other_stages_and_malformed_lines(tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.jsonl"
    lines = [
        '{"stage": "autonomous-armed", "work_item_id": "x"}',  # S1 arming record, not a decision
        '{"stage": "calibration", "work_item_id": "y"}',  # calibration record
        "not json at all",  # malformed JSON
        '["a", "list"]',  # valid JSON but not an object
        # an autonomous-decision record with an out-of-range gate is skipped:
        '{"stage": "autonomous-decision", "work_item_id": "z", "gate": "bogus", '
        '"decision": "d", "disposition": "auto-resolved"}',
        # the one valid decision record:
        '{"stage": "autonomous-decision", "work_item_id": "ok", "gate": "approve", '
        '"decision": "d", "disposition": "auto-resolved"}',
    ]
    _ = journal_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    audit = read_autonomous_decisions(journal_path=journal_path)

    assert [d.work_item_id for d in audit.auto_resolutions] == ["ok"]
    assert audit.escalations == ()
