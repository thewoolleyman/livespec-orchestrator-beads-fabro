"""Tests for the interim host-wide dispatch admission mutex."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_admission_mutex as mutex
from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop_command
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem


@dataclass(kw_only=True)
class _PsRunner:
    stdouts: list[str]
    exit_code: int = 0
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        self.calls.append(argv)
        stdout = self.stdouts.pop(0) if self.stdouts else json.dumps({"runs": []})
        return CommandResult(exit_code=self.exit_code, stdout=stdout, stderr="")


def _running_ps(*, run_id: str = "01RUNNING") -> str:
    return json.dumps([{"run_id": run_id, "status": "running"}])


def _empty_ps() -> str:
    return json.dumps({"runs": []})


def _repo_with_workflow(*, tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    workflow = tmp_path / "workflow.toml"
    _ = workflow.write_text(
        """
[workflow]
graph = "graph.toml"

[run.environment]
id = "fabro-sandbox"
""".lstrip(),
        encoding="utf-8",
    )
    return repo, workflow


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _item(*, item_id: str = "livespec-impl-beads-t1") -> WorkItem:
    return WorkItem(
        id=item_id,
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
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _lock_payload(*, pid: int, guard: str = "dispatch admission mutex") -> str:
    return json.dumps({"guard": guard, "pid": pid, "started_at_epoch": 1.0})


def test_claim_writes_pid_payload_and_release_removes_it(tmp_path: Path) -> None:
    claim = mutex.claim_dispatch_admission_mutex(
        repo=tmp_path, fabro_bin="fabro", runner=_PsRunner(stdouts=[_empty_ps()])
    )

    assert isinstance(claim, mutex.AdmissionMutexClaim)
    payload = json.loads(claim.path.read_text(encoding="utf-8"))
    assert payload["guard"] == "dispatch admission mutex"
    assert payload["pid"] == os.getpid()
    assert isinstance(payload["started_at_epoch"], float)

    mutex.release_dispatch_admission_mutex(claim=claim)

    assert not claim.path.exists()


def test_claim_refuses_immediately_when_any_run_is_running(tmp_path: Path) -> None:
    result = mutex.claim_dispatch_admission_mutex(
        repo=tmp_path, fabro_bin="fabro", runner=_PsRunner(stdouts=[_running_ps()])
    )

    assert isinstance(result, mutex.AdmissionMutexRefusal)
    assert result.run_id == "01RUNNING"
    assert "wait for run 01RUNNING to reach terminal state, then retry" in result.detail
    assert "bd-ib-sd8o is not done until deliverable (b)" in result.detail


def test_claim_refuses_live_pending_lock_without_running_run(tmp_path: Path) -> None:
    lock_path = mutex.admission_mutex_path(repo=tmp_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(_lock_payload(pid=os.getpid()), encoding="utf-8")

    result = mutex.claim_dispatch_admission_mutex(
        repo=tmp_path,
        fabro_bin="fabro",
        runner=_PsRunner(stdouts=[_empty_ps(), _empty_ps()]),
    )

    assert isinstance(result, mutex.AdmissionMutexRefusal)
    assert result.run_id is None
    assert f"pid {os.getpid()}" in result.detail


def test_claim_reclaims_dead_lock_when_no_run_is_running(tmp_path: Path) -> None:
    lock_path = mutex.admission_mutex_path(repo=tmp_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(_lock_payload(pid=999_999_999), encoding="utf-8")

    claim = mutex.claim_dispatch_admission_mutex(
        repo=tmp_path,
        fabro_bin="fabro",
        runner=_PsRunner(stdouts=[_empty_ps(), _empty_ps()]),
    )

    assert isinstance(claim, mutex.AdmissionMutexClaim)
    assert json.loads(lock_path.read_text(encoding="utf-8"))["pid"] == os.getpid()


def test_claim_reports_contention_when_post_reclaim_open_loses_race(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_path = mutex.admission_mutex_path(repo=tmp_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(_lock_payload(pid=999_999_999), encoding="utf-8")

    def refuse_open(*args: object) -> int:
        _ = args
        raise FileExistsError("replacement won")

    monkeypatch.setattr(mutex.os, "open", refuse_open)

    result = mutex.claim_dispatch_admission_mutex(
        repo=tmp_path,
        fabro_bin="fabro",
        runner=_PsRunner(stdouts=[_empty_ps()]),
    )

    assert isinstance(result, mutex.AdmissionMutexRefusal)
    assert "dispatch admission mutex" in result.detail


def test_claim_ignores_non_container_fabro_ps_payload(tmp_path: Path) -> None:
    claim = mutex.claim_dispatch_admission_mutex(
        repo=tmp_path, fabro_bin="fabro", runner=_PsRunner(stdouts=[json.dumps(7)])
    )

    assert isinstance(claim, mutex.AdmissionMutexClaim)


def test_claim_ignores_fabro_ps_entry_with_non_string_status(tmp_path: Path) -> None:
    claim = mutex.claim_dispatch_admission_mutex(
        repo=tmp_path,
        fabro_bin="fabro",
        runner=_PsRunner(stdouts=[json.dumps([{"run_id": "01ODD", "status": 7}])]),
    )

    assert isinstance(claim, mutex.AdmissionMutexClaim)


def test_claim_ignores_unparseable_fabro_ps_payload(tmp_path: Path) -> None:
    claim = mutex.claim_dispatch_admission_mutex(
        repo=tmp_path, fabro_bin="fabro", runner=_PsRunner(stdouts=["not json"])
    )

    assert isinstance(claim, mutex.AdmissionMutexClaim)


def test_claim_ignores_fabro_ps_entries_without_running_run_ids(tmp_path: Path) -> None:
    ps_json = json.dumps(
        [
            7,
            {"run_id": "", "status": "running"},
            {"run_id": "01BLOCKED", "status": {"kind": "blocked"}},
            {"run_id": "01UNKNOWN", "status": {"unexpected": "shape"}},
        ]
    )

    claim = mutex.claim_dispatch_admission_mutex(
        repo=tmp_path, fabro_bin="fabro", runner=_PsRunner(stdouts=[ps_json])
    )

    assert isinstance(claim, mutex.AdmissionMutexClaim)


def test_claim_ignores_fabro_ps_without_a_runs_list(tmp_path: Path) -> None:
    claim = mutex.claim_dispatch_admission_mutex(
        repo=tmp_path,
        fabro_bin="fabro",
        runner=_PsRunner(stdouts=[json.dumps({"runs": "not-a-list"})]),
    )

    assert isinstance(claim, mutex.AdmissionMutexClaim)


def test_claim_allows_admission_when_fabro_ps_is_unobservable(tmp_path: Path) -> None:
    claim = mutex.claim_dispatch_admission_mutex(
        repo=tmp_path,
        fabro_bin="fabro",
        runner=_PsRunner(stdouts=["not json"], exit_code=1),
    )

    assert isinstance(claim, mutex.AdmissionMutexClaim)


def test_claim_reports_no_pid_when_lock_path_is_unreadable(tmp_path: Path) -> None:
    lock_path = mutex.admission_mutex_path(repo=tmp_path)
    lock_path.mkdir(parents=True)
    lock_path.with_name(f"{lock_path.name}.reclaim").mkdir()

    result = mutex.claim_dispatch_admission_mutex(
        repo=tmp_path,
        fabro_bin="fabro",
        runner=_PsRunner(stdouts=[_empty_ps(), _empty_ps()]),
    )

    assert isinstance(result, mutex.AdmissionMutexRefusal)
    assert "no live pid recorded" in result.detail


def test_claim_reports_contention_when_reclaim_flock_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_path = mutex.admission_mutex_path(repo=tmp_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(_lock_payload(pid=999_999_999), encoding="utf-8")

    def deny_flock(*args: object) -> None:
        _ = args
        raise OSError("cannot lock")

    monkeypatch.setattr(mutex.fcntl, "flock", deny_flock)

    result = mutex.claim_dispatch_admission_mutex(
        repo=tmp_path,
        fabro_bin="fabro",
        runner=_PsRunner(stdouts=[_empty_ps(), _empty_ps()]),
    )

    assert isinstance(result, mutex.AdmissionMutexRefusal)
    assert "pid 999999999" in result.detail


@pytest.mark.parametrize("payload", ["not json", json.dumps({"pid": False})])
def test_claim_reports_no_pid_for_malformed_lock_payload(tmp_path: Path, payload: str) -> None:
    lock_path = mutex.admission_mutex_path(repo=tmp_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(payload, encoding="utf-8")

    result = mutex.claim_dispatch_admission_mutex(
        repo=tmp_path,
        fabro_bin="fabro",
        runner=_PsRunner(stdouts=[_empty_ps(), _empty_ps()]),
    )

    assert isinstance(result, mutex.AdmissionMutexRefusal)
    assert "no live pid recorded" in result.detail


def test_claim_preserves_replacement_when_stale_reclaim_races(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_path = mutex.admission_mutex_path(repo=tmp_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(_lock_payload(pid=999_999_999), encoding="utf-8")
    replacement = _lock_payload(pid=os.getpid(), guard="replacement")

    def replace_before_dead_report(*args: object) -> None:
        _ = args
        lock_path.write_text(replacement, encoding="utf-8")
        raise ProcessLookupError("dead")

    monkeypatch.setattr(mutex.os, "kill", replace_before_dead_report)

    result = mutex.claim_dispatch_admission_mutex(
        repo=tmp_path,
        fabro_bin="fabro",
        runner=_PsRunner(stdouts=[_empty_ps(), _empty_ps()]),
    )

    assert isinstance(result, mutex.AdmissionMutexRefusal)
    assert f"pid {os.getpid()}" in result.detail
    assert lock_path.read_text(encoding="utf-8") == replacement


def test_loop_refuses_running_fabro_run_before_dispatching(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item())
    runner = _PsRunner(stdouts=[_running_ps(run_id="fabro-run-01RUNNING")])
    monkeypatch.setattr(_dispatcher_loop_command, "ShellCommandRunner", lambda: runner)

    exit_code = main(
        argv=[
            "loop",
            "--repo",
            str(repo),
            "--budget",
            "1",
            "--workflow",
            str(workflow),
        ]
    )

    assert exit_code == 3
    captured = capsys.readouterr()
    assert "dispatch admission mutex" in captured.err
    assert "fabro-run-01RUNNING" in captured.err
    assert "wait for run fabro-run-01RUNNING to reach terminal state, then retry" in captured.err
    assert runner.calls == [["fabro", "ps", "-a", "--json"]]
    journal_records = [
        json.loads(line)
        for line in (repo / "tmp" / "fabro-dispatch-journal.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert any(
        record.get("stage") == "dispatch-admission-mutex"
        and record.get("guard") == "interim bd-ib-sd8o deliverable (c)"
        and record.get("run_id") == "fabro-run-01RUNNING"
        and record.get("refused") is True
        for record in journal_records
    )


def test_loop_refuses_missing_requested_item_before_dispatching(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item())
    runner = _PsRunner(stdouts=[_empty_ps()])
    monkeypatch.setattr(_dispatcher_loop_command, "ShellCommandRunner", lambda: runner)

    exit_code = main(
        argv=[
            "loop",
            "--repo",
            str(repo),
            "--budget",
            "1",
            "--workflow",
            str(workflow),
            "--item",
            "missing-item",
        ]
    )

    assert exit_code == 3
    assert "work-item(s) missing-item not found in the target-tenant" in capsys.readouterr().err
    assert runner.calls == []
