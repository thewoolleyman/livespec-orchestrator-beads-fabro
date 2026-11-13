"""Dispatcher watchdog-run context coverage."""

from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace
from typing import cast

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
