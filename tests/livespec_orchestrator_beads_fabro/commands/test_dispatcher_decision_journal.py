"""Regression coverage for Dispatcher auto-disposition journal records."""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro.commands import _dispatcher_completion
from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_rework import (
    rework_or_block_failed_acceptance,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_admission import admit_and_select
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan_build import build_plan
from livespec_orchestrator_beads_fabro.commands._dispatcher_review_gate import (
    ReviewGateEmission,
    emit_review_gate_from_fabro_events,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_MODULE = "livespec_orchestrator_beads_fabro.commands." "_dispatcher_decision_journal"


def test_successor_decision_journal_module_exists() -> None:
    module_path = (
        Path(".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands")
        / "_dispatcher_decision_journal.py"
    )
    assert module_path.is_file()
    module = importlib.import_module(_MODULE)
    assert hasattr(module, "dispatcher_decision_journal_record")
    assert hasattr(module, "read_dispatcher_decisions")


@pytest.mark.parametrize(
    ("stage", "disposition", "settings"),
    [
        ("ledger-approve", "auto-approve", ("auto_approve_ready",)),
        ("ledger-accept", "ai-auto-accept", ("acceptance_mode",)),
        (
            "acceptance-auto-rework",
            "ai-fail-auto-rework",
            ("acceptance_mode", "acceptance_rework_cap"),
        ),
        (
            "review-gate-ship-on-cap",
            "ship-on-cap",
            ("merge_on_review_cap", "review_fix_cap"),
        ),
        (
            "acceptance-rework-cap-exceeded",
            "cap-exceeded-escalation",
            ("acceptance_rework_cap",),
        ),
    ],
)
def test_every_auto_disposition_record_names_governing_settings(
    stage: str,
    disposition: str,
    settings: tuple[str, ...],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    journal = JournalFile(path=repo / f"{stage}.jsonl")

    if stage == "ledger-approve":
        _drive_auto_approve(repo=repo, journal=journal)
    elif stage == "ledger-accept":
        _drive_ai_auto_accept(repo=repo, journal=journal, monkeypatch=monkeypatch)
    elif stage == "acceptance-auto-rework":
        _drive_ai_fail_auto_rework(repo=repo, journal=journal)
    elif stage == "review-gate-ship-on-cap":
        _drive_ship_on_cap(repo=repo, journal=journal)
    else:
        _drive_cap_exceeded_escalation(repo=repo, journal=journal)

    records = _journal_records(path=journal.path)
    matching = [record for record in records if record.get("stage") == stage]
    assert matching, f"{stage} emitted no journal record"
    record = matching[-1]
    assert record["work_item_id"] == "bd-ib-decision"
    assert record["disposition"] == disposition
    assert tuple(record["governing_settings"]) == settings


def test_read_dispatcher_decisions_exposes_flat_records(tmp_path: Path) -> None:
    module = importlib.import_module(_MODULE)
    journal = tmp_path / "journal.jsonl"
    journal.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "stage": "ledger-approve",
                        "work_item_id": "bd-ib-decision",
                        "disposition": "auto-approve",
                        "governing_settings": ["auto_approve_ready"],
                    }
                ),
                "{not-json",
                json.dumps({"stage": "unrelated"}),
            ]
        ),
        encoding="utf-8",
    )

    assert module.read_dispatcher_decisions(journal_path=journal) == (
        {
            "stage": "ledger-approve",
            "work_item_id": "bd-ib-decision",
            "disposition": "auto-approve",
            "governing_settings": ["auto_approve_ready"],
        },
    )


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {"prefix": "bd-ib"},
                    "dispatcher": {
                        "auto_approve_ready": True,
                        "acceptance_mode": "ai-only",
                        "acceptance_rework_cap": 1,
                        "merge_on_review_cap": True,
                        "review_fix_cap": 3,
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    return repo


def _item(
    *,
    status: str = "ready",
    acceptance_policy: str | None = None,
    admission_policy: str | None = None,
) -> WorkItem:
    return WorkItem(
        id="bd-ib-decision",
        type="task",
        status=status,
        title="Decision journal",
        description="Exercise an auto-disposition.",
        origin="freeform",
        gap_id=None,
        rank="a1",
        assignee=None,
        depends_on=(),
        captured_at="2026-07-16T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy=admission_policy,
        acceptance_policy=acceptance_policy,
    )


def _drive_auto_approve(*, repo: Path, journal: JournalFile) -> None:
    item = _item(status="pending-approval")
    append_work_item(path=_config(), item=item)
    _ = admit_and_select(
        repo=repo,
        items=[item],
        candidates=[item],
        journal=journal,
        enforce_cap=True,
    )


def _drive_ai_auto_accept(
    *, repo: Path, journal: JournalFile, monkeypatch: pytest.MonkeyPatch
) -> None:
    item = _item(acceptance_policy="ai-only")
    append_work_item(path=_config(), item=item)
    monkeypatch.setattr(
        _dispatcher_completion,
        "run_acceptance_pass",
        lambda **_: _AcceptancePass(verdict="PASS"),
    )
    _dispatcher_completion.complete_and_accept(
        repo=repo,
        item=item,
        outcome=_green_outcome(item_id=item.id),
        journal=journal,
    )


def _drive_ai_fail_auto_rework(*, repo: Path, journal: JournalFile) -> None:
    item = _item(acceptance_policy="ai-then-human")
    append_work_item(path=_config(), item=item)
    rework_or_block_failed_acceptance(repo=repo, item=item, policy="ai-then-human", journal=journal)


def _drive_cap_exceeded_escalation(*, repo: Path, journal: JournalFile) -> None:
    item = _item(acceptance_policy="ai-only")
    append_work_item(path=_config(), item=item)
    make_beads_client(config=_config()).update_issue(
        issue_id=item.id,
        add_labels=["acceptance-rework-cap:1"],
    )
    rework_or_block_failed_acceptance(repo=repo, item=item, policy="ai-only", journal=journal)
    rework_or_block_failed_acceptance(repo=repo, item=item, policy="ai-only", journal=journal)


def _drive_ship_on_cap(*, repo: Path, journal: JournalFile) -> None:
    plan = build_plan(
        repo=repo,
        work_item_id="bd-ib-decision",
        workflow_toml=repo / "workflow.fabro",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=repo / "janitor",
    )
    emit_review_gate_from_fabro_events(
        emission=ReviewGateEmission(
            plan=plan,
            runner=_ReviewRunner(),
            journal=journal,
            spans_path=repo / "spans.jsonl",
            work_item_id="bd-ib-decision",
            dispatch_id="dispatch-1",
            run_id="run-1",
        )
    )


def _green_outcome(*, item_id: str) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=item_id,
        status="green",
        stage="done",
        pr_number=11,
        merge_sha="feed01",
        detail="merged",
    )


def _journal_records(*, path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


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


@dataclass(frozen=True, kw_only=True)
class _ReviewRunner:
    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        _ = (argv, cwd, timeout_seconds, env)
        return CommandResult(exit_code=0, stdout=_ship_on_cap_events(), stderr="")


def _ship_on_cap_events() -> str:
    events = [
        _edge(to_node="review_fix", reason="preferred_label", preferred_label="fix"),
        _edge(to_node="review_fix", reason="preferred_label", preferred_label="fix"),
        _edge(to_node="pr", reason="unconditional", preferred_label=None),
    ]
    return "\n".join(json.dumps(event) for event in events)


def _edge(*, to_node: str, reason: str, preferred_label: str | None) -> dict[str, object]:
    event: dict[str, object] = {
        "event": "edge.selected",
        "from_node": "review",
        "to_node": to_node,
        "reason": reason,
    }
    if preferred_label is not None:
        event["preferred_label"] = preferred_label
    return event
