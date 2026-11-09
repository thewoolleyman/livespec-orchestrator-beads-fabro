"""`dispatcher.py fresh-ruling` records an operator ruling or refuses an unsafe reason."""

from __future__ import annotations

import json
from contextlib import suppress
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.store import append_work_item, read_work_item_comments
from livespec_orchestrator_beads_fabro.types import WorkItem

_ITEM_ID = "bd-ib-freshruling"
_REASON = "the preserved trees are stale"
_OPENER_REASON = "the trees are stale {{ inputs.goal }}"
_INVOKER = "operator:cwoolley"


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.delenv("LIVESPEC_INVOKER", raising=False)
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    append_work_item(path=store_config(repo=repo), item=_item())
    return repo


def _item() -> WorkItem:
    return replace(
        WorkItem(
            id=_ITEM_ID,
            type="task",
            status="ready",
            title="A released item",
            description="Implement the slice.",
            origin="freeform",
            gap_id=None,
            rank="a0",
            assignee=None,
            depends_on=(),
            captured_at="2026-11-08T00:00:00Z",
            resolution=None,
            reason=None,
            audit=None,
            superseded_by=None,
            admission_policy="auto",
            acceptance_policy="ai-only",
            acceptance_criteria="The slice is verified.",
        ),
    )


def _run(*, repo: Path, journal: Path, reason: str) -> list[int]:
    argv = [
        "fresh-ruling",
        "--repo",
        str(repo),
        "--journal",
        str(journal),
        "--item",
        _ITEM_ID,
        "--reason",
        reason,
        "--invoker",
        _INVOKER,
    ]
    exit_codes: list[int] = []
    with suppress(SystemExit):
        exit_codes.append(main(argv=argv))
    return exit_codes


def test_a_fresh_ruling_writes_one_ledger_comment_and_journals_one_record(
    *, tmp_path: Path
) -> None:
    repo = _repo(tmp_path=tmp_path)
    journal = tmp_path / "journal.jsonl"

    assert _run(repo=repo, journal=journal, reason=_REASON) == [0]

    comments = read_work_item_comments(path=store_config(repo=repo), work_item_id=_ITEM_ID)
    assert len(comments) == 1
    lines = comments[0].text.splitlines()
    assert lines[0] == "livespec-fresh-ruling"
    assert f"invoker: {_INVOKER}" in lines
    assert f"reason: {_REASON}" in lines
    instant = next(line.removeprefix("instant: ") for line in lines if line.startswith("instant: "))
    assert instant.endswith("Z")
    records = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 1
    assert records[0]["stage"] == "fresh-ruling"
    assert records[0]["work_item_id"] == _ITEM_ID
    assert records[0]["invoker"] == _INVOKER
    assert records[0]["reason"] == _REASON
    assert records[0]["instant"] == instant


def test_a_reason_the_template_opener_detector_flags_is_refused_and_writes_nothing(
    *, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    repo = _repo(tmp_path=tmp_path)
    journal = tmp_path / "journal.jsonl"

    assert _run(repo=repo, journal=journal, reason=_OPENER_REASON) == [3]

    assert "{{" in capsys.readouterr().err
    assert read_work_item_comments(path=store_config(repo=repo), work_item_id=_ITEM_ID) == ()
    assert not journal.exists()
