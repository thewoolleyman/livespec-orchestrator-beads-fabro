"""Path coverage for Dispatcher auto-disposition journal records."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._store_acceptance_rework import AcceptanceFailureState
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_acceptance_rework,
    _dispatcher_admission,
    _dispatcher_completion,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_decision_journal import (
    read_auto_disposition_decisions,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import build_plan
from livespec_orchestrator_beads_fabro.commands._dispatcher_review_gate import (
    ReviewGateEmission,
    emit_review_gate_from_fabro_events,
)
from livespec_orchestrator_beads_fabro.types import WorkItem


@dataclass(kw_only=True)
class _MemoryJournal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@dataclass(frozen=True, kw_only=True)
class _AcceptancePass:
    verdict: str

    def journal_record(self, *, work_item_id: str, policy: str) -> dict[str, object]:
        return {
            "stage": "acceptance-ai-pass",
            "work_item_id": work_item_id,
            "verdict": self.verdict,
            "acceptance_policy": policy,
        }


@dataclass(kw_only=True)
class _Runner:
    stdout: str

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        _ = (argv, cwd, timeout_seconds, env)
        return CommandResult(exit_code=0, stdout=self.stdout, stderr="")


def test_auto_approve_path_journals_governing_setting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal = _MemoryJournal()
    monkeypatch.setattr(_dispatcher_admission, "store_config", lambda **_: tmp_path)
    monkeypatch.setattr(_dispatcher_admission, "update_work_item_status", lambda **_: None)

    _dispatcher_admission.admit_and_select(
        repo=tmp_path,
        items=[],
        candidates=[_item(status="pending-approval", admission_policy="auto")],
        journal=journal,
        enforce_cap=False,
    )

    _assert_auto_disposition(
        records=journal.records,
        disposition="auto-approve",
        governing_settings=("auto_approve_ready",),
    )


def test_ai_auto_accept_path_journals_governing_setting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal = _MemoryJournal()
    item = _item(acceptance_policy="ai-only")
    monkeypatch.setattr(_dispatcher_completion, "store_config", lambda **_: tmp_path)
    monkeypatch.setattr(_dispatcher_completion, "update_work_item_status", lambda **_: None)
    monkeypatch.setattr(_dispatcher_completion, "_close_item", lambda **_: None)
    monkeypatch.setattr(
        _dispatcher_completion,
        "run_acceptance_pass",
        lambda **_: _AcceptancePass(verdict="PASS"),
    )

    _dispatcher_completion.complete_and_accept(
        repo=tmp_path,
        item=item,
        outcome=_outcome(item_id=item.id),
        journal=journal,
    )

    _assert_auto_disposition(
        records=journal.records,
        disposition="ai-auto-accept",
        governing_settings=("acceptance_mode",),
    )


def test_ai_fail_auto_rework_path_journals_governing_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal_path = tmp_path / "journal.jsonl"
    monkeypatch.setattr(_dispatcher_acceptance_rework, "store_config", lambda **_: tmp_path)
    monkeypatch.setattr(_dispatcher_acceptance_rework, "update_work_item_status", lambda **_: None)
    monkeypatch.setattr(
        _dispatcher_acceptance_rework,
        "update_acceptance_failed_ai_passes",
        lambda **_: AcceptanceFailureState(failed_ai_passes=1, raw_labels=()),
    )

    _dispatcher_acceptance_rework.rework_or_block_failed_acceptance(
        repo=tmp_path,
        item=_item(acceptance_policy="ai-then-human"),
        policy="ai-then-human",
        journal=JournalFile(path=journal_path),
    )

    _assert_auto_disposition(
        records=read_auto_disposition_decisions(journal_path=journal_path),
        disposition="ai-fail-auto-rework",
        governing_settings=("acceptance_mode", "acceptance_rework_cap"),
    )


def test_acceptance_cap_exceeded_path_journals_governing_setting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal_path = tmp_path / "journal.jsonl"
    monkeypatch.setattr(_dispatcher_acceptance_rework, "store_config", lambda **_: tmp_path)
    monkeypatch.setattr(
        _dispatcher_acceptance_rework,
        "update_work_item_blocked_state",
        lambda **_: None,
    )
    monkeypatch.setattr(
        _dispatcher_acceptance_rework,
        "update_acceptance_failed_ai_passes",
        lambda **_: AcceptanceFailureState(failed_ai_passes=3, raw_labels=()),
    )

    _dispatcher_acceptance_rework.rework_or_block_failed_acceptance(
        repo=tmp_path,
        item=_item(acceptance_policy="ai-only"),
        policy="ai-only",
        journal=JournalFile(path=journal_path),
    )

    _assert_auto_disposition(
        records=read_auto_disposition_decisions(journal_path=journal_path),
        disposition="cap-exceeded-escalation",
        governing_settings=("acceptance_rework_cap",),
    )


def test_ship_on_cap_path_journals_governing_settings(tmp_path: Path) -> None:
    journal = _MemoryJournal()

    emit_review_gate_from_fabro_events(
        emission=ReviewGateEmission(
            plan=build_plan(
                repo=tmp_path,
                work_item_id="bd-ib-item",
                workflow_toml=tmp_path / "workflow.toml",
                goal_file=tmp_path / "goal.md",
                fabro_bin="fabro",
                janitor=None,
                janitor_checkout=tmp_path / "janitor",
                merge_on_review_cap=True,
            ),
            runner=_Runner(stdout=_review_ship_on_cap_events()),
            journal=journal,
            spans_path=tmp_path / "spans.jsonl",
            work_item_id="bd-ib-item",
            dispatch_id="dispatch-1",
            run_id="run-1",
        )
    )

    _assert_auto_disposition(
        records=journal.records,
        disposition="ship-on-cap",
        governing_settings=("merge_on_review_cap", "review_fix_cap"),
    )


def test_read_auto_disposition_decisions_skips_missing_and_malformed_lines(tmp_path: Path) -> None:
    assert read_auto_disposition_decisions(journal_path=tmp_path / "missing.jsonl") == ()
    journal_path = tmp_path / "journal.jsonl"
    expected = {
        "stage": "auto-disposition",
        "work_item_id": "bd-ib-item",
        "disposition": "auto-approve",
        "governing_settings": ["auto_approve_ready"],
    }
    journal_path.write_text(
        "not-json\n" + json.dumps(["not", "an", "object"]) + "\n" + json.dumps(expected),
        encoding="utf-8",
    )

    assert read_auto_disposition_decisions(journal_path=journal_path) == (expected,)


def test_review_cap_exceeded_path_journals_governing_setting(tmp_path: Path) -> None:
    journal = _MemoryJournal()

    emit_review_gate_from_fabro_events(
        emission=ReviewGateEmission(
            plan=build_plan(
                repo=tmp_path,
                work_item_id="bd-ib-item",
                workflow_toml=tmp_path / "workflow.toml",
                goal_file=tmp_path / "goal.md",
                fabro_bin="fabro",
                janitor=None,
                janitor_checkout=tmp_path / "janitor",
                merge_on_review_cap=False,
            ),
            runner=_Runner(stdout=_review_cap_exceeded_events()),
            journal=journal,
            spans_path=tmp_path / "spans.jsonl",
            work_item_id="bd-ib-item",
            dispatch_id="dispatch-1",
            run_id="run-1",
        )
    )

    _assert_auto_disposition(
        records=journal.records,
        disposition="cap-exceeded-escalation",
        governing_settings=("review_fix_cap",),
    )


def _assert_auto_disposition(
    *,
    records: list[dict[str, object]] | tuple[dict[str, object], ...],
    disposition: str,
    governing_settings: tuple[str, ...],
) -> None:
    matches = [
        record
        for record in records
        if record.get("stage") == "auto-disposition" and record.get("disposition") == disposition
    ]
    assert matches
    assert matches[-1]["work_item_id"]
    assert matches[-1]["governing_settings"] == list(governing_settings)


def _item(**overrides: object) -> WorkItem:
    fields: dict[str, object] = {
        "id": "bd-ib-item",
        "type": "task",
        "status": "ready",
        "title": "Task",
        "description": "Do it.",
        "origin": "freeform",
        "gap_id": None,
        "rank": "a1",
        "assignee": None,
        "depends_on": (),
        "captured_at": "2026-07-16T00:00:00Z",
        "resolution": None,
        "reason": None,
        "audit": None,
        "superseded_by": None,
        "admission_policy": None,
        "acceptance_policy": None,
    }
    fields.update(overrides)
    return WorkItem(**fields)


def _outcome(*, item_id: str) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=item_id,
        status="green",
        stage="done",
        pr_number=1,
        merge_sha="abc123",
        detail="merged",
    )


def _review_ship_on_cap_events() -> str:
    return "\n".join(
        json.dumps(event)
        for event in (
            _edge(from_node="review", to_node="review_fix", reason="preferred_label"),
            _edge(from_node="review", to_node="review_fix", reason="preferred_label"),
            _edge(from_node="review", to_node="review_fix", reason="preferred_label"),
            _edge(from_node="review", to_node="pr", reason="unconditional"),
        )
    )


def _review_cap_exceeded_events() -> str:
    return "\n".join(
        json.dumps(event)
        for event in (
            _edge(from_node="review", to_node="review_fix", reason="preferred_label"),
            _edge(from_node="review", to_node="review_fix", reason="preferred_label"),
            _edge(from_node="review", to_node="review_fix", reason="preferred_label"),
            _edge(from_node="review", to_node="blocked", reason="unconditional"),
        )
    )


def _edge(*, from_node: str, to_node: str, reason: str) -> dict[str, object]:
    return {
        "event": "edge.selected",
        "properties": {
            "from_node": from_node,
            "to_node": to_node,
            "reason": reason,
        },
    }
