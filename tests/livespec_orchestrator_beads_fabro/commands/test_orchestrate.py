"""Tests for the minimal orchestrate operator surface."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import orchestrate
from livespec_orchestrator_beads_fabro.commands.orchestrate import (
    CommandRun,
    build_dispatcher_argv,
    main,
    plan_actions,
    run_action,
)
from livespec_orchestrator_beads_fabro.types import AuditRecord, StoreConfig, WorkItem


class _Runner:
    def __init__(self, *, results: list[CommandRun]) -> None:
        self.results = results
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, *, argv: tuple[str, ...], cwd: Path | None = None) -> CommandRun:
        self.calls.append(argv)
        _ = cwd
        return self.results.pop(0)


def _ok(payload: object, *, argv: tuple[str, ...] = ("cmd",)) -> CommandRun:
    return CommandRun(argv=argv, returncode=0, stdout=json.dumps(payload), stderr="")


def _store_config() -> StoreConfig:
    return StoreConfig(
        tenant="tenant",
        prefix="bd-ib",
        server_user="tenant",
        database="tenant",
        bd_path="bd",
        fake=True,
    )


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id="bd-ib-123",
        type="task",
        status="ready",
        title="A ready task",
        description="Do the thing.",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-06-11T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )
    return replace(base, **overrides)


def _audit(*, merge_sha: str = "abc123", pr_number: int | None = 7) -> AuditRecord:
    return AuditRecord(
        verification_timestamp="2026-06-11T01:00:00Z",
        commits=(),
        files_changed=(),
        merge_sha=merge_sha,
        pr_number=pr_number,
    )


def _wip_cap(value: int) -> object:
    def resolve(*, cwd: Path) -> int:
        _ = cwd
        return value

    return resolve


def _install_valve_store(
    monkeypatch: pytest.MonkeyPatch,
    *,
    items: list[WorkItem],
) -> list[dict[str, Any]]:
    updates: list[dict[str, Any]] = []
    config = _store_config()

    def fake_resolve_store_config(*, cwd: Path, work_items_arg: str | None) -> StoreConfig:
        _ = cwd
        _ = work_items_arg
        return config

    def fake_read_work_items(*, path: StoreConfig) -> list[WorkItem]:
        assert path is config
        return items

    def fake_update_work_item_status(
        *,
        path: StoreConfig,
        item_id: str,
        status: str,
        assignee: str | None = None,
    ) -> None:
        assert path is config
        updates.append({"item_id": item_id, "status": status, "assignee": assignee})

    monkeypatch.setattr(
        orchestrate, "resolve_store_config", fake_resolve_store_config, raising=False
    )
    monkeypatch.setattr(orchestrate, "read_work_items", fake_read_work_items, raising=False)
    monkeypatch.setattr(
        orchestrate, "update_work_item_status", fake_update_work_item_status, raising=False
    )
    return updates


def test_plan_actions_composes_spec_and_impl_next_candidates(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runner = _Runner(
        results=[
            _ok(
                {
                    "candidates": [
                        {
                            "action": "revise",
                            "urgency": "high",
                            "reason": "pending proposal",
                            "target": "proposed_changes/a.md",
                        }
                    ]
                }
            ),
            _ok(
                {
                    "candidates": [
                        {
                            "action": "implement",
                            "work_item_ref": "bd-ib-123",
                            "urgency": "medium",
                            "reason": "ready item",
                        }
                    ]
                }
            ),
        ]
    )

    plan = plan_actions(repo=repo, runner=runner)

    assert [action["id"] for action in plan["actions"]] == [
        "spec:revise:0",
        "impl:bd-ib-123",
    ]
    assert plan["summary"] == {
        "spec_actions": 1,
        "impl_actions": 1,
        "total_actions": 2,
    }
    assert plan["actions"][0]["handoff"] == "/livespec:revise --spec-target SPECIFICATION/"
    assert plan["actions"][1]["factory_safe"] is True


def test_plan_actions_surfaces_spec_only_candidates(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runner = _Runner(
        results=[
            _ok({"candidates": [{"action": "critique", "urgency": "low", "reason": "hygiene"}]}),
            _ok({"candidates": []}),
        ]
    )

    plan = plan_actions(repo=repo, runner=runner)

    assert [action["kind"] for action in plan["actions"]] == ["spec"]
    assert plan["summary"]["impl_actions"] == 0


def test_build_dispatcher_argv_uses_shadow_loop_for_selected_impl_item(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    dispatcher_bin = tmp_path / "dispatcher.py"

    argv = build_dispatcher_argv(
        repo=repo,
        dispatcher_bin=dispatcher_bin,
        work_item_ref="bd-ib-123",
    )

    assert argv == (
        "python3",
        str(dispatcher_bin),
        "loop",
        "--repo",
        str(repo),
        "--budget",
        "1",
        "--parallel",
        "1",
        "--mode",
        "shadow",
        "--item",
        "bd-ib-123",
        "--json",
    )


def test_run_action_dispatches_selected_impl_item(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    dispatcher_bin = tmp_path / "dispatcher.py"
    runner = _Runner(results=[_ok([{"work_item_id": "bd-ib-123", "status": "green"}])])

    result = run_action(
        repo=repo,
        action_id="impl:bd-ib-123",
        runner=runner,
        dispatcher_bin=dispatcher_bin,
    )

    assert result["status"] == "green"
    assert result["kind"] == "impl"
    assert result["work_item_ref"] == "bd-ib-123"
    assert runner.calls == [
        build_dispatcher_argv(
            repo=repo,
            dispatcher_bin=dispatcher_bin,
            work_item_ref="bd-ib-123",
        )
    ]


def test_run_action_surfaces_spec_actions_as_human_handoff(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runner = _Runner(results=[])

    result = run_action(repo=repo, action_id="spec:revise:0", runner=runner)

    assert result["status"] == "human-gated"
    assert result["handoff"] == "/livespec:revise --spec-target SPECIFICATION/"
    assert runner.calls == []


def test_run_action_approve_admits_manual_ready_item(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    updates = _install_valve_store(
        monkeypatch,
        items=[_item(admission_policy="manual"), _item(id="bd-ib-active", status="active")],
    )
    monkeypatch.setattr(orchestrate, "resolve_wip_cap", _wip_cap(2), raising=False)

    result = run_action(repo=repo, action_id="approve:bd-ib-123", runner=_Runner(results=[]))

    assert result["status"] == "green"
    assert updates == [{"item_id": "bd-ib-123", "status": "active", "assignee": "fabro"}]
    assert result["journal"] == {
        "actor": "operator",
        "stage": "human-valve-approve",
        "work_item_id": "bd-ib-123",
    }


def test_run_action_approve_refuses_when_wip_cap_full(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    updates = _install_valve_store(
        monkeypatch,
        items=[_item(admission_policy="manual"), _item(id="bd-ib-active", status="active")],
    )
    monkeypatch.setattr(orchestrate, "resolve_wip_cap", _wip_cap(1), raising=False)

    result = run_action(repo=repo, action_id="approve:bd-ib-123", runner=_Runner(results=[]))

    assert result["status"] == "failed"
    assert result["kind"] == "human-valve"
    assert result["domain_error"] == "wip-cap-exhausted"
    assert updates == []


def test_run_action_accept_transitions_acceptance_item_to_done(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    updates = _install_valve_store(monkeypatch, items=[_item(status="acceptance")])

    result = run_action(repo=repo, action_id="accept:bd-ib-123", runner=_Runner(results=[]))

    assert result["status"] == "green"
    assert updates == [{"item_id": "bd-ib-123", "status": "done", "assignee": None}]
    assert result["journal"] == {
        "actor": "operator",
        "stage": "human-valve-accept",
        "work_item_id": "bd-ib-123",
    }


def test_run_action_accept_refuses_non_acceptance_item(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    updates = _install_valve_store(monkeypatch, items=[_item(status="active")])

    result = run_action(repo=repo, action_id="accept:bd-ib-123", runner=_Runner(results=[]))

    assert result["status"] == "failed"
    assert result["domain_error"] == "invalid-source-state"
    assert "expected acceptance" in result["summary"]
    assert updates == []


@pytest.mark.parametrize(
    ("action_id", "target_status", "stage"),
    [
        ("reject:bd-ib-123:rework", "active", "human-valve-reject-rework"),
    ],
)
def test_run_action_reject_routes_acceptance_item(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    action_id: str,
    target_status: str,
    stage: str,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    updates = _install_valve_store(monkeypatch, items=[_item(status="acceptance")])

    result = run_action(repo=repo, action_id=action_id, runner=_Runner(results=[]))

    assert result["status"] == "green"
    assert updates == [{"item_id": "bd-ib-123", "status": target_status, "assignee": None}]
    assert result["journal"] == {
        "actor": "operator",
        "stage": stage,
        "work_item_id": "bd-ib-123",
    }


def test_run_action_reject_regroom_reverts_merged_change_before_backlog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    updates = _install_valve_store(
        monkeypatch,
        items=[_item(status="acceptance", audit=_audit(merge_sha="feed01"))],
    )
    runner = _Runner(results=[CommandRun(argv=("git",), returncode=0, stdout="", stderr="")])

    result = run_action(repo=repo, action_id="reject:bd-ib-123:regroom", runner=runner)

    assert result["status"] == "green"
    assert runner.calls == [("git", "revert", "--no-edit", "feed01")]
    assert updates == [{"item_id": "bd-ib-123", "status": "backlog", "assignee": None}]


def test_run_action_reject_refuses_non_acceptance_item(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    updates = _install_valve_store(monkeypatch, items=[_item(status="ready")])

    result = run_action(repo=repo, action_id="reject:bd-ib-123:rework", runner=_Runner(results=[]))

    assert result["status"] == "failed"
    assert result["domain_error"] == "invalid-source-state"
    assert updates == []


def test_main_plan_emits_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runner = _Runner(results=[_ok({"candidates": []}), _ok({"candidates": []})])

    exit_code = main(["plan", "--repo", str(repo), "--json"], runner=runner)

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["actions"] == []


def test_main_plan_empty_renders_no_actions_markdown(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runner = _Runner(results=[_ok({"candidates": []}), _ok({"candidates": []})])

    exit_code = main(["plan", "--repo", str(repo)], runner=runner)

    assert exit_code == 0
    out = capsys.readouterr().out
    assert out.lstrip().startswith("#")
    assert "No actions ready." in out


def test_main_run_impl_renders_markdown_with_dispatcher_exit_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runner = _Runner(results=[_ok([{"work_item_id": "bd-ib-123", "status": "green"}])])

    exit_code = main(["run", "--repo", str(repo), "--action", "impl:bd-ib-123"], runner=runner)

    assert exit_code == 0
    out = capsys.readouterr().out
    assert out.lstrip().startswith("#")
    assert "status: **green**" in out
    assert "dispatcher exit code: 0" in out


def test_main_run_spec_renders_markdown_handoff(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runner = _Runner(results=[])

    exit_code = main(["run", "--repo", str(repo), "--action", "spec:revise:0"], runner=runner)

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "status: **human-gated**" in out
    assert "handoff: `/livespec:revise --spec-target SPECIFICATION/`" in out
