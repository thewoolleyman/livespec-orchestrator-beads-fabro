"""The `hygiene:spec-tier-relink` lane: a held item names its relink candidate.

`bd-ib-jnbcny`: a spec-change-tier item held because its linked topic has no
ratifying revision record, whose generalization-target heading a LATER ratified
revision amended under a different topic, is surfaced by `needs-attention` with
that topic and its specification version, and a handoff naming the
`relink-spec-tier` route that would replace the stale stem.

The spec history is a real fixture and the lane is driven over a real (fake-backend)
tenant, because the thing it has to get right is agreement with the wall's refusal:
both read ONE `standing_hold`, so a lane built on a second reading could name a
different topic than the refusal and still pass a stubbed test. Every case that
expects a row sits beside one that expects none on the same fixture shape — the
rejected revision, the untouched heading, the ratified topic and the wrong lane —
because a lane that emitted a row for every held item satisfies each positive case.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_comments import append_work_item_comment
from livespec_orchestrator_beads_fabro.commands import needs_attention
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_comments import (
    item_comment_bodies,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier import (
    decide_spec_change_tier,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_record import (
    STAGE_DISPATCH,
    spec_change_tier_comment,
)
from livespec_orchestrator_beads_fabro.commands.needs_attention import build_attention
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from livespec_runtime.spec_stated import SpecStatedVerdict

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_needs_attention_spec_tier_relink.py"
)
_ITEM = "bd-held"
_DERIVED_TOPIC = "hold-an-unstated-feature-for"
_TARGET = "## A governing clause"
_ROW = f"hygiene:spec-tier-relink:{_ITEM}"


@pytest.fixture(autouse=True)
def _fake_beads_env(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config(*, repo: Path) -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
        repo_root=repo,
    )


def _snapshot(*, spec_root: Path, version: int, body: str) -> Path:
    version_dir = spec_root / "history" / f"v{version:03d}"
    version_dir.mkdir(parents=True, exist_ok=True)
    _ = (version_dir / "spec.md").write_text(
        f"# Spec\n\n{_TARGET}\n\n{body}\n\n## Last clause\n\nend\n", encoding="utf-8"
    )
    return version_dir


def _revise(*, version_dir: Path, topic: str, decision: str) -> None:
    changes = version_dir / "proposed_changes"
    changes.mkdir(parents=True, exist_ok=True)
    _ = (changes / f"{topic}.md").write_text("the proposal\n", encoding="utf-8")
    _ = (changes / f"{topic}-revision.md").write_text(
        f"---\nproposal: {topic}.md\ndecision: {decision}\n---\n", encoding="utf-8"
    )


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "SPECIFICATION").mkdir(parents=True)
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": '
        '{"prefix": "bd", "bd_path": "bd", "fake": true}}}',
        encoding="utf-8",
    )
    return repo


def _item(*, item_id: str = _ITEM, status: str = "backlog") -> WorkItem:
    return WorkItem(
        id=item_id,
        type="bug",
        status=status,  # type: ignore[arg-type]
        title="Hold an unstated feature for its proposal",
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
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _hold(*, repo: Path, status: str = "backlog", item_id: str = _ITEM) -> WorkItem:
    """File the item and record a spec-change tier against specification version 1."""
    item = _item(item_id=item_id, status=status)
    append_work_item(path=_config(repo=repo), item=item)
    decision = decide_spec_change_tier(
        item=item,
        classification="feature",
        verdict=SpecStatedVerdict(
            kind="unstated",
            stated_by=(),
            generalization_target=_TARGET,
            rationale="the ratified text does not state the whole of it",
        ),
    )
    append_work_item_comment(
        path=_config(repo=repo),
        work_item_id=item_id,
        body=spec_change_tier_comment(
            item_id=item_id,
            stage=STAGE_DISPATCH,
            decision=decision,
            spec_version="1",
            digest="a-digest",
        ),
    )
    return item


def _amend(*, repo: Path, topic: str, decision: str, version: int = 2, body: str = "new") -> None:
    spec_root = repo / "SPECIFICATION"
    if version == 2:
        _ = _snapshot(spec_root=spec_root, version=1, body="old")
    _revise(
        version_dir=_snapshot(spec_root=spec_root, version=version, body=body),
        topic=topic,
        decision=decision,
    )


def _lane(*, repo: Path, items: list[WorkItem]) -> list[Any]:
    assert _MODULE_PATH.is_file()
    return importlib.import_module(
        f"{_PACKAGE}._needs_attention_spec_tier_relink"
    ).spec_tier_relink_items(project_root=repo, repo="repo", items=items, config=_config(repo=repo))


def test_a_held_item_with_a_ratified_amendment_gets_one_row_naming_the_candidate(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _amend(repo=repo, topic="the-topic-it-was-filed-under", decision="accept")
    item = _hold(repo=repo)

    [row] = _lane(repo=repo, items=[item])

    assert (row.id, row.kind) == (_ROW, "hygiene")
    assert row.source_ref.repo == "repo"
    assert row.source_ref.work_item == _ITEM
    assert _DERIVED_TOPIC in row.summary
    assert "the-topic-it-was-filed-under" in row.summary
    assert "v002" in row.summary
    assert row.handoff.kind == "drive"
    action = f"relink-spec-tier:{_ITEM}:the-topic-it-was-filed-under"
    assert row.handoff.action_id == action
    assert f"--action {action}" in row.handoff.command


def test_a_modify_revision_is_named_and_the_most_recently_cut_one_wins(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    _amend(repo=repo, topic="the-earlier-topic", decision="accept")
    _amend(repo=repo, topic="the-later-topic", decision="modify", version=3, body="newer")
    item = _hold(repo=repo)

    [row] = _lane(repo=repo, items=[item])

    assert row.handoff.action_id == f"relink-spec-tier:{_ITEM}:the-later-topic"
    assert "v003" in row.summary
    assert "the-earlier-topic" not in row.summary


def test_a_rejected_revision_gets_no_row(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    _amend(repo=repo, topic="a-rejected-topic", decision="reject")
    item = _hold(repo=repo)

    assert _lane(repo=repo, items=[item]) == []


def test_a_hold_whose_target_no_later_revision_amended_gets_no_row(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    _amend(repo=repo, topic="an-unrelated-topic", decision="accept", body="old")
    item = _hold(repo=repo)

    assert _lane(repo=repo, items=[item]) == []


def test_a_hold_whose_own_topic_is_ratified_gets_no_row(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    _amend(repo=repo, topic="the-topic-it-was-filed-under", decision="accept")
    _amend(repo=repo, topic=_DERIVED_TOPIC, decision="accept", version=3, body="newest")
    item = _hold(repo=repo)

    assert _lane(repo=repo, items=[item]) == []


def test_an_item_in_a_lane_a_hold_cannot_stand_in_gets_no_row(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    _amend(repo=repo, topic="the-topic-it-was-filed-under", decision="accept")
    active = _hold(repo=repo, status="active")

    assert _lane(repo=repo, items=[active]) == []


def test_an_item_with_no_recorded_classification_gets_no_row(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    _amend(repo=repo, topic="the-topic-it-was-filed-under", decision="accept")
    unrecorded = _item(item_id="bd-unrecorded")
    append_work_item(path=_config(repo=repo), item=unrecorded)

    assert _lane(repo=repo, items=[unrecorded]) == []


def test_composing_the_lane_writes_no_ledger_record(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    _amend(repo=repo, topic="the-topic-it-was-filed-under", decision="accept")
    item = _hold(repo=repo)
    before = item_comment_bodies(path=_config(repo=repo), work_item_id=_ITEM)

    assert len(_lane(repo=repo, items=[item])) == 1

    assert item_comment_bodies(path=_config(repo=repo), work_item_id=_ITEM) == before


def test_build_attention_carries_the_row_for_a_held_item(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(needs_attention, "spec_next", lambda **_kwargs: None)
    monkeypatch.setattr(needs_attention, "currency_staleness_items", lambda **_kwargs: [])
    repo = _repo(tmp_path=tmp_path)
    _amend(repo=repo, topic="the-topic-it-was-filed-under", decision="accept")
    _ = _hold(repo=repo)

    attention = build_attention(project_root=repo, repo_name="repo", include_hygiene=False)

    assert [one.id for one in attention if one.id.startswith("hygiene:spec-tier-relink:")] == [_ROW]
