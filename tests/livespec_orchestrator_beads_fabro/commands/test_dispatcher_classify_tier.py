"""The mutation-only `classify-tier` command records a parked child's tier.

Scenario 267 needs an operator surface that takes precisely the same
spec-stated judgement as the pre-dispatch wall without taking any dispatch
steps.  The assertions in this module drive the dispatcher entry point against
the fake tenant so they observe the command's ledger write rather than a
private helper's return value.
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments
from livespec_orchestrator_beads_fabro.commands import dispatcher
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_record import (
    recorded_spec_change_tier,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM = "bd-ib-parked-child"
_HEADING = "## A governing clause"
_UNSTATED = (
    '{"kind": "unstated", "stated_by": [], "generalization_target": '
    f'"{_HEADING}", "rationale": "the ratified text does not state it"}}'
)


@pytest.fixture(autouse=True)
def _fake_beads_env(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config(*, repo: Path) -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
        repo_root=repo,
    )


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    (spec / "history" / "v001").mkdir(parents=True)
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}, '
        '"dispatcher": {"acp_nodes": {"dod_gate": {"agent": "claude-acp", '
        '"model": "claude-opus-5"}}}}}',
        encoding="utf-8",
    )
    _ = (spec / "contracts.md").write_text(
        f"# Contracts\n\n{_HEADING}\n\nThe clause body.\n", encoding="utf-8"
    )
    return repo


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM,
        type="task",
        status="blocked",
        title="A parked plan child",
        description="New observable behaviour.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-15T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _install_judge(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    script = tmp_path / "fake-judge"
    _ = script.write_text(
        "#!/bin/sh\n"
        'calls=$(wc -l < "$LIVESPEC_CLASSIFY_TIER_CALLS" 2>/dev/null || true)\n'
        "case $calls in\n"
        "0) echo feature ;;\n"
        f"1) echo '{_UNSTATED}' ;;\n"
        "*) exit 1 ;;\n"
        "esac\n"
        'echo call >> "$LIVESPEC_CLASSIFY_TIER_CALLS"\n',
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("LIVESPEC_DOD_JUDGEMENT_CLAUDE_PATH", str(script))
    calls = tmp_path / "calls"
    _ = calls.touch()
    monkeypatch.setenv("LIVESPEC_CLASSIFY_TIER_CALLS", str(calls))


def test_classify_tier_records_one_classification_for_an_unclassified_item(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _install_judge(tmp_path=tmp_path, monkeypatch=monkeypatch)
    append_work_item(path=_config(repo=repo), item=_item())

    assert "run_classify_tier_command" in dispatcher.__all__

    assert dispatcher.main(argv=["classify-tier", "--repo", str(repo), "--item", _ITEM]) == 0
    comments = read_work_item_comments(path=_config(repo=repo), work_item_id=_ITEM)
    recorded = recorded_spec_change_tier(comments=tuple(comment.text for comment in comments))
    assert len(comments) == 1
    assert recorded is not None
    assert recorded.is_spec_change is True
