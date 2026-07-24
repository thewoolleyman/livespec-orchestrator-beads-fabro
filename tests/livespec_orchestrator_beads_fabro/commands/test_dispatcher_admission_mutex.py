"""Tests for the host-level dispatch admission cap (spec v047).

The counting successor of the interim binary admission mutex (bd-ib-sd8o
deliverable (b)): two independent gauges — live capacity slot claims and
observed RUNNING Fabro runs — each capped by `dispatcher.host_dispatch_cap`.
"""

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

_GUARD = "dispatch admission cap"


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


def _running_ps(*run_ids: str) -> str:
    return json.dumps([{"run_id": run_id, "status": "running"} for run_id in run_ids])


def _empty_ps() -> str:
    return json.dumps({"runs": []})


def _repo_with_workflow(
    *, tmp_path: Path, host_dispatch_cap: int | None = None
) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    dispatcher_block = (
        ""
        if host_dispatch_cap is None
        else f', "dispatcher": {{"host_dispatch_cap": {host_dispatch_cap}}}'
    )
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}'
        + dispatcher_block
        + "}}",
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


def _lock_payload(*, pid: int, guard: str = _GUARD) -> str:
    return json.dumps({"guard": guard, "pid": pid, "started_at_epoch": 1.0})


def _slot(*, repo: Path, slot: int) -> Path:
    return repo / "tmp" / f"fabro-dispatch-admission.slot{slot}.lock"


def test_counting_cap_slot_surface_is_implemented() -> None:
    slot_path = getattr(mutex, "admission_mutex_slot_path", None)
    assert slot_path is not None, (
        "host_dispatch_cap counting-cap slot surface is unimplemented "
        "(bd-ib-sd8o deliverable (b), spec v047 "
        '§"Host-level dispatch concurrency cap (`host_dispatch_cap`)")'
    )
    assert slot_path(repo=Path("/r"), slot=0) == Path("/r/tmp/fabro-dispatch-admission.slot0.lock")
    assert slot_path(repo=Path("/r"), slot=1) == Path("/r/tmp/fabro-dispatch-admission.slot1.lock")


def test_claim_writes_pid_payload_and_release_removes_it(tmp_path: Path) -> None:
    claim = mutex.claim_dispatch_admission_mutex(
        repo=tmp_path, fabro_bin="fabro", runner=_PsRunner(stdouts=[_empty_ps()]), cap=2
    )

    assert isinstance(claim, mutex.AdmissionMutexClaim)
    assert claim.path == _slot(repo=tmp_path, slot=0)
    payload = json.loads(claim.path.read_text(encoding="utf-8"))
    assert payload["guard"] == _GUARD
    assert payload["pid"] == os.getpid()
    assert isinstance(payload["started_at_epoch"], float)

    mutex.release_dispatch_admission_mutex(claim=claim)

    assert not claim.path.exists()


def test_claim_admits_alongside_one_running_run_under_cap_two(tmp_path: Path) -> None:
    claim = mutex.claim_dispatch_admission_mutex(
        repo=tmp_path,
        fabro_bin="fabro",
        runner=_PsRunner(stdouts=[_running_ps("01RUNNING")]),
        cap=2,
    )

    assert isinstance(claim, mutex.AdmissionMutexClaim)
    assert claim.path == _slot(repo=tmp_path, slot=0)


def test_second_claim_takes_next_free_slot(tmp_path: Path) -> None:
    first = mutex.claim_dispatch_admission_mutex(
        repo=tmp_path, fabro_bin="fabro", runner=_PsRunner(stdouts=[_empty_ps()]), cap=2
    )
    second = mutex.claim_dispatch_admission_mutex(
        repo=tmp_path, fabro_bin="fabro", runner=_PsRunner(stdouts=[_empty_ps()]), cap=2
    )

    assert isinstance(first, mutex.AdmissionMutexClaim)
    assert isinstance(second, mutex.AdmissionMutexClaim)
    assert first.path == _slot(repo=tmp_path, slot=0)
    assert second.path == _slot(repo=tmp_path, slot=1)
    assert first.path.exists()
    assert second.path.exists()


def test_claim_refuses_when_running_runs_meet_cap(tmp_path: Path) -> None:
    result = mutex.claim_dispatch_admission_mutex(
        repo=tmp_path,
        fabro_bin="fabro",
        runner=_PsRunner(stdouts=[_running_ps("01AAA", "01BBB")]),
        cap=2,
    )

    assert isinstance(result, mutex.AdmissionMutexRefusal)
    assert result.run_id == "01AAA"
    assert "2 Fabro run(s) already in flight (01AAA, 01BBB)" in result.detail
    assert "host dispatch cap (2)" in result.detail
    assert "reach terminal state" in result.detail
    assert "dispatcher.host_dispatch_cap" in result.detail
    assert "config-only" in result.detail
    assert "bd-ib-sd8o deliverable (b)" in result.detail
    assert not _slot(repo=tmp_path, slot=0).exists()


def test_parked_blocked_run_never_counts_toward_the_cap(tmp_path: Path) -> None:
    ps_json = json.dumps(
        [
            {"run_id": "01PARKED", "status": {"kind": "blocked"}},
            {"run_id": "01RUNNING", "status": "running"},
        ]
    )

    claim = mutex.claim_dispatch_admission_mutex(
        repo=tmp_path, fabro_bin="fabro", runner=_PsRunner(stdouts=[ps_json]), cap=2
    )

    assert isinstance(claim, mutex.AdmissionMutexClaim)


def test_claim_refuses_when_all_slots_are_held_live(tmp_path: Path) -> None:
    slot_zero = _slot(repo=tmp_path, slot=0)
    slot_zero.parent.mkdir(parents=True, exist_ok=True)
    slot_zero.write_text(_lock_payload(pid=os.getpid()), encoding="utf-8")

    result = mutex.claim_dispatch_admission_mutex(
        repo=tmp_path,
        fabro_bin="fabro",
        runner=_PsRunner(stdouts=[_empty_ps(), _empty_ps()]),
        cap=1,
    )

    assert isinstance(result, mutex.AdmissionMutexRefusal)
    assert result.run_id is None
    assert "all 1 admission capacity slot(s) are held" in result.detail
    assert f"slot 0: pid {os.getpid()}" in result.detail
    assert "dispatcher.host_dispatch_cap" in result.detail
    assert "config-only" in result.detail


def test_claim_reclaims_dead_slot_when_capacity_is_free(tmp_path: Path) -> None:
    slot_zero = _slot(repo=tmp_path, slot=0)
    slot_zero.parent.mkdir(parents=True, exist_ok=True)
    slot_zero.write_text(_lock_payload(pid=999_999_999), encoding="utf-8")

    claim = mutex.claim_dispatch_admission_mutex(
        repo=tmp_path,
        fabro_bin="fabro",
        runner=_PsRunner(stdouts=[_empty_ps(), _empty_ps()]),
        cap=1,
    )

    assert isinstance(claim, mutex.AdmissionMutexClaim)
    assert claim.path == slot_zero
    assert json.loads(slot_zero.read_text(encoding="utf-8"))["pid"] == os.getpid()


def test_dead_slot_zero_is_reclaimed_before_slot_one_is_considered(tmp_path: Path) -> None:
    slot_zero = _slot(repo=tmp_path, slot=0)
    slot_zero.parent.mkdir(parents=True, exist_ok=True)
    slot_zero.write_text(_lock_payload(pid=999_999_999), encoding="utf-8")

    claim = mutex.claim_dispatch_admission_mutex(
        repo=tmp_path, fabro_bin="fabro", runner=_PsRunner(stdouts=[_empty_ps()]), cap=2
    )

    assert isinstance(claim, mutex.AdmissionMutexClaim)
    assert claim.path == slot_zero
    assert not _slot(repo=tmp_path, slot=1).exists()


def test_live_slot_zero_overflows_to_slot_one_under_cap_two(tmp_path: Path) -> None:
    slot_zero = _slot(repo=tmp_path, slot=0)
    slot_zero.parent.mkdir(parents=True, exist_ok=True)
    slot_zero.write_text(_lock_payload(pid=os.getpid()), encoding="utf-8")

    claim = mutex.claim_dispatch_admission_mutex(
        repo=tmp_path, fabro_bin="fabro", runner=_PsRunner(stdouts=[_empty_ps()]), cap=2
    )

    assert isinstance(claim, mutex.AdmissionMutexClaim)
    assert claim.path == _slot(repo=tmp_path, slot=1)
    assert json.loads(slot_zero.read_text(encoding="utf-8"))["pid"] == os.getpid()


def test_claim_reports_contention_when_post_reclaim_open_loses_race(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slot_zero = _slot(repo=tmp_path, slot=0)
    slot_zero.parent.mkdir(parents=True, exist_ok=True)
    slot_zero.write_text(_lock_payload(pid=999_999_999), encoding="utf-8")

    def refuse_open(*args: object) -> int:
        _ = args
        raise FileExistsError("replacement won")

    monkeypatch.setattr(mutex.os, "open", refuse_open)

    result = mutex.claim_dispatch_admission_mutex(
        repo=tmp_path,
        fabro_bin="fabro",
        runner=_PsRunner(stdouts=[_empty_ps()]),
        cap=1,
    )

    assert isinstance(result, mutex.AdmissionMutexRefusal)
    assert _GUARD in result.detail


def test_claim_ignores_non_container_fabro_ps_payload(tmp_path: Path) -> None:
    claim = mutex.claim_dispatch_admission_mutex(
        repo=tmp_path, fabro_bin="fabro", runner=_PsRunner(stdouts=[json.dumps(7)]), cap=2
    )

    assert isinstance(claim, mutex.AdmissionMutexClaim)


def test_claim_ignores_fabro_ps_entry_with_non_string_status(tmp_path: Path) -> None:
    claim = mutex.claim_dispatch_admission_mutex(
        repo=tmp_path,
        fabro_bin="fabro",
        runner=_PsRunner(stdouts=[json.dumps([{"run_id": "01ODD", "status": 7}])]),
        cap=2,
    )

    assert isinstance(claim, mutex.AdmissionMutexClaim)


def test_claim_ignores_unparseable_fabro_ps_payload(tmp_path: Path) -> None:
    claim = mutex.claim_dispatch_admission_mutex(
        repo=tmp_path, fabro_bin="fabro", runner=_PsRunner(stdouts=["not json"]), cap=2
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
        repo=tmp_path, fabro_bin="fabro", runner=_PsRunner(stdouts=[ps_json]), cap=1
    )

    assert isinstance(claim, mutex.AdmissionMutexClaim)


def test_claim_ignores_fabro_ps_without_a_runs_list(tmp_path: Path) -> None:
    claim = mutex.claim_dispatch_admission_mutex(
        repo=tmp_path,
        fabro_bin="fabro",
        runner=_PsRunner(stdouts=[json.dumps({"runs": "not-a-list"})]),
        cap=2,
    )

    assert isinstance(claim, mutex.AdmissionMutexClaim)


def test_claim_allows_admission_when_fabro_ps_is_unobservable(tmp_path: Path) -> None:
    claim = mutex.claim_dispatch_admission_mutex(
        repo=tmp_path,
        fabro_bin="fabro",
        runner=_PsRunner(stdouts=["not json"], exit_code=1),
        cap=2,
    )

    assert isinstance(claim, mutex.AdmissionMutexClaim)


def test_claim_reports_no_pid_when_slot_path_is_unreadable(tmp_path: Path) -> None:
    slot_zero = _slot(repo=tmp_path, slot=0)
    slot_zero.mkdir(parents=True)
    slot_zero.with_name(f"{slot_zero.name}.reclaim").mkdir()

    result = mutex.claim_dispatch_admission_mutex(
        repo=tmp_path,
        fabro_bin="fabro",
        runner=_PsRunner(stdouts=[_empty_ps(), _empty_ps()]),
        cap=1,
    )

    assert isinstance(result, mutex.AdmissionMutexRefusal)
    assert "slot 0: no live pid recorded" in result.detail


def test_claim_reports_contention_when_reclaim_flock_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slot_zero = _slot(repo=tmp_path, slot=0)
    slot_zero.parent.mkdir(parents=True, exist_ok=True)
    slot_zero.write_text(_lock_payload(pid=999_999_999), encoding="utf-8")

    def deny_flock(*args: object) -> None:
        _ = args
        raise OSError("cannot lock")

    monkeypatch.setattr(mutex.fcntl, "flock", deny_flock)

    result = mutex.claim_dispatch_admission_mutex(
        repo=tmp_path,
        fabro_bin="fabro",
        runner=_PsRunner(stdouts=[_empty_ps(), _empty_ps()]),
        cap=1,
    )

    assert isinstance(result, mutex.AdmissionMutexRefusal)
    assert "slot 0: pid 999999999" in result.detail


def test_slot_with_eperm_pid_probe_reads_held(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slot_zero = _slot(repo=tmp_path, slot=0)
    slot_zero.parent.mkdir(parents=True, exist_ok=True)
    slot_zero.write_text(_lock_payload(pid=999_999_999), encoding="utf-8")

    def eperm_kill(*args: object) -> None:
        _ = args
        raise PermissionError("foreign owner")

    monkeypatch.setattr(mutex.os, "kill", eperm_kill)

    result = mutex.claim_dispatch_admission_mutex(
        repo=tmp_path,
        fabro_bin="fabro",
        runner=_PsRunner(stdouts=[_empty_ps(), _empty_ps()]),
        cap=1,
    )

    assert isinstance(result, mutex.AdmissionMutexRefusal)
    assert "slot 0: pid 999999999" in result.detail


@pytest.mark.parametrize("payload", ["not json", json.dumps({"pid": False})])
def test_claim_reports_no_pid_for_malformed_slot_payload(tmp_path: Path, payload: str) -> None:
    slot_zero = _slot(repo=tmp_path, slot=0)
    slot_zero.parent.mkdir(parents=True, exist_ok=True)
    slot_zero.write_text(payload, encoding="utf-8")

    result = mutex.claim_dispatch_admission_mutex(
        repo=tmp_path,
        fabro_bin="fabro",
        runner=_PsRunner(stdouts=[_empty_ps(), _empty_ps()]),
        cap=1,
    )

    assert isinstance(result, mutex.AdmissionMutexRefusal)
    assert "slot 0: no live pid recorded" in result.detail


def test_claim_preserves_replacement_when_stale_reclaim_races(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slot_zero = _slot(repo=tmp_path, slot=0)
    slot_zero.parent.mkdir(parents=True, exist_ok=True)
    slot_zero.write_text(_lock_payload(pid=999_999_999), encoding="utf-8")
    replacement = _lock_payload(pid=os.getpid(), guard="replacement")

    def replace_before_dead_report(*args: object) -> None:
        _ = args
        slot_zero.write_text(replacement, encoding="utf-8")
        raise ProcessLookupError("dead")

    monkeypatch.setattr(mutex.os, "kill", replace_before_dead_report)

    result = mutex.claim_dispatch_admission_mutex(
        repo=tmp_path,
        fabro_bin="fabro",
        runner=_PsRunner(stdouts=[_empty_ps(), _empty_ps()]),
        cap=1,
    )

    assert isinstance(result, mutex.AdmissionMutexRefusal)
    assert f"slot 0: pid {os.getpid()}" in result.detail
    assert slot_zero.read_text(encoding="utf-8") == replacement


def test_loop_refuses_at_committed_host_dispatch_cap_of_one(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path, host_dispatch_cap=1)
    append_work_item(path=_config(), item=_item())
    runner = _PsRunner(stdouts=[_running_ps("fabro-run-01RUNNING")])
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
    assert _GUARD in captured.err
    assert "fabro-run-01RUNNING" in captured.err
    assert "host dispatch cap (1)" in captured.err
    assert "dispatcher.host_dispatch_cap" in captured.err
    assert runner.calls == [["fabro", "ps", "-a", "--json"]]
    journal_records = [
        json.loads(line)
        for line in (repo / "tmp" / "fabro-dispatch-journal.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert any(
        record.get("stage") == "dispatch-admission-mutex"
        and record.get("guard") == "host_dispatch_cap counting cap (bd-ib-sd8o deliverable (b))"
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
