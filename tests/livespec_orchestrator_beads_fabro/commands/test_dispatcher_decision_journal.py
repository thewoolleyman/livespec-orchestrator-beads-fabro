"""Tests for the Dispatcher auto-disposition decision journal surface."""

from __future__ import annotations

import importlib
import json
from pathlib import Path


def test_auto_disposition_journal_records_name_governing_settings(tmp_path: Path) -> None:
    module_path = (
        Path.cwd()
        / ".claude-plugin"
        / "scripts"
        / "livespec_orchestrator_beads_fabro"
        / "commands"
        / "_dispatcher_decision_journal.py"
    )
    assert module_path.is_file()
    journal = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_decision_journal"
    )

    records = [
        journal.auto_disposition_journal_record(
            work_item_id=f"bd-ib-{index}",
            disposition=disposition,
            governing_settings=settings,
        )
        for index, (disposition, settings) in enumerate(
            (
                ("auto-approve", ("auto_approve_ready",)),
                ("ai-auto-accept", ("acceptance_mode",)),
                (
                    "ai-fail-auto-rework",
                    ("acceptance_mode", "acceptance_rework_cap"),
                ),
                ("ship-on-cap", ("merge_on_review_cap", "review_fix_cap")),
                ("cap-exceeded-escalation", ("acceptance_rework_cap",)),
            ),
            start=1,
        )
    ]

    for record in records:
        assert record["stage"] == "auto-disposition"
        assert record["work_item_id"]
        assert record["disposition"]
        assert record["governing_settings"]

    journal_path = tmp_path / "journal.jsonl"
    journal_path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )

    assert journal.read_auto_disposition_decisions(journal_path=journal_path) == tuple(records)
