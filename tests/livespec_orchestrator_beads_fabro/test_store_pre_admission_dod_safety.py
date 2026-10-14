"""Ledger verdict writes preserve unrelated provenance and safe full remedies."""

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro import _store_pre_admission_dod as admission
from livespec_orchestrator_beads_fabro._beads_client import (
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._otel_scrub import REDACTION_MARKER
from livespec_orchestrator_beads_fabro.store import read_work_items
from livespec_orchestrator_beads_fabro.types import StoreConfig
from returns.io import IOResult, IOSuccess


def test_recorded_verdict_cannot_poison_a_dispatch_or_replace_other_metadata(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_fake_singleton()
    config = StoreConfig(
        tenant="safe",
        prefix="safe",
        server_user="safe",
        database="safe",
        bd_path="bd",
        fake=True,
        repo_root=tmp_path,
    )
    client = make_beads_client(config=config)
    audit = {
        "supersedes": "kept",
        "merge_sha": "abc123",
        "verification_timestamp": "2026-10-14T00:00:00Z",
    }
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id="safe-1",
            issue_type="task",
            title="A task",
            description="A brief",
            priority=2,
            assignee=None,
            created_at="2026-10-14T00:00:00Z",
            labels=[],
            metadata={"unmodeled": "kept", "audit": audit},
            spec_id=None,
            parent_id=None,
        )
    )
    item = next(iter(read_work_items(path=config)))

    def judge(**_: object) -> IOResult[CommandResult, str]:
        return IOSuccess(
            CommandResult(
                exit_code=0,
                stderr="",
                stdout=json.dumps(
                    {
                        "outcome": "failed",
                        "failure_reason": "Remove {{ expression }} from the brief.",
                        "remedies": [
                            "Remove {% statement %} and {# comment #}.",
                            "https://user:secret@example.test",
                        ],
                    }
                ),
            )
        )

    monkeypatch.setattr(admission, "judge_before_admission", judge)
    assert admission.pre_admission_hold(path=config, item=item) is not None
    record = client.show_issue(issue_id=item.id)
    assert record["metadata"]["unmodeled"] == "kept"
    assert record["metadata"]["audit"] == audit
    comment = client.list_comments(issue_id=item.id)[0]["text"]
    assert "{{" not in comment and "{%" not in comment and "{#" not in comment
    assert REDACTION_MARKER in comment
    assert "user:secret" not in comment
    assert record["metadata"]["pre_admission_dod"]["remedies"][1] == REDACTION_MARKER
