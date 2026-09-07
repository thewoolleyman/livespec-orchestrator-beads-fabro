"""Tests for the drive human-valve action cluster."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, make_beads_client
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import InvokerIdentity
from livespec_orchestrator_beads_fabro.commands._drive_valves import run_human_valve_action
from livespec_orchestrator_beads_fabro.commands.drive import run_action
from livespec_orchestrator_beads_fabro.store import append_work_item, read_work_item_comments
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


def _human() -> InvokerIdentity:
    """A press asserting a named human operator.

    Required by any press carrying an answer since v104 gated who may answer an
    attention item: the effective answer disposition admits only the `human`
    role, and an invocation asserting nothing resolves to the unattributed MARK
    (`test_drive_answer_disposition` owns that gate's own coverage).
    """
    return InvokerIdentity(invoker="human:cw", invoker_source="flag")


def _write_fake_config(repo: Path, *, auto_approve_ready: bool = False) -> None:
    dispatcher = (
        f""",
    "dispatcher": {{
      "auto_approve_ready": {str(auto_approve_ready).lower()}
    }}"""
        if auto_approve_ready
        else ""
    )
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
    }"""
        + dispatcher
        + """
  }
}
""",
        encoding="utf-8",
    )


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
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
    return replace(base, **overrides)


def test_approve_refuses_unlabeled_pending_item_when_global_auto_enabled(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_fake_config(repo, auto_approve_ready=True)
    append_work_item(
        path=_config(),
        item=_item(status="pending-approval", admission_policy=None),
    )

    result = run_human_valve_action(repo=repo, action_id="approve:bd-ib-ready")

    assert result["status"] == "failed"
    assert result["domain_error"] == "invalid-source-state"
    assert _fake().show_issue(issue_id="bd-ib-ready")["status"] == "pending-approval"


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


def test_run_human_valve_action_refuses_unknown_value_action(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    result = run_human_valve_action(repo=repo, action_id="unsupported:bd-ib-ready:value")

    assert result == {
        "action_id": "unsupported:bd-ib-ready:value",
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


def test_resolve_blocked_writes_the_answer_before_the_transition(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_fake_config(repo)
    append_work_item(
        path=_config(),
        item=_item(id="bd-ib-nh", status="blocked", blocked_reason="needs-human"),
    )

    result = run_human_valve_action(
        repo=repo,
        action_id="resolve-blocked:bd-ib-nh:ready",
        identity=_human(),
        answer="Take option B; the guard stays fail-closed.",
    )

    assert result["status"] == "green"
    assert result["target_status"] == "ready"
    assert "the answer is on the ledger" in result["summary"]
    assert _fake().show_issue(issue_id="bd-ib-nh")["status"] == "ready"
    [comment] = read_work_item_comments(path=_config(), work_item_id="bd-ib-nh")
    assert "Take option B; the guard stays fail-closed." in comment.text


def test_resolve_blocked_without_an_answer_writes_no_comment(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_fake_config(repo)
    append_work_item(
        path=_config(),
        item=_item(id="bd-ib-nh2", status="blocked", blocked_reason="needs-human"),
    )

    result = run_human_valve_action(repo=repo, action_id="resolve-blocked:bd-ib-nh2:backlog")

    assert result["status"] == "green"
    assert result["summary"] == "Resolved bd-ib-nh2: blocked -> backlog."
    assert read_work_item_comments(path=_config(), work_item_id="bd-ib-nh2") == ()


def test_a_poisoned_answer_leaves_the_item_blocked(tmp_path: Path) -> None:
    """The refusal is free: nothing moved, so the operator rewords and re-runs."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_fake_config(repo)
    append_work_item(
        path=_config(),
        item=_item(id="bd-ib-nh3", status="blocked", blocked_reason="needs-human"),
    )

    result = run_human_valve_action(
        repo=repo,
        action_id="resolve-blocked:bd-ib-nh3:ready",
        identity=_human(),
        answer="run " + "{" + "{ recipe }}",
    )

    assert result["status"] == "failed"
    assert result["domain_error"] == "answer-would-poison-goal"
    assert _fake().show_issue(issue_id="bd-ib-nh3")["status"] == "blocked"
    assert read_work_item_comments(path=_config(), work_item_id="bd-ib-nh3") == ()


def test_an_answer_to_a_non_blocked_item_is_refused_before_it_is_written(
    tmp_path: Path,
) -> None:
    """The source-state guard runs first, so a mis-aimed answer writes nothing."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_fake_config(repo)
    append_work_item(path=_config(), item=_item())

    result = run_human_valve_action(
        repo=repo, action_id="resolve-blocked:bd-ib-ready:ready", answer="Take option B."
    )

    assert result["domain_error"] == "invalid-source-state"
    assert read_work_item_comments(path=_config(), work_item_id="bd-ib-ready") == ()


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


def test_set_cap_clear_removes_the_override_and_inherits_global(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_fake_config(repo)
    append_work_item(path=_config(), item=_item())
    run_human_valve_action(repo=repo, action_id="set-review-fix-cap:bd-ib-ready:5")

    result = run_human_valve_action(repo=repo, action_id="set-review-fix-cap:bd-ib-ready:clear")

    assert result["status"] == "green"
    assert "inherits global default" in result["summary"]
    labels = _fake().show_issue(issue_id="bd-ib-ready")["labels"]
    assert not any(str(label).startswith("review-fix-cap:") for label in labels)


def test_set_cap_clear_when_absent_is_a_green_noop(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_fake_config(repo)
    append_work_item(path=_config(), item=_item())

    result = run_human_valve_action(
        repo=repo, action_id="set-merge-on-review-cap:bd-ib-ready:clear"
    )

    assert result["status"] == "green"
    labels = _fake().show_issue(issue_id="bd-ib-ready")["labels"]
    assert not any(str(label).startswith("merge-on-review-cap:") for label in labels)


def test_move_transitions_item_to_allowed_status(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_fake_config(repo)
    append_work_item(path=_config(), item=_item())

    result = run_human_valve_action(repo=repo, action_id="move:bd-ib-ready:blocked")

    assert result["status"] == "green"
    assert result["target_status"] == "blocked"
    assert _fake().show_issue(issue_id="bd-ib-ready")["status"] == "blocked"


def test_move_from_active_to_ready_clears_factory_assignee(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_fake_config(repo)
    append_work_item(path=_config(), item=_item(status="active", assignee="fabro"))

    result = run_human_valve_action(repo=repo, action_id="move:bd-ib-ready:ready")

    assert result["status"] == "green"
    [read_back] = _fake().list_issues()
    assert read_back["status"] == "ready"
    assert read_back["assignee"] is None


def test_move_refuses_active_target_from_every_source_lane(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_fake_config(repo)
    source_statuses = (
        "backlog",
        "ready",
        "blocked",
        "active",
        "acceptance",
        "pending-approval",
    )
    for source_status in source_statuses:
        item_id = f"bd-ib-{source_status.replace('-', '')}"
        append_work_item(path=_config(), item=_item(id=item_id, status=source_status))

        result = run_human_valve_action(repo=repo, action_id=f"move:{item_id}:active")

        assert result["status"] == "failed"
        assert result["domain_error"] == "forbidden-move-target"
        assert "'active' is not an operator-movable target" in result["summary"]
        assert _fake().show_issue(issue_id=item_id)["status"] == source_status


def test_move_keeps_backlog_ready_and_blocked_targets_allowed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_fake_config(repo)
    allowed_targets = ("backlog", "ready", "blocked")
    for target_status in allowed_targets:
        item_id = f"bd-ib-move-{target_status}"
        append_work_item(
            path=_config(),
            item=_item(id=item_id, status="pending-approval"),
        )

        result = run_human_valve_action(repo=repo, action_id=f"move:{item_id}:{target_status}")

        assert result["status"] == "green"
        assert result["target_status"] == target_status
        assert _fake().show_issue(issue_id=item_id)["status"] == target_status


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


class _NoPullRequestRunner:
    """A forge that reports no pull request, so the valve's ledger half stands alone."""

    def __call__(self, *, argv: tuple[str, ...], cwd: Path | None = None) -> _NoPullRequest:
        _ = (argv, cwd)
        return _NoPullRequest()


@dataclass(frozen=True, kw_only=True)
class _NoPullRequest:
    returncode: int = 1
    stdout: str = ""
    stderr: str = ""


def test_drive_accepts_the_twelfth_action_and_routes_it_to_the_merge_hold_valve(
    tmp_path: Path,
) -> None:
    """`drive`'s own grammar, not just the valve router, admits `set-merge-hold:`."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_fake_config(repo)
    append_work_item(path=_config(), item=_item(status="active"))

    result = run_action(
        repo=repo, action_id="set-merge-hold:bd-ib-ready:on", runner=_NoPullRequestRunner()
    )

    assert result["kind"] == "human-valve"
    assert "merge-hold:on" in _fake().show_issue(issue_id="bd-ib-ready")["labels"]
    assert _fake().show_issue(issue_id="bd-ib-ready")["status"] == "active"
