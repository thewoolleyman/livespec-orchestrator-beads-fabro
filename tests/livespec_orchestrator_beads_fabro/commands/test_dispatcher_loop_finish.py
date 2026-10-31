"""The post-launch dispatcher finish step."""

from __future__ import annotations

import argparse
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_id_journal import (
    DispatchJournalIdentity,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_finish import finish_dispatch
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._dispatcher_review_gate import (
    ReviewGateEmission,
)
from livespec_orchestrator_beads_fabro.types import WorkItem


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-5d5aue",
        type="task",
        status="active",
        title="Profile dispatch launch phases",
        description="Do the thing.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-10-31T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
        acceptance_criteria="The implementation is verified.",
    )


def _outcome(*, detail: str) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id="bd-ib-5d5aue",
        status="green",
        stage="fabro-run",
        pr_number=42,
        merge_sha="abc123",
        detail=detail,
        fabro_run_id="01RUN",
    )


def _plan(*, repo: Path) -> DispatchPlan:
    return DispatchPlan(
        repo=repo,
        work_item_id="bd-ib-5d5aue",
        branch="feat/bd-ib-5d5aue",
        workflow_toml=repo / "workflow.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        fabro_factory_name="hp",
        fabro_factory_server="https://hp.example.test",
        fabro_factory_dev_token=None,
        janitor=(),
        janitor_checkout=repo / "janitor",
        janitor_core_checkout=repo / "janitor-core",
        janitor_core_repo_url="https://example.test/livespec.git",
        janitor_core_ref="master",
        review_fix_visit_cap=0,
        merge_on_review_cap_outcome="succeeded",
    )


def test_finish_applies_disposition_then_emits_review_for_its_outcome(tmp_path: Path) -> None:
    """The review row describes the post-disposition terminal outcome."""
    original = _outcome(detail="before disposition")
    finished = _outcome(detail="after disposition")
    disposed: list[dict[str, object]] = []
    emissions: list[ReviewGateEmission] = []

    def dispose(**kwargs: object) -> DispatchOutcome:
        disposed.append(kwargs)
        return finished

    def emit_review(*, emission: ReviewGateEmission) -> None:
        emissions.append(emission)

    result = finish_dispatch(
        args=argparse.Namespace(),
        repo=tmp_path,
        item=_item(),
        journal=JournalFile(path=tmp_path / "journal.jsonl"),
        plan=_plan(repo=tmp_path),
        outcome=original,
        started_at=0.0,
        goal_text="rendered goal",
        token_supplier=lambda: "token",
        identity=DispatchJournalIdentity(dispatch_id="dispatch-7", dispatch_factory="hp"),
        spans=tmp_path / "spans.jsonl",
        dispose=dispose,
        emit_review=emit_review,
    )

    assert result is finished
    assert disposed[0]["outcome"] is original
    assert disposed[0]["dispatch_context_size"] == len("rendered goal")
    assert emissions[0].run_id == finished.fabro_run_id
    assert emissions[0].dispatch_id == "dispatch-7"
    assert emissions[0].dispatch_factory == "hp"
