"""Behavior tests for bounded detached-gate session waits."""

from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands.session_wait import (
    GateObservation,
    GateTarget,
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
        assert timeout_seconds > 0
        self.started.append(target.run_id)
        handle = _CompletedProbe(observation=self.observations[target.run_id])
        self.handles.append(handle)
        return handle


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
