"""Integration coverage for Scenario 150 plan-progress attention facts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import needs_attention
from livespec_orchestrator_beads_fabro.commands._plan_epoch_genesis import create_genesis_token
from livespec_orchestrator_beads_fabro.commands.needs_attention import build_attention
from livespec_orchestrator_beads_fabro.commands.plan import NextAction, append_handoff
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from livespec_runtime.needs_attention import SpecNextOutput

_NOW = "2026-10-20T12:00:00Z"
_OVERDUE_FACT_ID = "hygiene:overdue-result:bd-plan"


@pytest.fixture(autouse=True)
def _hermetic_fake_backend(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config(*, root: Path | None = None) -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
        repo_root=root,
    )


def _write_project(*, root: Path) -> None:
    (root / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {
                        "tenant": "livespec-impl-beads",
                        "prefix": "bd",
                        "server_user": "livespec-impl-beads",
                        "database": "livespec-impl-beads",
                        "bd_path": "bd",
                        "fake": True,
                    },
                    "dispatcher": {
                        "plan_progress_window_seconds": 3600,
                        "plan_progress_handoff_threshold": 2,
                    },
                }
            }
        ),
        encoding="utf-8",
    )


def _seed_plan(*, root: Path) -> None:
    append_work_item(
        path=_config(root=root),
        item=WorkItem(
            id="bd-plan",
            type="epic",
            status="backlog",
            title="Plan",
            description="d",
            origin="freeform",
            gap_id=None,
            rank="a1",
            assignee=None,
            depends_on=(),
            captured_at="2026-10-01T00:00:00Z",
            resolution=None,
            reason=None,
            audit=None,
            superseded_by=None,
            spec_commitment_hint="plan:scenario-150",
        ),
    )
    _ = create_genesis_token(config=_config(root=root), epic_id="bd-plan")
    append_handoff(
        config=_config(root=root),
        epic_id="bd-plan",
        body="Next action: recover the required result.",
        author="factory-test",
        now="2026-10-19T10:00:00Z",
        next_action=NextAction(
            kind="impl",
            ref="bd-plan",
            text="Recover the required result.",
            required_result={
                "repo": root.name,
                "item_status": {"item_id": "bd-plan", "status": "closed"},
            },
            budget={"deadline": "2026-10-20T11:00:00Z", "max_handoffs": 3},
        ),
    )


def _no_spec_next(*, project_root: Path) -> SpecNextOutput | None:
    _ = project_root
    return None


def test_an_expired_declared_result_remains_visible_after_ancillary_activity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_project(root=tmp_path)
    _seed_plan(root=tmp_path)
    monkeypatch.setattr(needs_attention, "spec_next", _no_spec_next)
    monkeypatch.setattr(needs_attention, "_utc_now_iso", lambda: _NOW)

    attention = build_attention(project_root=tmp_path, repo_name="repo", include_hygiene=False)

    [fact] = [item for item in attention if item.id == _OVERDUE_FACT_ID]
    assert "bd-plan" in fact.summary
    assert "closed" in fact.summary
    assert "2026-10-20T11:00:00Z" in fact.summary
    assert fact.handoff.action_id == "diagnose-plan-progress:bd-plan"
