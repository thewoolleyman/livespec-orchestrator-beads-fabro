"""Durable inventory behavior for bounded detached-gate waits."""

from __future__ import annotations

import json
import subprocess
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import pytest
from livespec_orchestrator_beads_fabro.commands.session_wait import (
    GateObservation,
    GateTarget,
    WaitRequest,
    run_wait,
)


@dataclass(kw_only=True)
class _ImmediateProbe:
    observation: GateObservation
    cancelled: bool = False

    def poll(self, *, now: float) -> GateObservation | None:
        del now
        return self.observation

    def cancel(self, *, timeout_seconds: float) -> None:
        del timeout_seconds
        self.cancelled = True


@dataclass(kw_only=True)
class _RegistrationAwareLauncher:
    record_path: Path
    observation: GateObservation
    record_seen_before_launch: bool = False

    def launch(self, *, target: GateTarget, timeout_seconds: float) -> _ImmediateProbe:
        del target, timeout_seconds
        self.record_seen_before_launch = self.record_path.is_file()
        return _ImmediateProbe(observation=self.observation)


@dataclass(frozen=True, kw_only=True)
class _InventoryContext:
    repository: Path
    gate_store_root: Path
    wait_store_root: Path
    ended_target: GateTarget
    ended_record: Path


@dataclass(frozen=True, kw_only=True)
class _ObservationSeams:
    observe_target: Callable[..., GateObservation]
    process_generation: Callable[..., str | None]


class _Pollable(Protocol):
    def poll(self, *, now: float) -> GateObservation | None: ...


def _target(*, gate_store_root: Path, run_id: str) -> GateTarget:
    run_dir = gate_store_root / run_id
    run_dir.mkdir(parents=True)
    _ = (run_dir / "started_at").write_text(f"generation-{run_id}\n", encoding="utf-8")
    return GateTarget.freeze(gate_store_root=gate_store_root, run_id=run_id)


def _wait_request(
    *,
    repository: Path,
    target: GateTarget,
    wait_id: str,
    session_id: str,
    deadline_seconds: float,
) -> WaitRequest:
    return WaitRequest(
        wait_id=wait_id,
        session_id=session_id,
        repository=repository,
        deadline_seconds=deadline_seconds,
        targets=(target,),
    )


def _assert_atomic_registration(*, tmp_path: Path) -> _InventoryContext:
    gate_store_root = tmp_path / "gate-runs"
    ended_target = _target(gate_store_root=gate_store_root, run_id="gate-ended")
    wait_store_root = tmp_path / "session-waits"
    ended_record = wait_store_root / "wait-ended.json"
    launcher = _RegistrationAwareLauncher(
        record_path=ended_record,
        observation=GateObservation.finished(
            target=ended_target,
            state="FAILED",
            exit_code=23,
            observed_at=101.0,
        ),
    )
    result = run_wait(
        request=_wait_request(
            repository=tmp_path,
            target=ended_target,
            wait_id="wait-ended",
            session_id="session-ended",
            deadline_seconds=60.0,
        ),
        launcher=launcher,
        wait_store_root=wait_store_root,
    )
    assert launcher.record_seen_before_launch is True
    assert ended_record.is_file()
    assert result.command_outcome == "target-ended"
    return _InventoryContext(
        repository=tmp_path,
        gate_store_root=gate_store_root,
        wait_store_root=wait_store_root,
        ended_target=ended_target,
        ended_record=ended_record,
    )


def _register_concurrent_waits(*, context: _InventoryContext) -> None:
    from livespec_orchestrator_beads_fabro.commands.session_wait import (
        WaiterIdentity,
        register_wait,
    )

    requests = tuple(
        _wait_request(
            repository=context.repository,
            target=_target(gate_store_root=context.gate_store_root, run_id=f"gate-{suffix}"),
            wait_id=f"wait-{suffix}",
            session_id=f"session-{suffix}",
            deadline_seconds=deadline,
        )
        for suffix, deadline in (("missing", 5.0), ("replaced", 100.0))
    )
    waiters = (
        WaiterIdentity(pid=111, generation="generation-missing"),
        WaiterIdentity(pid=222, generation="generation-original"),
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(
                register_wait,
                request=request,
                wait_store_root=context.wait_store_root,
                waiter=waiter,
                armed_at=100.0,
            )
            for request, waiter in zip(requests, waiters, strict=True)
        ]
        assert [future.result() for future in futures] == ["registered", "registered"]
    assert (
        register_wait(
            request=requests[0],
            wait_store_root=context.wait_store_root,
            waiter=waiters[0],
            armed_at=100.0,
        )
        == "conflict"
    )


def _observation_seams(*, context: _InventoryContext) -> _ObservationSeams:
    ended_payload = json.loads(context.ended_record.read_text(encoding="utf-8"))
    ended_pid = int(ended_payload["waiter"]["pid"])
    ended_generation = str(ended_payload["waiter"]["generation"])

    def observe_target(*, target: GateTarget, observed_at: float) -> GateObservation:
        if target == context.ended_target:
            return GateObservation.finished(
                target=target,
                state="FAILED",
                exit_code=23,
                observed_at=observed_at,
            )
        return GateObservation.running(target=target, observed_at=observed_at)

    def process_generation(*, pid: int) -> str | None:
        return {
            ended_pid: ended_generation,
            111: None,
            222: "generation-replacement",
        }[pid]

    return _ObservationSeams(
        observe_target=observe_target,
        process_generation=process_generation,
    )


def _assert_fresh_inventory(
    *,
    context: _InventoryContext,
    seams: _ObservationSeams,
) -> None:
    from livespec_orchestrator_beads_fabro.commands.session_wait import inventory_waits

    _ = (context.wait_store_root / "corrupt.json").write_text("{", encoding="utf-8")
    _ = (context.wait_store_root / "unsupported.json").write_text(
        json.dumps({"schema_version": 99, "wait_id": "unsupported"}),
        encoding="utf-8",
    )
    (context.wait_store_root / "unreadable.json").mkdir()
    snapshot = inventory_waits(
        wait_store_root=context.wait_store_root,
        observed_at=110.0,
        observe_target=seams.observe_target,
        process_generation=seams.process_generation,
    )
    rows = {record.wait_id: record for record in snapshot.records}
    assert "ended-unacknowledged" in rows["wait-ended"].findings
    assert rows["wait-ended"].observations[0].fresh is True
    assert rows["wait-ended"].observation_sequence > 0
    assert {"overdue", "waiter-missing", "running-without-waiter"}.issubset(
        rows["wait-missing"].findings
    )
    assert {"waiter-replaced", "running-without-waiter"}.issubset(rows["wait-replaced"].findings)
    assert rows["corrupt"].record_state == "unavailable"
    assert rows["unsupported"].diagnostic == "unsupported-schema"
    assert rows["unreadable"].diagnostic == "unreadable-record"


def _assert_receipt_acknowledgement(
    *,
    context: _InventoryContext,
    seams: _ObservationSeams,
) -> None:
    from livespec_orchestrator_beads_fabro.commands.session_wait import (
        ack_wait,
        inventory_waits,
    )

    mismatch = ack_wait(
        wait_store_root=context.wait_store_root,
        wait_id="wait-ended",
        session_id="not-the-owner",
        acknowledged_at=111.0,
        retention_limit=1,
    )
    assert mismatch.status == "owner-mismatch"
    assert (
        ack_wait(
            wait_store_root=context.wait_store_root,
            wait_id="absent",
            session_id="session-ended",
            acknowledged_at=111.0,
            retention_limit=1,
        ).status
        == "not-found"
    )
    acknowledged = ack_wait(
        wait_store_root=context.wait_store_root,
        wait_id="wait-ended",
        session_id="session-ended",
        acknowledged_at=111.0,
        retention_limit=1,
    )
    assert acknowledged.status == "receipt-acknowledged"
    payload = json.loads(context.ended_record.read_text(encoding="utf-8"))
    assert payload["acknowledgement"]["kind"] == "receipt-only"
    assert "execution_consumed" not in payload
    assert "result_fulfilled" not in payload
    snapshot = inventory_waits(
        wait_store_root=context.wait_store_root,
        observed_at=112.0,
        observe_target=seams.observe_target,
        process_generation=seams.process_generation,
    )
    row = {record.wait_id: record for record in snapshot.records}["wait-ended"]
    assert "ended-unacknowledged" not in row.findings
    second = ack_wait(
        wait_store_root=context.wait_store_root,
        wait_id="wait-missing",
        session_id="session-missing",
        acknowledged_at=113.0,
        retention_limit=1,
    )
    assert second.status == "receipt-acknowledged"
    assert not context.ended_record.exists()
    assert (context.wait_store_root / "wait-missing.json").is_file()
    assert (context.wait_store_root / "wait-replaced.json").is_file()
    assert (context.wait_store_root / "corrupt.json").is_file()


def _assert_primary_resolution(*, tmp_path: Path) -> None:
    from livespec_orchestrator_beads_fabro.commands.session_wait import (
        resolve_primary_repository,
    )

    git_repo = tmp_path / "configured-repo"
    git_repo.mkdir()
    subprocess.run(["git", "init", "--quiet", str(git_repo)], check=True)
    subprocess.run(
        ["git", "-C", str(git_repo), "config", "livespec.primaryPath", str(tmp_path)],
        check=True,
    )
    assert resolve_primary_repository(repository=git_repo) == tmp_path.resolve()
    missing = tmp_path / "not-a-repo"
    assert resolve_primary_repository(repository=missing) == missing.resolve()


def _assert_cli(
    *,
    context: _InventoryContext,
    seams: _ObservationSeams,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from livespec_orchestrator_beads_fabro.commands.session_wait import (
        SessionWaitCliSeams,
        main,
    )

    cli_target = _target(gate_store_root=context.gate_store_root, run_id="gate-cli")
    launcher = _RegistrationAwareLauncher(
        record_path=context.wait_store_root / "wait-cli.json",
        observation=GateObservation.finished(
            target=cli_target,
            state="PASSED",
            exit_code=0,
            observed_at=114.0,
        ),
    )
    cli_seams = SessionWaitCliSeams(
        primary_repository=lambda *, repository: repository,
        launcher=lambda *, repository: launcher if repository else launcher,
        observe_target=seams.observe_target,
        process_generation=seams.process_generation,
        wall_clock=lambda: 114.0,
    )
    wait_argv = [
        "wait",
        "--repo",
        str(context.repository),
        "--session-id",
        "session-cli",
        "--wait-id",
        "wait-cli",
        "--deadline-seconds",
        "10",
        "--gate",
        "gate-cli",
    ]
    assert main(argv=wait_argv, seams=cli_seams) == 0
    assert json.loads(capsys.readouterr().out)["command_outcome"] == "target-ended"
    assert (
        main(
            argv=["inventory", "--repo", str(context.repository)],
            seams=cli_seams,
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["observation_id"]
    assert main(argv=["check", "--repo", str(context.repository)], seams=cli_seams) == 1
    _ = capsys.readouterr()
    ack_argv = [
        "ack",
        "--repo",
        str(context.repository),
        "--session-id",
        "session-cli",
        "--wait-id",
        "wait-cli",
    ]
    assert main(argv=ack_argv, seams=cli_seams) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "receipt-acknowledged"


def _poll_until_observed(*, probe: _Pollable) -> GateObservation:
    observation: GateObservation | None = None
    deadline = time.monotonic() + 2.0
    while observation is None and time.monotonic() < deadline:
        observation = probe.poll(now=time.monotonic())
        time.sleep(0.01)
    assert observation is not None
    return observation


def _assert_gate_status_adapter(*, context: _InventoryContext) -> None:
    from livespec_orchestrator_beads_fabro.commands.session_wait import GateStatusLauncher

    # A POSIX-SHELL adapter rather than a Python one. `launch` clamps its budget
    # to `min(1.0, ...)` regardless of the 2.0 passed below, and a cold CPython
    # cannot print its first line within one second while the suite runs under
    # coverage tracing on a loaded host — the RUNNING probe was reaped before it
    # emitted anything, which the parser correctly reads as UNAVAILABLE. That is
    # what made this test fail, and it was never about the code under test.
    # Every observable behavior is preserved: `read` strips the trailing newline
    # exactly as `.strip()` did, `$(dirname "$1")` mirrors `Path(argv[1]).parent`
    # (the launcher passes the bare run id and runs the child in the gate dir, so
    # both resolve to `./mode`), the two status lines are emitted byte-identically,
    # and the hang arm still ignores SIGTERM in a process whose pid survives
    # `exec`, so cancelling it must still escalate past SIGTERM.
    helper = context.repository / "fake-gate-status.sh"
    _ = helper.write_text(
        """read mode < "$(dirname "$1")/mode"
case "$mode" in
hang)
    trap '' TERM
    exec sleep 60
    ;;
malformed)
    echo 'not gate status output'
    ;;
*)
    echo "  state             : $mode"
    if [ "$mode" = FAILED ]; then
        echo "  exit_code         : 23"
    fi
    ;;
esac
""",
        encoding="utf-8",
    )
    target = _target(gate_store_root=context.gate_store_root, run_id="gate-adapter")
    mode_file = target.gate_store_root / target.run_id / "mode"
    adapter = GateStatusLauncher(
        repository=context.repository,
        command_prefix=("/bin/sh", str(helper)),
    )
    _ = mode_file.write_text("FAILED\n", encoding="utf-8")
    finished = adapter.launch(target=target, timeout_seconds=2.0)
    observation = _poll_until_observed(probe=finished)
    assert (observation.state, observation.exit_code) == ("FAILED", 23)
    finished.cancel(timeout_seconds=0.0)
    _ = mode_file.write_text("RUNNING\n", encoding="utf-8")
    running = adapter.launch(target=target, timeout_seconds=2.0)
    assert _poll_until_observed(probe=running).state == "RUNNING"
    _ = mode_file.write_text("hang\n", encoding="utf-8")
    assert running.poll(now=time.monotonic()) is None
    running.cancel(timeout_seconds=0.01)
    assert running.active is False
    _ = mode_file.write_text("malformed\n", encoding="utf-8")
    unavailable = adapter.launch(target=target, timeout_seconds=2.0)
    assert _poll_until_observed(probe=unavailable).state == "UNAVAILABLE"
    started_at = target.gate_store_root / target.run_id / "started_at"
    _ = started_at.write_text("replacement-generation\n", encoding="utf-8")
    replaced = adapter.launch(target=target, timeout_seconds=2.0).poll(now=115.0)
    assert replaced is not None
    assert replaced.state == "REPLACED"
    started_at.unlink()
    gone = adapter.launch(target=target, timeout_seconds=2.0).poll(now=116.0)
    assert gone is not None
    assert gone.state == "GONE"


def test_inventory_distinguishes_produced_and_acknowledged_wakeups(
    *,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    context = _assert_atomic_registration(tmp_path=tmp_path)
    _register_concurrent_waits(context=context)
    seams = _observation_seams(context=context)
    _assert_fresh_inventory(context=context, seams=seams)
    _assert_receipt_acknowledgement(context=context, seams=seams)
    _assert_primary_resolution(tmp_path=tmp_path)
    _assert_cli(context=context, seams=seams, capsys=capsys)
    _assert_gate_status_adapter(context=context)
