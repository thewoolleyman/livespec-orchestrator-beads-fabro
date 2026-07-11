"""Edge coverage for the drive command supervisor."""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _drive_valves as drive_valves
from livespec_orchestrator_beads_fabro.commands import drive
from livespec_orchestrator_beads_fabro.commands.drive import CommandRun
from livespec_orchestrator_beads_fabro.types import AuditRecord, StoreConfig, WorkItem


class _Runner:
    def __init__(self, *, results: list[CommandRun]) -> None:
        self.results = results
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, *, argv: tuple[str, ...], cwd: Path | None = None) -> CommandRun:
        self.calls.append(argv)
        _ = cwd
        return self.results.pop(0)


@dataclass(frozen=True, kw_only=True)
class _Completed:
    returncode: int
    stdout: str
    stderr: str


def _run(*, stdout: str, returncode: int = 0, stderr: str = "") -> CommandRun:
    return CommandRun(argv=("cmd",), returncode=returncode, stdout=stdout, stderr=stderr)


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


def _install_valve_store(
    monkeypatch: pytest.MonkeyPatch,
    *,
    items: list[WorkItem],
) -> list[tuple[str, str, str | None]]:
    updates: list[tuple[str, str, str | None]] = []
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
        updates.append((item_id, status, assignee))

    monkeypatch.setattr(drive_valves, "resolve_store_config", fake_resolve_store_config)
    monkeypatch.setattr(drive_valves.store, "read_work_items", fake_read_work_items)
    monkeypatch.setattr(drive_valves.store, "update_work_item_status", fake_update_work_item_status)
    return updates


def test_red_commit_wip_cap_helper_remains_covered(tmp_path: Path) -> None:
    module = importlib.import_module(
        "tests.livespec_orchestrator_beads_fabro.commands.test_drive_core"
    )
    resolver = module._wip_cap(3)  # noqa: SLF001 - cover byte-frozen Red helper from Green file.

    assert resolver(cwd=tmp_path) == 3


def test_run_human_valve_action_accept_success_updates_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    updates = _install_valve_store(monkeypatch, items=[_item(status="acceptance")])

    result = drive.run_human_valve_action(repo=repo, action_id="accept:bd-ib-123")

    assert result["status"] == "green"
    assert updates == [("bd-ib-123", "done", None)]


def test_run_human_valve_action_refuses_malformed_action(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    result = drive.run_human_valve_action(repo=repo, action_id="approve:")

    assert result == {
        "action_id": "approve:",
        "kind": "human-valve",
        "status": "failed",
        "domain_error": "invalid-action-id",
        "summary": "Unsupported human valve action id.",
    }


def test_run_human_valve_action_refuses_missing_item(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    updates = _install_valve_store(monkeypatch, items=[_item(id="bd-ib-other")])

    result = drive.run_human_valve_action(repo=repo, action_id="accept:bd-ib-123")

    assert result["status"] == "failed"
    assert result["domain_error"] == "work-item-not-found"
    assert "work_item_ref" not in result
    assert updates == []


def test_run_human_valve_action_approve_refuses_non_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    updates = _install_valve_store(monkeypatch, items=[_item(status="backlog")])

    result = drive.run_human_valve_action(repo=repo, action_id="approve:bd-ib-123")

    assert result["status"] == "failed"
    assert result["domain_error"] == "invalid-source-state"
    assert "expected pending-approval" in result["summary"]
    assert updates == []


def test_run_human_valve_action_approve_refuses_auto_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    updates = _install_valve_store(
        monkeypatch, items=[_item(status="pending-approval", admission_policy="auto")]
    )

    result = drive.run_human_valve_action(repo=repo, action_id="approve:bd-ib-123")

    assert result["status"] == "failed"
    assert result["domain_error"] == "invalid-source-state"
    assert "effective-manual" in result["summary"]
    assert updates == []


def test_run_human_valve_action_approve_refuses_ready_item(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    updates = _install_valve_store(monkeypatch, items=[_item(admission_policy="manual")])

    result = drive.run_human_valve_action(repo=repo, action_id="approve:bd-ib-123")

    assert result["status"] == "failed"
    assert result["domain_error"] == "invalid-source-state"
    assert "expected pending-approval" in result["summary"]
    assert updates == []


def test_run_human_valve_action_reject_regroom_refuses_when_revert_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    updates = _install_valve_store(
        monkeypatch, items=[_item(status="acceptance", audit=_audit(merge_sha="badc0de"))]
    )
    runner = _Runner(results=[CommandRun(argv=("git",), returncode=1, stdout="", stderr="boom")])

    result = drive.run_human_valve_action(
        repo=repo, action_id="reject:bd-ib-123:regroom", runner=runner
    )

    assert result["status"] == "failed"
    assert result["domain_error"] == "revert-failed"
    assert runner.calls == [("git", "revert", "--no-edit", "badc0de")]
    assert updates == []


def test_run_human_valve_action_reject_regroom_uses_default_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    updates = _install_valve_store(
        monkeypatch, items=[_item(status="acceptance", audit=_audit(merge_sha="feed01"))]
    )
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def fake_run(*args: object, **kwargs: object) -> _Completed:
        calls.append((args, kwargs))
        assert kwargs["cwd"] == repo
        assert kwargs["check"] is False
        assert kwargs["capture_output"] is True
        return _Completed(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(drive_valves, "run", fake_run)

    result = drive.run_human_valve_action(repo=repo, action_id="reject:bd-ib-123:regroom")

    assert result["status"] == "green"
    assert calls[0][0][0] == ("git", "revert", "--no-edit", "feed01")
    assert updates == [("bd-ib-123", "backlog", None)]


def test_run_human_valve_action_reject_regroom_without_audit_refuses_before_backlog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    updates = _install_valve_store(monkeypatch, items=[_item(status="acceptance")])
    runner = _Runner(results=[])

    result = drive.run_human_valve_action(
        repo=repo, action_id="reject:bd-ib-123:regroom", runner=runner
    )

    assert result["status"] == "failed"
    assert result["domain_error"] == "missing-merge-evidence"
    assert runner.calls == []
    assert updates == []


def test_run_action_rejects_unknown_action(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    result = drive.run_action(repo=repo, action_id="bogus", runner=_Runner(results=[]))

    assert result["status"] == "failed"
    assert result["kind"] == "unknown"


def test_run_action_reports_blocked_dispatch_with_default_dispatcher(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runner = _Runner(results=[_run(stdout=json.dumps([{"status": "blocked"}]), returncode=1)])

    result = drive.run_action(repo=repo, action_id="impl:bd-ib-123", runner=runner)

    assert result["status"] == "blocked"
    assert "human-gated blocked" in result["summary"]
    assert runner.calls[0][1].endswith("/bin/dispatcher.py")


def test_run_action_falls_back_to_failed_for_bad_dispatch_output(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runner = _Runner(results=[_run(stdout="not json", returncode=1)])

    result = drive.run_action(repo=repo, action_id="impl:bd-ib-123", runner=runner)

    assert result["status"] == "failed"
    assert "did not report green" in result["summary"]


def test_run_action_falls_back_to_green_for_missing_status(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runner = _Runner(results=[_run(stdout=json.dumps([{}]))])

    result = drive.run_action(repo=repo, action_id="impl:bd-ib-123", runner=runner)

    assert result["status"] == "green"


def test_run_action_ignores_non_dict_dispatch_entries(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runner = _Runner(results=[_run(stdout=json.dumps([1]), returncode=1)])

    result = drive.run_action(repo=repo, action_id="impl:bd-ib-123", runner=runner)

    assert result["status"] == "failed"


def test_main_missing_repo_returns_precondition(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing = tmp_path / "missing"

    exit_code = drive.main(argv=["--repo", str(missing), "--action", "impl:bd-ib-123", "--json"])

    assert exit_code == 3
    assert "does not exist" in capsys.readouterr().err


def test_main_run_returns_exit_failure_for_failed_dispatch(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runner = _Runner(results=[_run(stdout="not json", returncode=1)])

    exit_code = drive.main(
        argv=["--repo", str(repo), "--action", "impl:bd-ib-123"],
        runner=runner,
    )

    assert exit_code == 1
    assert "did not report green" in capsys.readouterr().out


def test_red_commit_runner_helper_remains_covered() -> None:
    module = importlib.import_module("tests.livespec_orchestrator_beads_fabro.commands.test_drive")
    runner = module._Runner(  # noqa: SLF001 - cover byte-frozen Red helper.
        results=[CommandRun(argv=("cmd",), returncode=0, stdout="[]", stderr="")]
    )

    result = runner(argv=("cmd",), cwd=None)

    assert result.returncode == 0
    assert runner.calls == [("cmd",)]


def test_run_action_without_injected_runner_uses_subprocess_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    calls: list[tuple[object, ...]] = []

    def fake_run(*args: object, **kwargs: object) -> _Completed:
        calls.append(args)
        assert kwargs["cwd"] == repo
        assert kwargs["check"] is False
        assert kwargs["capture_output"] is True
        return _Completed(returncode=0, stdout=json.dumps([{"status": "green"}]), stderr="")

    monkeypatch.setattr(drive.subprocess, "run", fake_run)

    result = drive.run_action(repo=repo, action_id="impl:bd-ib-123")

    assert result["status"] == "green"
    assert calls[0][0][0] == "python3"


def test_main_without_action_reports_usage(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        drive.main(argv=[])

    assert exc_info.value.code == 2
    assert "the following arguments are required: --action" in capsys.readouterr().err


def test_main_unknown_action_renders_markdown_without_dispatcher(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    exit_code = drive.main(argv=["--repo", str(repo), "--action", "bogus"])

    assert exit_code == 1
    out = capsys.readouterr().out
    assert "# drive" in out
    assert "dispatcher exit code" not in out
