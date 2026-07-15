"""Tests for the drive human-valve action cluster."""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._drive_valves import run_human_valve_action
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-ready",
        type="task",
        status="ready",
        title="Ready",
        description="d",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-07-10T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def test_run_human_valve_action_refuses_malformed_action(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    result = run_human_valve_action(repo=repo, action_id="approve:")

    assert result == {
        "action_id": "approve:",
        "kind": "human-valve",
        "status": "failed",
        "domain_error": "invalid-action-id",
        "summary": "Unsupported human valve action id.",
    }


def test_resolve_blocked_refuses_non_blocked_source_state(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".livespec.jsonc").write_text(
        """{
  \"livespec-orchestrator-beads-fabro\": {
    \"connection\": {
      \"tenant\": \"livespec-impl-beads\",
      \"prefix\": \"bd\",
      \"server_user\": \"livespec-impl-beads\",
      \"database\": \"livespec-impl-beads\",
      \"bd_path\": \"bd\",
      \"fake\": true
    }
  }
}
""",
        encoding="utf-8",
    )
    append_work_item(path=_config(), item=_item())

    result = run_human_valve_action(repo=repo, action_id="resolve-blocked:bd-ib-ready:ready")

    assert result == {
        "action_id": "resolve-blocked:bd-ib-ready:ready",
        "kind": "human-valve",
        "status": "failed",
        "domain_error": "invalid-source-state",
        "summary": "resolve-blocked requires a blocked needs-human item.",
        "work_item_ref": "bd-ib-ready",
    }
