"""`classify-tier` leaves an existing record alone and writes nothing when it cannot judge.

Two contracts of Scenario 267 that the happy path cannot show: a recorded tier is
reported as it stands even when it was taken against an older specification, and
a judgement that could not be obtained leaves the item's comments untouched and
the exit code non-zero.
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_comments import (
    append_work_item_comment,
    read_work_item_comments,
)
from livespec_orchestrator_beads_fabro.commands import dispatcher
from livespec_orchestrator_beads_fabro.commands._spec_change_tier import exempt_decision
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_record import (
    spec_change_tier_comment,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM = "bd-ib-parked-child"


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
        "# Contracts\n\n## A governing clause\n\nThe clause body.\n", encoding="utf-8"
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


def _install_judge(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reply: str) -> None:
    script = tmp_path / "fake-judge"
    _ = script.write_text(f"#!/bin/sh\n{reply}\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("LIVESPEC_DOD_JUDGEMENT_CLAUDE_PATH", str(script))


def _bodies(*, repo: Path) -> list[str]:
    comments = read_work_item_comments(path=_config(repo=repo), work_item_id=_ITEM)
    return [comment.text for comment in comments]


def test_a_stale_existing_record_is_reported_and_nothing_is_appended(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _install_judge(tmp_path=tmp_path, monkeypatch=monkeypatch, reply="echo bug")
    append_work_item(path=_config(repo=repo), item=_item())
    append_work_item_comment(
        path=_config(repo=repo),
        work_item_id=_ITEM,
        body=spec_change_tier_comment(
            item_id=_ITEM,
            stage="filing",
            decision=exempt_decision(classification="chore"),
            spec_version="999",
            digest="a-digest-from-an-older-input",
        ),
    )
    before = _bodies(repo=repo)

    assert dispatcher.main(argv=["classify-tier", "--repo", str(repo), "--item", _ITEM]) == 0

    assert _bodies(repo=repo) == before
    assert "existing classification tier none" in capsys.readouterr().out


def test_a_judgement_that_cannot_be_obtained_exits_non_zero_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _install_judge(tmp_path=tmp_path, monkeypatch=monkeypatch, reply="exit 1")
    append_work_item(path=_config(repo=repo), item=_item())

    assert dispatcher.main(argv=["classify-tier", "--repo", str(repo), "--item", _ITEM]) != 0

    assert _bodies(repo=repo) == []
    assert "classification did not run" in capsys.readouterr().err
