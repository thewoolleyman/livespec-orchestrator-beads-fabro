"""Bounded host-session waits for detached gates."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from math import isfinite
from pathlib import Path
from typing import Protocol

__all__: list[str] = [
    "GateObservation",
    "GateTarget",
    "WaitRequest",
    "WaitResult",
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
class WaitResult:
    command_outcome: str
    trigger_target: str | None
    trigger_exit_code: int | None
    observations: dict[str, GateObservation]
    unfinished_targets: tuple[str, ...] = ()


class _Probe(Protocol):
    def poll(self, *, now: float) -> GateObservation | None: ...

    def cancel(self, *, timeout_seconds: float) -> None: ...


class _Launcher(Protocol):
    def launch(self, *, target: GateTarget, timeout_seconds: float) -> _Probe: ...


class _Sleeper(Protocol):
    def __call__(self, *, seconds: float) -> None: ...


def freeze_gate_pointer(*, gate_store_root: Path, pointer: Path) -> GateTarget:
    return GateTarget.freeze(
        gate_store_root=gate_store_root,
        run_id=pointer.read_text(encoding="utf-8").strip(),
    )


def _deadline_result(
    *,
    request: WaitRequest,
    observations: dict[str, GateObservation],
    deadline: float,
) -> WaitResult:
    deadline_observations: dict[str, GateObservation] = {}
    for target in request.targets:
        observation = observations.get(target.identity)
        if observation is None:
            observation = GateObservation(
                target=target,
                state="UNAVAILABLE",
                exit_code=None,
                observed_at=deadline,
                fresh=False,
            )
        else:
            observation = replace(observation, fresh=False)
        deadline_observations[target.identity] = observation
    return WaitResult(
        command_outcome="deadline",
        trigger_target=None,
        trigger_exit_code=None,
        observations=deadline_observations,
        unfinished_targets=tuple(target.identity for target in request.targets),
    )


def run_wait(
    *,
    request: WaitRequest,
    launcher: _Launcher,
    wait_store_root: Path,
    monotonic: Callable[[], float] = time.monotonic,
    sleeper: _Sleeper = lambda *, seconds=0.0: time.sleep(seconds),
) -> WaitResult:
    del wait_store_root
    if not isfinite(request.deadline_seconds) or request.deadline_seconds <= 0:
        return WaitResult(
            command_outcome="invalid-deadline",
            trigger_target=None,
            trigger_exit_code=None,
            observations={},
        )
    deadline = monotonic() + request.deadline_seconds
    handles = [
        launcher.launch(target=target, timeout_seconds=max(0.0, deadline - monotonic()))
        for target in request.targets
    ]
    observations: dict[str, GateObservation] = {}
    while True:
        now = monotonic()
        for handle in handles:
            observation = handle.poll(now=now)
            if observation is not None:
                observations[observation.target.identity] = observation
        terminal_observations = [
            observation for observation in observations.values() if observation.state != "RUNNING"
        ]
        if terminal_observations:
            terminal = min(
                terminal_observations,
                key=lambda observation: observation.observed_at,
            )
            for handle in handles:
                handle.cancel(timeout_seconds=max(0.0, deadline - monotonic()))
            return WaitResult(
                command_outcome="target-ended",
                trigger_target=terminal.target.identity,
                trigger_exit_code=terminal.exit_code,
                observations=observations,
                unfinished_targets=tuple(
                    target.identity
                    for target in request.targets
                    if target.identity != terminal.target.identity
                ),
            )
        remaining = deadline - monotonic()
        if remaining <= 0:
            break
        sleeper(seconds=min(1.0, remaining))

    for handle in handles:
        handle.cancel(timeout_seconds=max(0.0, deadline - monotonic()))
    return _deadline_result(
        request=request,
        observations=observations,
        deadline=deadline,
    )
