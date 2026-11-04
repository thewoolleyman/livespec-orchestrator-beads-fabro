"""The human valve that relinks a held item to its filed proposed change."""

from __future__ import annotations

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_comments import (
    append_work_item_comment,
    read_work_item_comments,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import InvokerIdentity
from livespec_orchestrator_beads_fabro.commands._drive_valves import run_human_valve_action
from livespec_orchestrator_beads_fabro.commands._spec_change_tier import (
    SpecChangeTierDecision,
    behaviour_digest,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_record import (
    STAGE_FILING,
    recorded_spec_change_tier,
    spec_change_tier_comment,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from livespec_runtime.spec_stated import SpecStatedVerdict

_ITEM = "bd-ib-relink"
_ORIGINAL_TOPIC = "a-held-spec-change-tier"
_REPLACEMENT_TOPIC = "filed-under-a-different-stem"
_ACTOR = InvokerIdentity(invoker="human:chad", invoker_source="flag")


@pytest.fixture(autouse=True)
def _fake_beads_env(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _item(*, held: bool = True) -> WorkItem:
    item = WorkItem(
        id=_ITEM,
        type="feature",
        status="pending-approval",
        title="A held spec change tier item needs a relink",
        description="## Definition of Done\n\n- The linked topic is replaced.\n",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-03T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )
    append_work_item(path=_config(), item=item)
    if held:
        append_work_item_comment(
            path=_config(),
            work_item_id=_ITEM,
            body=spec_change_tier_comment(
                item_id=_ITEM,
                stage=STAGE_FILING,
                decision=SpecChangeTierDecision(
                    tier="spec-change",
                    classification="feature",
                    verdict=SpecStatedVerdict(
                        kind="unstated",
                        stated_by=(),
                        generalization_target="## Governing clause",
                        rationale="not stated",
                    ),
                    linked_proposal_topic=_ORIGINAL_TOPIC,
                ),
                spec_version="1",
                digest=behaviour_digest(item=item),
            ),
        )
    return item


def _repo(*, tmp_path: Path, topic: str | None = _REPLACEMENT_TOPIC) -> Path:
    repo = tmp_path / "repo"
    changes = repo / "SPECIFICATION" / "proposed_changes"
    changes.mkdir(parents=True)
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {'
        '"tenant": "livespec-impl-beads", "prefix": "bd-ib", '
        '"server_user": "livespec-impl-beads", "database": "livespec-impl-beads", '
        '"bd_path": "bd", "fake": true}}}',
        encoding="utf-8",
    )
    if topic is not None:
        _ = (changes / f"{topic}.md").write_text("proposal\n", encoding="utf-8")
    return repo


def _comments() -> tuple[str, ...]:
    return tuple(
        comment.text for comment in read_work_item_comments(path=_config(), work_item_id=_ITEM)
    )


def test_a_held_item_is_relinked_to_the_file_stem_and_records_the_actor(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _item()

    result = run_human_valve_action(
        repo=repo,
        action_id=f"relink-spec-tier:{_ITEM}:{_REPLACEMENT_TOPIC}",
        identity=_ACTOR,
    )

    assert result["status"] == "green", result
    recorded = recorded_spec_change_tier(comments=_comments())
    assert recorded is not None
    assert recorded.linked_proposal_topic == _REPLACEMENT_TOPIC
    assert "actor: human:chad" in _comments()[-1]
    assert f"previous-topic: {_ORIGINAL_TOPIC}" in _comments()[-1]
    assert f"replacement-topic: {_REPLACEMENT_TOPIC}" in _comments()[-1]


@pytest.mark.parametrize(
    ("state", "topic", "error"),
    [
        ("unheld", _REPLACEMENT_TOPIC, "not-held"),
        ("held", "missing-proposal", "unknown-topic"),
        ("held", "Not Canonical", "non-canonical-topic"),
    ],
)
def test_relink_refusals_leave_the_item_comments_unchanged(
    tmp_path: Path, state: str, topic: str, error: str
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _item(held=state == "held")
    before = _comments()

    result = run_human_valve_action(
        repo=repo,
        action_id=f"relink-spec-tier:{_ITEM}:{topic}",
        identity=_ACTOR,
    )

    assert result["domain_error"] == error
    assert _comments() == before
