"""Tests for the drive human-valve action cluster."""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, make_beads_client
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


def _fake() -> FakeBeadsClient:
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    return client


def _write_fake_config(repo: Path) -> None:
    (repo / ".livespec.jsonc").write_text(
        """{
  "livespec-orchestrator-beads-fabro": {
    "connection": {
      "tenant": "livespec-impl-beads",
      "prefix": "bd",
      "server_user": "livespec-impl-beads",
      "database": "livespec-impl-beads",
      "bd_path": "bd",
      "fake": true
    }
  }
}
""",
        encoding="utf-8",
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


def test_set_review_fix_cap_writes_label_and_leaves_status(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_fake_config(repo)
    append_work_item(path=_config(), item=_item())

    result = run_human_valve_action(repo=repo, action_id="set-review-fix-cap:bd-ib-ready:5")

    assert result["status"] == "green"
    assert result["target_status"] == "ready"
    assert "review-fix-cap:5" in _fake().show_issue(issue_id="bd-ib-ready")["labels"]


def test_set_merge_on_review_cap_writes_boolean_label(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_fake_config(repo)
    append_work_item(path=_config(), item=_item())

    result = run_human_valve_action(repo=repo, action_id="set-merge-on-review-cap:bd-ib-ready:true")

    assert result["status"] == "green"
    assert "merge-on-review-cap:true" in _fake().show_issue(issue_id="bd-ib-ready")["labels"]


def test_set_acceptance_rework_cap_writes_label(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_fake_config(repo)
    append_work_item(path=_config(), item=_item())

    result = run_human_valve_action(repo=repo, action_id="set-acceptance-rework-cap:bd-ib-ready:4")

    assert result["status"] == "green"
    assert "acceptance-rework-cap:4" in _fake().show_issue(issue_id="bd-ib-ready")["labels"]


def test_set_cap_refuses_invalid_value_and_writes_no_label(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_fake_config(repo)
    append_work_item(path=_config(), item=_item())

    result = run_human_valve_action(repo=repo, action_id="set-review-fix-cap:bd-ib-ready:0")

    assert result["status"] == "failed"
    assert result["domain_error"] == "invalid-cap-value"
    labels = _fake().show_issue(issue_id="bd-ib-ready")["labels"]
    assert not any(str(label).startswith("review-fix-cap:") for label in labels)


def test_set_cap_with_empty_item_is_unsupported(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_fake_config(repo)

    result = run_human_valve_action(repo=repo, action_id="set-review-fix-cap::5")

    assert result["status"] == "failed"
    assert result["domain_error"] == "invalid-action-id"


def test_move_transitions_item_to_allowed_status(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_fake_config(repo)
    append_work_item(path=_config(), item=_item())

    result = run_human_valve_action(repo=repo, action_id="move:bd-ib-ready:blocked")

    assert result["status"] == "green"
    assert result["target_status"] == "blocked"
    assert _fake().show_issue(issue_id="bd-ib-ready")["status"] == "blocked"


def test_move_refuses_forbidden_target_and_leaves_status(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_fake_config(repo)
    append_work_item(path=_config(), item=_item())

    result = run_human_valve_action(repo=repo, action_id="move:bd-ib-ready:done")

    assert result["status"] == "failed"
    assert result["domain_error"] == "forbidden-move-target"
    assert _fake().show_issue(issue_id="bd-ib-ready")["status"] == "ready"


def test_move_with_empty_item_is_unsupported(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_fake_config(repo)

    result = run_human_valve_action(repo=repo, action_id="move::ready")

    assert result["status"] == "failed"
    assert result["domain_error"] == "invalid-action-id"
