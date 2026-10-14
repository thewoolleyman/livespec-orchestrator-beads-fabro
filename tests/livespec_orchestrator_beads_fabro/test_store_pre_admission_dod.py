"""Admission's fail-open decision consumes the gate Result without inventing a hold."""

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro import _store_pre_admission_dod as admission
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from returns.io import IOFailure, IOResult, IOSuccess


@pytest.mark.parametrize("available", [False, True])
def test_only_a_completed_needs_human_verdict_holds(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, available: bool
) -> None:
    config = StoreConfig(
        tenant="gate",
        prefix="gate",
        server_user="gate",
        database="gate",
        bd_path="bd",
        fake=True,
        repo_root=tmp_path,
    )
    item = WorkItem(
        id="gate-1",
        type="task",
        status="backlog",
        title="A task",
        description="A brief",
        origin="freeform",
        gap_id=None,
        rank="a1",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-14T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )

    def judge(**_: object) -> IOResult[CommandResult, str]:
        if not available:
            return IOFailure("no eligible model")
        return IOSuccess(
            CommandResult(
                exit_code=0,
                stdout='{"outcome":"failed","failure_reason":"Name Scenario 174."}',
                stderr="",
            )
        )

    monkeypatch.setattr(admission, "judge_before_admission", judge)
    assert admission.pre_admission_hold(path=config, item=item) == (
        "Name Scenario 174." if available else None
    )
