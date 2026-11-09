"""The durable hand-off before Scenario 184 resumes an eligible pull request."""

from __future__ import annotations

import argparse
import importlib
import inspect
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop_selection as loop_selection
from livespec_orchestrator_beads_fabro.commands._dispatcher_base_advance import (
    BaseAdvancedAfterArming,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome

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


def test_the_journaler_names_every_measurement_as_a_typed_keyword_parameter() -> None:
    module = importlib.import_module(_MODULE)
    parameters = inspect.signature(module.journal_record_file_resume).parameters

    assert not any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters.values())
    assert {"default_branch_tip", "conflicted_paths"} <= set(parameters)


def test_an_eligible_record_file_conflict_is_journaled_then_released_and_resumed() -> None:
    """Scenario 184's automatic arm does all three acts in order, once."""
    module = importlib.import_module(_MODULE)
    assert hasattr(module, "resume_record_file_conflict")
    journal = _Journal()
    events: list[tuple[str, object]] = []

    def resolve_ready(*, work_item_id: str) -> None:
        events.append(("ready", work_item_id))

    def resume(*, work_item_id: str) -> str:
        events.append(("resume", work_item_id))
        return "resumed-outcome"

    outcome = module.resume_record_file_conflict(
        journal=journal,
        work_item_id="bd-ib-mfl2qa",
        run_id="01M6W31BSSE1P8Z43EGGY9XVNF",
        pr_number=184,
        pr_head="head1111",
        default_branch_tip="base2222",
        conflicted_paths=("record.json", "notes.md"),
        resolve_ready=resolve_ready,
        resume=resume,
    )

    assert outcome == "resumed-outcome"
    assert events == [("ready", "bd-ib-mfl2qa"), ("resume", "bd-ib-mfl2qa")]
    assert journal.records[0]["stage"] == "base-advanced-record-files-resume"


def test_the_real_terminal_disposition_resumes_an_eligible_record_file_conflict(
    tmp_path: Path, monkeypatch: object
) -> None:
    """Scenario 184 reaches the shared journal, ready transition, and resume path."""
    parameters = inspect.signature(loop_selection.post_run_dispositions).parameters
    assert "resume" in parameters, (
        "the terminal disposition has no resume seam, so an eligible record-file conflict "
        "still falls through to needs-human"
    )
    journal = _Journal()
    events: list[str] = []
    monkeypatch.setattr(  # type: ignore[union-attr]
        loop_selection,
        "livespec_config_text",
        lambda **_kwargs: (
            '{"livespec-orchestrator-beads-fabro":{"dispatcher":{"record_files":'
            '[{"path":"record.json"}]}}}'
        ),
    )
    monkeypatch.setattr(  # type: ignore[union-attr]
        loop_selection,
        "write_blocked_state_and_reconcile",
        lambda **_kwargs: events.append("ready"),
    )
    outcome = DispatchOutcome(
        work_item_id="bd-ib-mfl2qa",
        status="blocked",
        stage="merge-poll",
        pr_number=184,
        merge_sha=None,
        detail="base advanced",
        fabro_run_id="01M6W31BSSE1P8Z43EGGY9XVNF",
        base_advanced=BaseAdvancedAfterArming(
            factory="petri",
            pr_head="head1111",
            default_branch_tip="base2222",
            conflicted_paths=("record.json",),
        ),
    )

    resumed = loop_selection.post_run_dispositions(
        args=argparse.Namespace(close_on_merge=False),
        repo=tmp_path,
        item=SimpleNamespace(id="bd-ib-mfl2qa"),
        outcome=outcome,
        journal=journal,
        wall_clock_seconds=1.0,
        dispatch_context_size=1,
        token_supplier=lambda: "token",
        resume=lambda *, work_item_id: events.append(f"resume:{work_item_id}") or "resumed",
    )

    assert resumed == "resumed"
    assert events == ["ready", "resume:bd-ib-mfl2qa"]
    assert journal.records[0]["stage"] == "base-advanced-record-files-resume"
