"""Focused coverage for needs-attention work-item host-only lanes."""

import json
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands._needs_attention_work_items import (
    host_only_items,
)
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

    monkeypatch.setattr(Path, "read_text", _raise)

    attention = host_only_items(project_root=tmp_path, repo="repo", items=[])

    assert attention == []
