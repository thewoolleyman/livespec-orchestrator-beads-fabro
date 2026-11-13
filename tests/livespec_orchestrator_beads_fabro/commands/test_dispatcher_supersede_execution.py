"""Failure reporting for contaminated-item supersession."""

from __future__ import annotations

import argparse
import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from livespec_orchestrator_beads_fabro._store_comments import WorkItemComment
from livespec_orchestrator_beads_fabro.errors import BeadsCommandError
from livespec_orchestrator_beads_fabro.types import WorkItem
from returns.io import IOSuccess


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-old",
        type="bug",
        status="ready",
        title="poisoned item",
        description="description",
        origin="manual",
        gap_id=None,
        rank="b3b",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-13T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def test_a_failed_post_filing_step_names_the_successor_and_step(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module_path = Path(
        ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/"
        "_dispatcher_supersede_contaminated.py"
    )
    assert module_path.is_file()
    subject = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_supersede_contaminated"
    )
    error = BeadsCommandError(command="bd update", exit_code=1, stderr="unavailable")
    monkeypatch.setattr(subject, "new_work_item_id", lambda **_: "bd-ib-new")
    monkeypatch.setattr(subject, "store_config", lambda **_: SimpleNamespace(prefix="bd-ib"))
    monkeypatch.setattr(subject, "read_work_items", lambda **_: [_item()])
    monkeypatch.setattr(
        subject,
        "read_work_item_comments",
        lambda **_: (WorkItemComment(text="{{ evidence", author=None, created_at=None),),
    )
    monkeypatch.setattr(
        subject,
        "make_beads_client",
        lambda **_: SimpleNamespace(show_issue=lambda **_: {"labels": []}),
    )
    monkeypatch.setattr(subject, "file_captured_work_item", lambda **_: IOSuccess("backlog"))
    monkeypatch.setattr(subject, "_copy_labels", lambda **_: (_ for _ in ()).throw(error))

    exit_code = subject.run_supersede_contaminated_command(
        args=argparse.Namespace(
            repo=".", item="bd-ib-old", reason="preserve evidence", journal=None
        )
    )

    assert exit_code == 1
    assert "successor bd-ib-new failed at copy labels" in capsys.readouterr().err
