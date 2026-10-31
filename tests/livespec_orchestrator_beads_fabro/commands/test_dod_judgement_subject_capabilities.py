"""A host judgement subject carries the capability set a tool-free judge cannot read."""

from __future__ import annotations

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    CAPABILITIES_HEADING,
    judgement_subject,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_capabilities import (
    UNPUBLISHED_REPORT,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_ITEM = WorkItem(
    id="bd-ib-aaaaaa",
    type="bug",
    status="ready",
    title="t",
    description="## Definition of Done\n\n- It works.\n\nReferences: ## Scenario 1 — x\n",
    origin="freeform",
    gap_id=None,
    rank="a0",
    assignee=None,
    depends_on=(),
    captured_at="2026-10-20T00:00:00Z",
    resolution=None,
    reason=None,
    audit=None,
    superseded_by=None,
    admission_policy="auto",
    acceptance_policy="ai-only",
)


def _capability_block(*, subject: str) -> str:
    after = subject.split(f"{CAPABILITIES_HEADING}\n", 1)[1]
    return after.split("\n", 1)[0]


def _config(*, repo: Path, dispatcher: str) -> None:
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"dispatcher": {' + dispatcher + "}}}",
        encoding="utf-8",
    )


def test_the_subject_names_the_committed_capability_mirror(tmp_path: Path) -> None:
    _config(repo=tmp_path, dispatcher='"sandbox_capabilities": ["terminal", "tmux"]')

    subject = judgement_subject(item=_ITEM, cwd=tmp_path)

    assert _capability_block(subject=subject) == (
        "committed dispatcher.sandbox_capabilities: terminal, tmux"
    )


@pytest.mark.parametrize(
    "dispatcher",
    ['"sandbox_capabilities": []', '"sandbox_capabilities": ["Not-Snake"]', '"other": 1'],
)
def test_an_empty_or_unusable_mirror_is_the_unknown_set(tmp_path: Path, dispatcher: str) -> None:
    _config(repo=tmp_path, dispatcher=dispatcher)

    subject = judgement_subject(item=_ITEM, cwd=tmp_path)

    assert _capability_block(subject=subject) == UNPUBLISHED_REPORT


def test_an_unreadable_config_is_the_unknown_set(tmp_path: Path) -> None:
    _ = (tmp_path / ".livespec.jsonc").write_text("{ not json", encoding="utf-8")

    subject = judgement_subject(item=_ITEM, cwd=tmp_path)

    assert _capability_block(subject=subject) == UNPUBLISHED_REPORT


def test_an_absent_config_is_the_unknown_set(tmp_path: Path) -> None:
    subject = judgement_subject(item=_ITEM, cwd=tmp_path)

    assert _capability_block(subject=subject) == UNPUBLISHED_REPORT
