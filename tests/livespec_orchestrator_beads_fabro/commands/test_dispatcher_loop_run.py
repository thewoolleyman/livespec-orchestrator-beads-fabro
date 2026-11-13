"""Dispatcher watchdog-run context coverage."""

from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop_run as run_module
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_run import DispatchRunContext
from livespec_orchestrator_beads_fabro.types import WorkItem


def test_watchdog_context_is_public() -> None:
    assert DispatchRunContext.__name__ == "DispatchRunContext"


def test_pre_merge_gate_reads_the_fix_loop_count_when_it_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A final retry must not retain the count from before the engine ran."""
    assert hasattr(run_module, "pre_merge_gate_for")
    records: tuple[dict[str, object], ...] = ()
    captured: dict[str, object] = {}

    def bind_gate(**kwargs: object) -> object:
        captured.update(kwargs)
        return lambda **_: None

    monkeypatch.setattr(run_module, "pre_merge_runtime_gate", bind_gate)
    monkeypatch.setattr(run_module, "read_journal_records_for", lambda **_: records)
    context = DispatchRunContext(
        args=argparse.Namespace(journal=str(tmp_path / "journal.jsonl")),
        repo=tmp_path,
        plan=cast("DispatchPlan", SimpleNamespace(review_fix_visit_cap=3)),
        journal=JournalFile(path=tmp_path / "journal.jsonl"),
        overlay_file=tmp_path / "overlay.toml",
        token_supplier=lambda: "token",
        item=cast("WorkItem", SimpleNamespace(id="bd-ib-z2y4ca")),
    )

    _ = run_module.pre_merge_gate_for(context=context)

    count = captured["fix_loop_count"]
    assert callable(count)
    records = tuple({"work_item_id": "bd-ib-z2y4ca", "stage": "pr-update-branch"} for _ in range(3))
    assert count() == 3


def _plan(*, repo: Path) -> DispatchPlan:
    return DispatchPlan(
        repo=repo,
        work_item_id="bd-ib-z2y4ca",
        branch="feat/bd-ib-z2y4ca",
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


def test_the_watchdog_run_hands_the_engine_its_gate_on_the_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The engine takes the runtime gate from the plan, not from a seventh parameter."""
    monkeypatch.setattr(run_module, "emit_dispatch_span", lambda **_: None)
    monkeypatch.setattr(run_module, "dispatch_spans_path", lambda **_: tmp_path / "spans.jsonl")
    monkeypatch.setattr(run_module, "heartbeat_path", lambda **_: tmp_path / "beat.jsonl")
    monkeypatch.setattr(run_module, "revoke_proof_credentials", lambda **_: None)
    bound = object()
    monkeypatch.setattr(run_module, "pre_merge_gate_for", lambda **_: bound)
    received: dict[str, object] = {}

    def run_dispatch(**kwargs: object) -> object:
        received.update(kwargs)
        return "outcome"

    _ = run_module.run_dispatch_with_watchdog(
        context=DispatchRunContext(
            args=argparse.Namespace(poll_attempts=1, poll_interval_seconds=0.0),
            repo=tmp_path,
            plan=_plan(repo=tmp_path),
            journal=JournalFile(path=tmp_path / "journal.jsonl"),
            overlay_file=tmp_path / "overlay.toml",
            token_supplier=lambda: "token",
            dispatch_id="dispatch-7",
            item=cast("WorkItem", SimpleNamespace(id="bd-ib-z2y4ca")),
        ),
        run_dispatch_func=cast("Any", run_dispatch),
        fabro_launcher_type=lambda **_: cast("Any", object()),
    )

    plan = cast("DispatchPlan", received["plan"])
    assert plan.pre_merge_gate is bound
    assert "pre_merge_gate" not in received
