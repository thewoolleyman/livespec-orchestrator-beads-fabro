"""Bounded host-session waits for detached gates."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace
from math import isfinite
from pathlib import Path
from typing import Protocol

from livespec_orchestrator_beads_fabro.commands._session_wait_ack import AckResult, ack_wait
from livespec_orchestrator_beads_fabro.commands._session_wait_cli import (
    SessionWaitCliSeams,
    main,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_gate import (
    GateStatusLauncher,
    resolve_primary_repository,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_lock import LockBudget
from livespec_orchestrator_beads_fabro.commands._session_wait_records import (
    WaiterIdentity,
    current_waiter_identity,
    record_observations,
    record_return_ready,
    register_wait,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_types import (
    GateObservation,
    GateTarget,
    ProbeLauncher,
    WaitRequest,
    WaitResult,
    freeze_gate_pointer,
)
from livespec_orchestrator_beads_fabro.commands.session_wait_inventory import (
    InventoryRecord,
    InventorySnapshot,
    inventory_waits,
)

__all__: list[str] = [
    "AckResult",
    "GateObservation",
    "GateStatusLauncher",
    "GateTarget",
    "InventoryRecord",
    "InventorySnapshot",
    "SessionWaitCliSeams",
    "WaitRequest",
    "WaitResult",
    "WaiterIdentity",
    "ack_wait",
    "freeze_gate_pointer",
    "inventory_waits",
    "main",
    "register_wait",
    "resolve_primary_repository",
    "run_wait",
]


class _Sleeper(Protocol):
    def __call__(self, *, seconds: float) -> None: ...


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
    launcher: ProbeLauncher,
    wait_store_root: Path,
    monotonic: Callable[[], float] = time.monotonic,
    sleeper: _Sleeper = lambda *, seconds=0.0: time.sleep(seconds),
    wall_clock: Callable[[], float] = time.time,
) -> WaitResult:
    """Observe every frozen target independently and return the first ending."""
    if not isfinite(request.deadline_seconds) or request.deadline_seconds <= 0:
        return WaitResult(
            command_outcome="invalid-deadline",
            trigger_target=None,
            trigger_exit_code=None,
            observations={},
        )
    deadline = monotonic() + request.deadline_seconds
    lock_budget = LockBudget(deadline=deadline, monotonic=monotonic, sleeper=sleeper)
    registration = register_wait(
        request=request,
        wait_store_root=wait_store_root,
        waiter=current_waiter_identity(),
        armed_at=wall_clock(),
        lock_budget=lock_budget,
    )
    if registration == "unavailable":
        return _deadline_result(request=request, observations={}, deadline=deadline)
    handles = [
        launcher.launch(
            target=target,
            timeout_seconds=max(0.0, deadline - monotonic()),
        )
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
            result = WaitResult(
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
            _ = record_observations(
                wait_store_root=wait_store_root,
                wait_id=request.wait_id,
                observations=tuple(result.observations.values()),
                lock_budget=lock_budget,
            )
            _ = record_return_ready(
                wait_store_root=wait_store_root,
                wait_id=request.wait_id,
                return_reason=result.command_outcome,
                lock_budget=lock_budget,
            )
            return result
        remaining = deadline - monotonic()
        if remaining <= 0:
            break
        sleeper(seconds=min(1.0, remaining))

    for handle in handles:
        handle.cancel(timeout_seconds=max(0.0, deadline - monotonic()))
    result = _deadline_result(
        request=request,
        observations=observations,
        deadline=deadline,
    )
    _ = record_observations(
        wait_store_root=wait_store_root,
        wait_id=request.wait_id,
        observations=tuple(result.observations.values()),
        lock_budget=lock_budget,
    )
    _ = record_return_ready(
        wait_store_root=wait_store_root,
        wait_id=request.wait_id,
        return_reason=result.command_outcome,
        lock_budget=lock_budget,
    )
    return result
