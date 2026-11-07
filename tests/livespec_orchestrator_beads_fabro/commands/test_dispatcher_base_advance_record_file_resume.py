"""The durable hand-off before Scenario 184 resumes an eligible pull request."""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_MODULE = f"{_PACKAGE}._dispatcher_base_advance_record_file_resume"
_SOURCE = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_base_advance_record_file_resume.py"
)


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def test_the_eligible_resume_is_journaled_with_every_required_measurement() -> None:
    assert _SOURCE.is_file(), "the record-file resume journaler does not exist yet"
    module = importlib.import_module(_MODULE)
    journal = _Journal()

    module.journal_record_file_resume(
        journal=journal,
        work_item_id="bd-ib-mfl2qa",
        run_id="01M6W31BSSE1P8Z43EGGY9XVNF",
        pr_number=184,
        pr_head="head1111",
        default_branch_tip="base2222",
        conflicted_paths=("record.json", "notes.md"),
    )

    assert journal.records == [
        {
            "stage": "base-advanced-record-files-resume",
            "work_item_id": "bd-ib-mfl2qa",
            "run_id": "01M6W31BSSE1P8Z43EGGY9XVNF",
            "pr_number": 184,
            "pr_head": "head1111",
            "default_branch_tip": "base2222",
            "conflicted_paths": ["record.json", "notes.md"],
        }
    ]
