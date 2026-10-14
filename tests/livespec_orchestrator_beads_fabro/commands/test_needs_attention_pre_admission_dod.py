"""Scenario 174: held admission verdicts remain visible without another judgement."""

import copy
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from livespec_orchestrator_beads_fabro import _store_pre_admission_dod as admission
from livespec_orchestrator_beads_fabro._beads_client import (
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands import needs_attention
from livespec_orchestrator_beads_fabro.types import StoreConfig


def test_attention_names_each_held_item_and_its_first_remedy(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reset_fake_singleton()
    connection = {
        "tenant": "attention",
        "prefix": "attention",
        "server_user": "attention",
        "database": "attention",
        "bd_path": "bd",
        "fake": True,
    }
    (tmp_path / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"connection": connection}}),
        encoding="utf-8",
    )
    spec = tmp_path / "SPECIFICATION"
    spec.mkdir()
    (spec / "contracts.md").write_text("## Routing\n\nRouting rules.\n", encoding="utf-8")
    config = StoreConfig(**connection, repo_root=tmp_path)
    client = make_beads_client(config=config)
    expected = {
        "attention-backlog": "Name the governing scenario.",
        "attention-pending": "Restate the assertion as delivered behaviour.",
    }
    cases = [
        ("attention-backlog", "backlog", True),
        ("attention-pending", "pending-approval", True),
        ("attention-stale", "ready", True),
        ("attention-clear", "pending-approval", False),
        ("attention-advisory", "ready", False),
    ]
    for item_id, status, held in cases:
        client.create_issue(
            draft=IssueDraft(
                issue_id=item_id,
                issue_type="task",
                title="Route a work item",
                description=(
                    "## Definition of Done\n\n- Regression tests cover routing.\n\n"
                    "References: Routing\n"
                ),
                priority=2,
                assignee=None,
                created_at="2026-10-14T00:00:00Z",
                labels=[],
                metadata={
                    "pre_admission_dod": {
                        "verdict": "needs-human",
                        "failure_reason": "The brief needs repair.",
                        "remedies": [expected.get(item_id, "Old remedy."), "Second remedy."],
                    }
                    if held
                    else None
                },
                spec_id=None,
                parent_id=None,
            )
        )
        client.update_issue(issue_id=item_id, status=status)
    before = copy.deepcopy(client.list_issues())
    judge = Mock()
    monkeypatch.setattr(admission, "judge_before_admission", judge)
    monkeypatch.setattr(needs_attention, "spec_next", Mock(return_value=None))

    facts = needs_attention.build_attention(
        project_root=tmp_path, repo_name="example", include_hygiene=False
    )

    held_facts = [
        fact for fact in facts if fact.id.startswith("hygiene:pre-admission-definition-of-done:")
    ]
    assert {fact.source_ref.work_item for fact in held_facts} == set(expected)
    for fact in held_facts:
        item_id = fact.source_ref.work_item
        assert item_id is not None
        assert item_id in fact.summary
        assert expected[item_id] in fact.summary
        assert "Second remedy." not in fact.summary
        assert fact.handoff is not None
        assert "context.py" in str(fact.handoff.command)
    assert any(
        fact.id == "hygiene:advisory-definition-of-done:attention-advisory" for fact in facts
    )
    judge.assert_not_called()
    assert client.list_issues() == before
    reset_fake_singleton()
