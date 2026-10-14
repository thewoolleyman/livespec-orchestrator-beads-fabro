"""Behavior tests for bounded detached-gate session waits."""

import os
from dataclasses import dataclass, field
from math import inf, nan
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._session_wait_gate import GateStatusProbe
from livespec_orchestrator_beads_fabro.commands.session_wait import (
    GateObservation,
    GateStatusLauncher,
    GateTarget,
    HerdrPaneLauncher,
    RoutingLauncher,
    WaitRequest,
    freeze_gate_pointer,
    run_wait,
)


@dataclass(kw_only=True)
class _CompletedProbe:
    observation: GateObservation
    cancelled: bool = False

    def poll(self, *, now: float) -> GateObservation | None:
        del now
        return self.observation

    def cancel(self, *, timeout_seconds: float) -> None:
        del timeout_seconds
        self.cancelled = True


@dataclass(kw_only=True)
class _ProbeLauncher:
    observations: dict[str, GateObservation]
    started: list[str] = field(default_factory=list)
    handles: list[_CompletedProbe] = field(default_factory=list)

    def launch(self, *, target: GateTarget, timeout_seconds: float) -> _CompletedProbe:
        del timeout_seconds
        self.started.append(target.run_id)
        handle = _CompletedProbe(observation=self.observations[target.run_id])
        self.handles.append(handle)
        return handle


@dataclass(kw_only=True)
class _ManualClock:
    value: float
    sleeps: list[float] = field(default_factory=list)

    def now(self) -> float:
        return self.value

    def sleep(self, *, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.value += seconds


@dataclass(kw_only=True)
class _HungProbe:
    polls: int = 0
    cancelled: bool = False

    def poll(self, *, now: float) -> GateObservation | None:
        del now
        self.polls += 1
        return None

    def cancel(self, *, timeout_seconds: float) -> None:
        assert timeout_seconds >= 0
        self.cancelled = True


@dataclass(kw_only=True)
class _RunningProbe:
    target: GateTarget
    polls: int = 0
    cancelled: bool = False

    def poll(self, *, now: float) -> GateObservation | None:
        self.polls += 1
        return GateObservation.running(target=self.target, observed_at=now)

    def cancel(self, *, timeout_seconds: float) -> None:
        assert timeout_seconds >= 0
        self.cancelled = True


@dataclass(kw_only=True)
class _DeadlineLauncher:
    hung_target: GateTarget
    running_target: GateTarget
    hung: _HungProbe = field(default_factory=_HungProbe)
    running: _RunningProbe = field(init=False)
    started: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.running = _RunningProbe(target=self.running_target)

    def launch(self, *, target: GateTarget, timeout_seconds: float) -> _HungProbe | _RunningProbe:
        assert timeout_seconds > 0
        self.started.append(target.run_id)
        return self.hung if target == self.hung_target else self.running


def _target(*, gate_store_root: Path, run_id: str) -> GateTarget:
    run_dir = gate_store_root / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "started_at").write_text(f"started-{run_id}\n", encoding="utf-8")
    return GateTarget.freeze(gate_store_root=gate_store_root, run_id=run_id)


def test_first_completed_gate_wakes_with_preserved_verdict(*, tmp_path: Path) -> None:
    gate_store_root = tmp_path / "gate-runs"
    target_a = _target(gate_store_root=gate_store_root, run_id="gate-a")
    target_b = _target(gate_store_root=gate_store_root, run_id="gate-b")
    pointer = tmp_path / "gate-c.id"
    pointer.write_text("gate-c-original\n", encoding="utf-8")
    target_c = _target(gate_store_root=gate_store_root, run_id="gate-c-original")
    assert target_c == freeze_gate_pointer(
        gate_store_root=gate_store_root,
        pointer=pointer,
    )
    pointer.write_text("gate-c-replacement\n", encoding="utf-8")

    launcher = _ProbeLauncher(
        observations={
            "gate-a": GateObservation.running(target=target_a, observed_at=10.0),
            "gate-b": GateObservation.finished(
                target=target_b,
                state="FAILED",
                exit_code=23,
                observed_at=10.1,
            ),
            "gate-c-original": GateObservation.running(target=target_c, observed_at=10.2),
        }
    )
    result = run_wait(
        request=WaitRequest(
            wait_id="wait-first-event",
            session_id="session-first-event",
            repository=tmp_path,
            deadline_seconds=5.0,
            targets=(target_a, target_b, target_c),
        ),
        launcher=launcher,
        wait_store_root=tmp_path / "session-waits",
    )

    assert result.command_outcome == "target-ended"
    assert result.trigger_target == target_b.identity
    assert result.trigger_exit_code == 23
    assert result.observations[target_a.identity].state == "RUNNING"
    assert result.observations[target_a.identity].fresh is True
    assert result.observations[target_c.identity].state == "RUNNING"
    assert launcher.started == ["gate-a", "gate-b", "gate-c-original"]
    assert all(handle.cancelled for handle in launcher.handles)


def test_shared_deadline_bounds_hung_probe_and_leaves_gates_running(*, tmp_path: Path) -> None:
    gate_store_root = tmp_path / "gate-runs"
    hung_target = _target(gate_store_root=gate_store_root, run_id="gate-hung")
    running_target = _target(gate_store_root=gate_store_root, run_id="gate-running")
    completed = GateObservation.finished(
        target=running_target,
        state="PASSED",
        exit_code=0,
        observed_at=1.0,
    )
    invalid_launcher = _ProbeLauncher(observations={running_target.run_id: completed})
    for invalid in (0.0, -1.0, inf, nan):
        invalid_result = run_wait(
            request=WaitRequest(
                wait_id=f"invalid-{invalid}",
                session_id="session-deadline",
                repository=tmp_path,
                deadline_seconds=invalid,
                targets=(running_target,),
            ),
            launcher=invalid_launcher,
            wait_store_root=tmp_path / "invalid-session-waits",
        )
        assert invalid_result.command_outcome == "invalid-deadline"
    assert invalid_launcher.started == []
    assert not (tmp_path / "invalid-session-waits").exists()

    clock = _ManualClock(value=100.0)
    launcher = _DeadlineLauncher(hung_target=hung_target, running_target=running_target)
    target_processes_running = {hung_target.identity: True, running_target.identity: True}
    result = run_wait(
        request=WaitRequest(
            wait_id="wait-deadline",
            session_id="session-deadline",
            repository=tmp_path,
            deadline_seconds=2.0,
            targets=(hung_target, running_target),
        ),
        launcher=launcher,
        wait_store_root=tmp_path / "session-waits",
        monotonic=clock.now,
        sleeper=clock.sleep,
    )

    assert result.command_outcome == "deadline"
    assert clock.value == 102.0
    assert max(clock.sleeps) <= 1.0
    assert launcher.hung.polls >= 2
    assert launcher.running.polls >= 2
    assert result.observations[running_target.identity].state == "RUNNING"
    assert result.observations[running_target.identity].fresh is False
    assert result.observations[hung_target.identity].state == "UNAVAILABLE"
    assert set(result.unfinished_targets) == {hung_target.identity, running_target.identity}
    assert launcher.hung.cancelled is True
    assert launcher.running.cancelled is True
    assert all(target_processes_running.values())


def _file_gate_targets(*, repository: Path) -> tuple[GateTarget, ...]:
    targets = tuple(
        _target(gate_store_root=repository / "tmp/gate-runs", run_id=run_id)
        for run_id in ("gate-a", "gate-b", "gate-c")
    )
    for target in targets:
        (target.gate_store_root / target.run_id / "pid").write_text(
            f"{os.getpid()}\n", encoding="utf-8"
        )
    (targets[1].gate_store_root / targets[1].run_id / "exit_code").write_text(
        "23\n", encoding="utf-8"
    )
    return targets


@pytest.mark.parametrize(
    ("scenario", "expected_seen"),
    [
        ("first-event", ["gate-a", "gate-b", "gate-c"]),
        ("deadline-before-sibling", ["gate-a"]),
        ("deadline-on-completion", ["gate-a", "gate-b"]),
    ],
)
def test_file_backed_multi_gate_wait_shares_one_deadline(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
    expected_seen: list[str],
) -> None:
    targets = _file_gate_targets(repository=tmp_path)
    clock = _ManualClock(value=100.0)
    seen: list[str] = []
    poll = GateStatusProbe.poll

    def timed_poll(probe: GateStatusProbe, *, now: float) -> GateObservation:
        seen.append(probe.target.run_id)
        cost = 0.25
        if scenario == "deadline-before-sibling" and probe.target == targets[0]:
            cost = 1.0
        elif scenario == "deadline-on-completion" and probe.target == targets[1]:
            cost = 0.75
        clock.value += cost
        return poll(probe, now=now)

    monkeypatch.setattr(GateStatusProbe, "poll", timed_poll)
    result = run_wait(
        request=WaitRequest(
            wait_id=scenario,
            session_id="multi-gate",
            repository=tmp_path,
            deadline_seconds=1.0,
            targets=targets,
        ),
        launcher=RoutingLauncher(
            gate=GateStatusLauncher(repository=tmp_path),
            pane=HerdrPaneLauncher(),
        ),
        wait_store_root=tmp_path / "tmp/session-waits",
        monotonic=clock.now,
        sleeper=clock.sleep,
    )
    assert clock.value <= 101.0, "reading later gates must not extend the original deadline"
    assert seen == expected_seen
    if scenario == "first-event":
        assert result.command_outcome == "target-ended"
        assert result.trigger_target == targets[1].identity
        assert result.trigger_exit_code == 23
        assert [result.observations[target.identity].state for target in targets] == [
            "RUNNING",
            "FAILED",
            "RUNNING",
        ]
    else:
        assert result.command_outcome == "deadline"
        assert result.trigger_target is None
        assert result.unfinished_targets == tuple(target.identity for target in targets)
        assert all(not observation.fresh for observation in result.observations.values())
    assert not (targets[0].gate_store_root / targets[0].run_id / "exit_code").exists()
    assert not (targets[2].gate_store_root / targets[2].run_id / "exit_code").exists()
