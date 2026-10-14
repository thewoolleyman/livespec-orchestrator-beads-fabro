"""A semantic hold cannot consume the next eligible candidate's factory slot."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro import _store_pre_admission_dod as judgement
from livespec_orchestrator_beads_fabro._beads_client import make_beads_client, reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_admission as admission,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_admission_eligibility as eligibility,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from returns.io import IOResult, IOSuccess


def test_held_candidate_leaves_the_slot_for_existing_ready_work(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reset_fake_singleton()
    config = StoreConfig(
        tenant="slot",
        prefix="slot",
        server_user="slot",
        database="slot",
        bd_path="bd",
        fake=True,
        repo_root=tmp_path,
    )
    held = WorkItem(
        id="slot-1",
        type="task",
        status="pending-approval",
        title="An authoring defect",
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
        admission_policy="auto",
    )
    ready = replace(held, id="slot-2", status="ready", rank="a2")
    for item in (held, ready):
        append_work_item(path=config, item=item)
    _ = (tmp_path / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"dispatcher": {"wip_cap": 1}}}),
        encoding="utf-8",
    )
    judged: list[str] = []

    def judge(*, path: StoreConfig, item: WorkItem) -> IOResult[CommandResult, str]:
        assert path == config
        judged.append(item.id)
        return IOSuccess(
            CommandResult(
                exit_code=0,
                stdout='{"outcome":"failed","failure_reason":"Correct the reference."}',
                stderr="",
            )
        )

    monkeypatch.setattr(judgement, "judge_before_admission", judge)
    monkeypatch.setattr(admission, "store_config", lambda **_: config)
    monkeypatch.setattr(eligibility, "read_dispatch_labels", lambda **_: ())
    journal = JournalFile(path=tmp_path / "journal.jsonl")
    result = admission.admit_and_select(
        repo=tmp_path,
        items=[held, ready],
        candidates=[held, ready],
        journal=journal,
        enforce_cap=True,
    )
    assert judged == [held.id], "existing ready work is not rejudged by admission"
    assert [item.id for item in result.admitted] == [ready.id]
    assert result.deferred == []
    assert len(result.refused) == 1
    assert result.refused[0].stage == "pre-admission-dod"
    assert result.refused[0].detail == "Correct the reference."
    client = make_beads_client(config=config)
    assert client.show_issue(issue_id=held.id)["status"] == "pending-approval"
    assert client.show_issue(issue_id=ready.id)["status"] == "active"
    records = [json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines()]
    assert any(record.get("stage") == "outcome" for record in records)
