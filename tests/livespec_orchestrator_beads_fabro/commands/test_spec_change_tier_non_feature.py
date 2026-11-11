"""Non-feature classifications take the same spec-stated judgement as features."""

from __future__ import annotations

import stat
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments
from livespec_orchestrator_beads_fabro.commands import dispatcher
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_gate import (
    classify_item_spec_change_tier,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_record import (
    STAGE_FILING,
    recorded_spec_change_tier,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_HEADING = "## A governing clause"
_PARTIAL = (
    '{"kind": "partial", "stated_by": [], "generalization_target": '
    f'"{_HEADING}", "rationale": "the ratified text states only part"}}'
)
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


def _item(*, item_id: str) -> WorkItem:
    return WorkItem(
        id=item_id,
        type="bug",
        status="backlog",
        title="Hold an unstated change for its proposal",
        description="New observable behaviour.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-11T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _install_judge(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, replies: tuple[str, ...]
) -> None:
    script = tmp_path / "fake-judge"
    _ = script.write_text(
        "#!/bin/sh\n"
        'calls=$(wc -l < "$LIVESPEC_TIER_CALLS" 2>/dev/null || true)\n'
        "case $calls in\n"
        + "".join(f"{index}) echo '{reply}' ;;\n" for index, reply in enumerate(replies))
        + "*) exit 1 ;;\n"
        "esac\n"
        'echo call >> "$LIVESPEC_TIER_CALLS"\n',
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    calls = tmp_path / "calls"
    _ = calls.touch()
    monkeypatch.setenv("LIVESPEC_DOD_JUDGEMENT_CLAUDE_PATH", str(script))
    monkeypatch.setenv("LIVESPEC_TIER_CALLS", str(calls))


@pytest.mark.parametrize(
    ("classification", "verdict"),
    [
        ("bug", _PARTIAL),
        ("chore", _UNSTATED),
        ("non_functional", _PARTIAL),
    ],
)
def test_filing_holds_a_non_feature_classification_for_unstated_behaviour(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    classification: str,
    verdict: str,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _install_judge(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        replies=(classification, verdict),
    )
    item = _item(item_id=f"bd-ib-{classification}")
    append_work_item(path=_config(repo=repo), item=item)

    outcome = classify_item_spec_change_tier(
        item=item, repo=repo, path=_config(repo=repo), stage=STAGE_FILING
    )

    assert outcome.is_spec_change is True
    assert outcome.recorded is not None
    assert outcome.recorded.classification == classification
    assert outcome.recorded.verdict_kind in ("partial", "unstated")
    assert outcome.recorded.linked_proposal_topic is not None
    assert len(read_work_item_comments(path=_config(repo=repo), work_item_id=item.id)) == 1


def test_classify_tier_rejudges_a_changed_item_and_records_its_new_tier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _install_judge(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        replies=("feature", _UNSTATED, "feature", _UNSTATED),
    )
    item = _item(item_id="bd-ib-rejudge")
    append_work_item(path=_config(repo=repo), item=item)
    assert dispatcher.main(argv=["classify-tier", "--repo", str(repo), "--item", item.id]) == 0

    changed = replace(item, description="Changed observable behaviour.")
    append_work_item(path=_config(repo=repo), item=changed)

    assert dispatcher.main(argv=["classify-tier", "--repo", str(repo), "--item", item.id]) == 0
    comments = read_work_item_comments(path=_config(repo=repo), work_item_id=item.id)
    recorded = recorded_spec_change_tier(comments=tuple(comment.text for comment in comments))
    assert len(comments) == 2
    assert recorded is not None
    assert recorded.is_spec_change is True
