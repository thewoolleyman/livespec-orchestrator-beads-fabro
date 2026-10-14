"""Admission's fail-open decision consumes the gate Result without inventing a hold."""

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro import _store_pre_admission_dod as admission
from livespec_orchestrator_beads_fabro._beads_client import make_beads_client, reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from returns.io import IOFailure, IOResult, IOSuccess


@pytest.fixture
def filed(*, tmp_path: Path) -> tuple[StoreConfig, WorkItem]:
    reset_fake_singleton()
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

    append_work_item(path=config, item=item)
    return config, item


@pytest.mark.parametrize("available", [False, True])
def test_only_a_completed_needs_human_verdict_holds(
    *, filed: tuple[StoreConfig, WorkItem], monkeypatch: pytest.MonkeyPatch, available: bool
) -> None:
    config, item = filed

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


def test_held_verdict_and_every_remedy_are_appended_to_the_ledger(
    *,
    filed: tuple[StoreConfig, WorkItem],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, item = filed
    reason = (
        "Assertion 1 cites the wrong heading; assertion 2 promises a test instead of behaviour."
    )
    remedies = [
        "Reference Scenario 174.",
        "Describe the observable behaviour.",
        "Keep this full remedy: " + "detail " * 900,
    ]

    def judge(**_: object) -> IOResult[CommandResult, str]:
        return IOSuccess(
            CommandResult(
                exit_code=0,
                stderr="",
                stdout=json.dumps(
                    {"outcome": "failed", "failure_reason": reason, "remedies": remedies}
                ),
            )
        )

    monkeypatch.setattr(admission, "judge_before_admission", judge)
    assert admission.pre_admission_hold(path=config, item=item) == reason
    client = make_beads_client(config=config)
    comments = client.list_comments(issue_id=item.id)
    assert len(comments) == 1, "a held judgement must append its verdict to the item"
    text = comments[0]["text"]
    assert "needs-human" in text
    assert reason in text
    assert all(remedy in text for remedy in remedies)
    state = client.show_issue(issue_id=item.id)["metadata"]["pre_admission_dod"]
    assert state["failure_reason"] == reason
    assert state["remedies"] == remedies
