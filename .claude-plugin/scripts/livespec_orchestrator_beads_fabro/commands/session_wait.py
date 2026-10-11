"""Bounded host-session waits for detached gates."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

__all__: list[str] = [
    "GateObservation",
    "GateTarget",
    "WaitRequest",
    "freeze_gate_pointer",
    "run_wait",
]


@dataclass(frozen=True, kw_only=True)
class GateTarget:
    gate_store_root: Path
    run_id: str
    generation: str

    @property
    def identity(self) -> str:
        return f"gate:{self.gate_store_root}:{self.run_id}"

    @classmethod
    def freeze(cls, *, gate_store_root: Path, run_id: str) -> GateTarget:
        started_at = (gate_store_root / run_id / "started_at").read_text(encoding="utf-8")
        return cls(
            gate_store_root=gate_store_root,
            run_id=run_id,
            generation=started_at.strip(),
        )


@dataclass(frozen=True, kw_only=True)
class GateObservation:
    target: GateTarget
    state: str
    exit_code: int | None
    observed_at: float
    fresh: bool

    @classmethod
    def running(cls, *, target: GateTarget, observed_at: float) -> GateObservation:
        return cls(
            target=target,
            state="RUNNING",
            exit_code=None,
            observed_at=observed_at,
            fresh=True,
        )

    @classmethod
    def finished(
        cls,
        *,
        target: GateTarget,
        state: str,
        exit_code: int,
        observed_at: float,
    ) -> GateObservation:
        return cls(
            target=target,
            state=state,
            exit_code=exit_code,
            observed_at=observed_at,
            fresh=True,
        )


@dataclass(frozen=True, kw_only=True)
class WaitRequest:
    wait_id: str
    session_id: str
    repository: Path
    deadline_seconds: float
    targets: tuple[GateTarget, ...]


@dataclass(frozen=True, kw_only=True)
class _WaitResult:
    command_outcome: str
    trigger_target: str | None
    trigger_exit_code: int | None
    observations: dict[str, GateObservation]


class _Probe(Protocol):
    def poll(self, *, now: float) -> GateObservation | None: ...

    def cancel(self, *, timeout_seconds: float) -> None: ...


class _Launcher(Protocol):
    def launch(self, *, target: GateTarget, timeout_seconds: float) -> _Probe: ...


def freeze_gate_pointer(*, gate_store_root: Path, pointer: Path) -> GateTarget:
    return GateTarget.freeze(
        gate_store_root=gate_store_root,
        run_id=pointer.read_text(encoding="utf-8").strip(),
    )


def run_wait(*, request: WaitRequest, launcher: _Launcher, wait_store_root: Path) -> _WaitResult:
    del wait_store_root
    deadline = time.monotonic() + request.deadline_seconds
    handles = [
        launcher.launch(target=target, timeout_seconds=request.deadline_seconds)
        for target in request.targets
    ]
    now = time.monotonic()
    observed = [cast("GateObservation", handle.poll(now=now)) for handle in handles]
    observations = {observation.target.identity: observation for observation in observed}
    terminal = min(
        (observation for observation in observations.values() if observation.state != "RUNNING"),
        key=lambda observation: observation.observed_at,
    )
    for handle in handles:
        handle.cancel(timeout_seconds=max(0.0, deadline - time.monotonic()))
    return _WaitResult(
        command_outcome="target-ended",
        trigger_target=terminal.target.identity,
        trigger_exit_code=terminal.exit_code,
        observations=observations,
    )
