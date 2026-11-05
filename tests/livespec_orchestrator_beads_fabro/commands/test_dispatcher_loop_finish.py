"""The post-launch dispatcher finish step."""

from __future__ import annotations

import argparse
import importlib
from pathlib import Path
from typing import Any, cast

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

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_loop_finish"


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


def test_finish_emits_terminal_span_from_a_readable_fabro_event_stream(
    monkeypatch: Any, tmp_path: Path
) -> None:
    """The final disposition gains one terminal span without changing the result."""
    module = importlib.import_module(_MODULE)
    fabro_port_module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._fabro_port"
    )
    emitted: list[dict[str, object]] = []

    class _Events:
        def __init__(self) -> None:
            self.command = type("Command", (), {"exit_code": 0})()
            self.payload: list[object] = []

    class _Port:
        def events(self, *, run_id: str, timeout_seconds: float) -> _Events:
            assert (run_id, timeout_seconds) == ("01RUN", 30.0)
            return _Events()

    def port_for_plan(**_: object) -> _Port:
        return _Port()

    def terminal_emitter(**kwargs: object) -> None:
        emitted.append(kwargs)

    def dispose(**kwargs: object) -> DispatchOutcome:
        return cast("DispatchOutcome", kwargs["outcome"])

    def emit_review(**_: object) -> None:
        return None

    monkeypatch.setattr(fabro_port_module, "fabro_port_for_plan", port_for_plan)
    monkeypatch.setattr(module, "emit_terminal_span", terminal_emitter)

    result = finish_dispatch(
        args=argparse.Namespace(),
        repo=tmp_path,
        item=_item(),
        journal=JournalFile(path=tmp_path / "journal.jsonl"),
        plan=_plan(repo=tmp_path),
        outcome=_outcome(detail="done"),
        started_at=0.0,
        goal_text="goal",
        token_supplier=lambda: "token",
        identity=DispatchJournalIdentity(dispatch_id="dispatch-7", dispatch_factory="hp"),
        spans=tmp_path / "spans.jsonl",
        dispose=dispose,
        emit_review=emit_review,
    )

    assert result.fabro_run_id == "01RUN"
    assert emitted[0]["attempts"] == ()


def test_finish_keeps_the_disposition_when_terminal_telemetry_cannot_be_read(
    monkeypatch: Any, tmp_path: Path
) -> None:
    """A telemetry read error is best-effort and cannot replace the terminal result."""
    fabro_port_module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._fabro_port"
    )
    reviewed: list[ReviewGateEmission] = []

    class _Port:
        def events(self, *, run_id: str, timeout_seconds: float) -> object:
            _ = (run_id, timeout_seconds)
            raise OSError("events unavailable")

    def port_for_plan(**_: object) -> _Port:
        return _Port()

    def dispose(**kwargs: object) -> DispatchOutcome:
        return cast("DispatchOutcome", kwargs["outcome"])

    def emit_review(*, emission: ReviewGateEmission) -> None:
        reviewed.append(emission)

    monkeypatch.setattr(fabro_port_module, "fabro_port_for_plan", port_for_plan)

    result = finish_dispatch(
        args=argparse.Namespace(),
        repo=tmp_path,
        item=_item(),
        journal=JournalFile(path=tmp_path / "journal.jsonl"),
        plan=_plan(repo=tmp_path),
        outcome=_outcome(detail="done"),
        started_at=0.0,
        goal_text="goal",
        token_supplier=lambda: "token",
        identity=DispatchJournalIdentity(dispatch_id="dispatch-7", dispatch_factory="hp"),
        spans=tmp_path / "spans.jsonl",
        dispose=dispose,
        emit_review=emit_review,
    )

    assert result.detail == "done"
    assert len(reviewed) == 1
