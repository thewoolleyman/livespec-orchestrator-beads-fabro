"""A runner's atomic verdict wins over a concurrent process exit."""

import os
import time
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands.session_wait import (
    GateStatusLauncher,
    GateTarget,
    HerdrPaneLauncher,
    RoutingLauncher,
    WaitRequest,
    WaitResult,
    run_wait,
)


def _target(*, repository: Path) -> GateTarget:
    run_dir = repository / "tmp/gate-runs/completing"
    run_dir.mkdir(parents=True)
    (run_dir / "started_at").write_text("generation\n", encoding="utf-8")
    (run_dir / "pid").write_text(f"{os.getpid()}\n", encoding="utf-8")
    return GateTarget.freeze(gate_store_root=run_dir.parent, run_id=run_dir.name)


def _publish(*, target: GateTarget, code: int) -> float:
    partial = target.gate_store_root / target.run_id / "exit_code.partial"
    partial.write_text(f"{code}\n", encoding="utf-8")
    partial.replace(partial.with_name("exit_code"))
    return time.monotonic()


def _assert_verdict(*, result: WaitResult, target: GateTarget, code: int, state: str) -> None:
    assert result.command_outcome == "target-ended"
    assert result.trigger_target == target.identity
    assert result.trigger_exit_code == code
    assert result.observations[target.identity].state == state
    assert result.observations[target.identity].fresh is True


@pytest.mark.parametrize(
    ("code", "state"), [(0, "PASSED"), (23, "FAILED"), (143, "DIED_WITHOUT_VERDICT")]
)
def test_verdict_published_during_pid_probe_is_returned_within_two_seconds(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: int, state: str
) -> None:
    target = _target(repository=tmp_path)
    completed: list[float] = []

    def exit_during_probe(pid: int, signal: int) -> None:
        assert (pid, signal) == (os.getpid(), 0)
        completed.append(_publish(target=target, code=code))
        raise ProcessLookupError

    monkeypatch.setattr(os, "kill", exit_during_probe)
    result = run_wait(
        request=WaitRequest(
            wait_id="completion-race",
            session_id="files",
            repository=tmp_path,
            deadline_seconds=5.0,
            targets=(target,),
        ),
        launcher=RoutingLauncher(
            gate=GateStatusLauncher(repository=tmp_path), pane=HerdrPaneLauncher()
        ),
        wait_store_root=tmp_path / "tmp/session-waits",
    )
    assert len(completed) == 1
    assert time.monotonic() - completed[0] < 2.0
    _assert_verdict(result=result, target=target, code=code, state=state)


def test_verdict_written_between_rounds_wakes_by_next_second(*, tmp_path: Path) -> None:
    target = _target(repository=tmp_path)
    completed: list[float] = []
    sleeps: list[float] = []

    def finish_while_sleeping(*, seconds: float) -> None:
        sleeps.append(seconds)
        completed.append(_publish(target=target, code=7))
        time.sleep(seconds)

    result = run_wait(
        request=WaitRequest(
            wait_id="completion-between-rounds",
            session_id="files",
            repository=tmp_path,
            deadline_seconds=5.0,
            targets=(target,),
        ),
        launcher=RoutingLauncher(
            gate=GateStatusLauncher(repository=tmp_path), pane=HerdrPaneLauncher()
        ),
        wait_store_root=tmp_path / "tmp/session-waits",
        sleeper=finish_while_sleeping,
    )
    assert len(completed) == 1
    assert sleeps == [1.0]
    assert time.monotonic() - completed[0] < 2.0
    _assert_verdict(result=result, target=target, code=7, state="FAILED")
