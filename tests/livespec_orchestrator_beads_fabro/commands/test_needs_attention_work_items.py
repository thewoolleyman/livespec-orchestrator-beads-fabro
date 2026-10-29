"""Focused coverage for needs-attention work-item host-only lanes."""

import importlib
import json
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._fabro_port import (
    FabroPsResult,
    FabroRunSummary,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_work_items import (
    host_only_items,
)
from livespec_orchestrator_beads_fabro.commands._run_attribution import RunAttribution
from livespec_orchestrator_beads_fabro.types import WorkItem


def _item(
    *,
    id_: str,
    status: str = "ready",
    factory_safety: str | None = None,
) -> WorkItem:
    return WorkItem(
        id=id_,
        type="task",
        status=status,  # type: ignore[arg-type]
        title=f"{id_} title",
        description="d",
        origin="freeform",
        gap_id=None,
        rank="a1",
        assignee=None,
        depends_on=(),
        captured_at="2026-05-19T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        factory_safety=factory_safety,  # type: ignore[arg-type]
    )


def _write_journal_lines(project_root: Path, *, records: list[object]) -> None:
    journal = project_root / "tmp" / "fabro-dispatch-journal.jsonl"
    journal.parent.mkdir(parents=True)
    lines = [record if isinstance(record, str) else json.dumps(record) for record in records]
    _ = journal.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _outcome(
    *, work_item_id: object = "bd-recorded", stage: object = "host-only-refused"
) -> dict[str, Any]:
    return {
        "stage": "outcome",
        "outcome": {
            "work_item_id": work_item_id,
            "stage": stage,
        },
    }


def _dispatch_outcome(
    *,
    work_item_id: object = "bd-active",
    status: object = "failed",
    stage: object = "janitor-post-merge",
    pr_number: object = 836,
    merge_sha: object = "ba9fdafef895",
) -> dict[str, Any]:
    return {
        "stage": "outcome",
        "outcome": {
            "work_item_id": work_item_id,
            "status": status,
            "stage": stage,
            "pr_number": pr_number,
            "merge_sha": merge_sha,
            "detail": "post-merge janitor red",
        },
    }


def test_stranded_dispatch_items_surface_active_terminal_janitor_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_journal_lines(
        tmp_path,
        records=[
            _dispatch_outcome(work_item_id="bd-active"),
            _dispatch_outcome(work_item_id="bd-active"),
            _dispatch_outcome(work_item_id="bd-closed"),
            _dispatch_outcome(work_item_id="bd-locked"),
        ],
    )

    def _live_lock(*, repo: Path, work_item_id: str) -> object | None:
        _ = repo
        return object() if work_item_id == "bd-locked" else None

    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._needs_attention_work_items"
    )
    assert hasattr(module, "stranded_dispatch_items")
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._needs_attention_work_items.live_dispatch_lock",
        _live_lock,
    )

    attention = module.stranded_dispatch_items(
        project_root=tmp_path,
        repo="repo",
        items=[
            _item(id_="bd-active", status="active"),
            _item(id_="bd-closed", status="done"),
            _item(id_="bd-locked", status="active"),
        ],
    )

    assert [item.id for item in attention] == ["host-only:stranded-dispatch:bd-active"]
    stranded = attention[0]
    assert stranded.kind == "host-only"
    assert stranded.urgency == "high"
    assert stranded.source_ref.work_item == "bd-active"
    assert "bd-active" in stranded.summary
    assert "PR #836" in stranded.summary
    assert "janitor-post-merge" in stranded.summary
    assert "2 prior attempts" in stranded.summary
    assert "ba9fdafef895" in stranded.summary
    assert stranded.handoff.kind == "shell"
    assert "reconcile-merged" in stranded.handoff.command
    assert "--item bd-active" in stranded.handoff.command
    assert "resolve-blocked" not in stranded.handoff.command


def test_host_only_items_ignores_done_items_and_malformed_journal_records(tmp_path: Path) -> None:
    _write_journal_lines(
        tmp_path,
        records=[
            "{",
            [],
            {"stage": "fabro-run"},
            {"stage": "outcome", "outcome": "not-a-dict"},
            _outcome(stage="failed"),
            _outcome(work_item_id=None),
            _outcome(work_item_id="bd-recorded"),
            _outcome(work_item_id="bd-recorded"),
        ],
    )

    attention = host_only_items(
        project_root=tmp_path,
        repo="repo",
        items=[_item(id_="bd-done", status="done", factory_safety="needs-host-secrets")],
    )

    assert [item.id for item in attention] == ["host-only:recorded-refusal:bd-recorded"]


def test_host_only_items_prefers_current_factory_safety_over_recorded_refusal(
    tmp_path: Path,
) -> None:
    _write_journal_lines(tmp_path, records=[_outcome(work_item_id="bd-host")])

    attention = host_only_items(
        project_root=tmp_path,
        repo="repo",
        items=[_item(id_="bd-host", factory_safety="needs-host-secrets")],
    )

    assert [item.id for item in attention] == ["host-only:needs-host-secrets:bd-host"]


def test_host_only_items_fail_soft_when_journal_cannot_be_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_journal_lines(tmp_path, records=[_outcome(work_item_id="bd-recorded")])

    def _raise(*args: object, **kwargs: object) -> str:
        _ = args
        _ = kwargs
        raise OSError("unreadable")

    monkeypatch.setattr(Path, "open", _raise)

    attention = host_only_items(project_root=tmp_path, repo="repo", items=[])

    assert attention == []


def _ps_result(*, runs: tuple[FabroRunSummary, ...]) -> FabroPsResult:
    return FabroPsResult(
        command=CommandResult(exit_code=0, stdout="", stderr=""),
        payload=None,
        runs=runs,
    )


def _live_row(*, run_id: str, work_item_id: str | None) -> FabroRunSummary:
    return FabroRunSummary(
        run_id=run_id,
        status_kind="running",
        goal=None,
        work_item_id=work_item_id,
        total_usd_micros=None,
    )


def test_needs_attention_reads_live_runs_through_the_stamp_not_the_goal_regex(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A live run reported under the wrong item makes needs-attention lie twice.

    It says the mis-named item is busy and it says the real owner is idle, so an
    operator reading the lane re-dispatches work that is already running.
    """
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._needs_attention_work_items"
    )
    row = _live_row(run_id="01LIVE", work_item_id="bd-ib-mislabelled")

    def _ps(*, repo: Path) -> FabroPsResult:
        assert repo == tmp_path
        return _ps_result(runs=(row,))

    def _attribution(*, repo: Path) -> RunAttribution:
        assert repo == tmp_path
        return RunAttribution(metadata_run_ids={"01LIVE": "bd-ib-owner"})

    monkeypatch.setattr(module, "_fabro_ps", _ps)
    monkeypatch.setattr(module, "repo_run_attribution", _attribution)

    assert module.watchable_fabro_run_item_ids(repo=tmp_path) == frozenset({"bd-ib-owner"})
    assert module.watchable_fabro_run_lookup(repo=tmp_path, work_item_id="bd-ib-owner") is row
    assert (
        module.watchable_fabro_run_lookup(repo=tmp_path, work_item_id="bd-ib-mislabelled") is None
    )
