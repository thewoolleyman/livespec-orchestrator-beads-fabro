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
from livespec_orchestrator_beads_fabro.commands._session_wait_pane import (
    HerdrPaneLauncher,
    freeze_pane_target,
    observe_pane_target,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_records import (
    REGISTRATION_CONFLICT,
    REGISTRATION_UNAVAILABLE,
    WaiterIdentity,
    current_waiter_identity,
    record_observations,
    record_return_ready,
    register_wait,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_routing import (
    RoutingLauncher,
    observe_wait_target,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_types import (
    GateObservation,
    GateTarget,
    PaneTarget,
    Probe,
    ProbeLauncher,
    WaitRequest,
    WaitResult,
    freeze_gate_pointer,
    observation_is_running,
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
    "HerdrPaneLauncher",
    "InventoryRecord",
    "InventorySnapshot",
    "PaneTarget",
    "RoutingLauncher",
    "SessionWaitCliSeams",
    "WaitRequest",
    "WaitResult",
    "WaiterIdentity",
    "ack_wait",
    "freeze_gate_pointer",
    "freeze_pane_target",
    "inventory_waits",
    "main",
    "observe_pane_target",
    "observe_wait_target",
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
    started_at = monotonic() if request.started_at is None else request.started_at
    deadline = started_at + request.deadline_seconds
    lock_budget = LockBudget(deadline=deadline, monotonic=monotonic, sleeper=sleeper)
    registration = register_wait(
        request=request,
        wait_store_root=wait_store_root,
        waiter=current_waiter_identity(),
        armed_at=wall_clock(),
        lock_budget=lock_budget,
    )
    refusal = _registration_refusal(
        registration=registration,
        request=request,
        deadline=deadline,
    )
    if refusal is not None:
        return refusal
    handles = [
        launcher.launch(
            target=target,
            timeout_seconds=max(0.0, deadline - monotonic()),
        )
        for target in request.targets
    ]
    observations = _observe_until(
        handles=handles,
        deadline=deadline,
        monotonic=monotonic,
        sleeper=sleeper,
    )
    for handle in handles:
        handle.cancel(timeout_seconds=max(0.0, deadline - monotonic()))
    result = _wait_result(request=request, observations=observations, deadline=deadline)
    _persist_result(
        wait_store_root=wait_store_root,
        request=request,
        result=result,
        lock_budget=lock_budget,
    )
    return result


def _registration_refusal(
    *,
    registration: str,
    request: WaitRequest,
    deadline: float,
) -> WaitResult | None:
    """The refusal registration owes, or None when this wait owns its id.

    A CONFLICT refuses before any probe exists. A live record already owns
    this wait id, and its frozen targets, owner and deadline ARE that record,
    so launching probes and carrying on would retarget an armed wait through
    the back door. An UNAVAILABLE store could not be measured at all, which is
    reported as the deadline outcome rather than as a verdict about a target.
    """
    if registration == REGISTRATION_CONFLICT:
        return WaitResult(
            command_outcome="registration-conflict",
            trigger_target=None,
            trigger_exit_code=None,
            observations={},
            unfinished_targets=tuple(target.identity for target in request.targets),
        )
    if registration == REGISTRATION_UNAVAILABLE:
        return _deadline_result(request=request, observations={}, deadline=deadline)
    return None


def _observe_until(
    *,
    handles: list[Probe],
    deadline: float,
    monotonic: Callable[[], float],
    sleeper: _Sleeper,
) -> dict[str, GateObservation]:
    """Poll every probe until one target ends or the shared deadline expires.

    The deadline is the one computed before registration and is never
    recomputed or extended here, so a hung probe cannot push the return out:
    each round polls every probe once, and the sleep between rounds is capped
    at one second so a sibling stays independently observable at that cadence.
    """
    observations: dict[str, GateObservation] = {}
    while True:
        now = monotonic()
        for handle in handles:
            observation = handle.poll(now=now)
            if observation is not None:
                observations[observation.target.identity] = observation
        if _first_terminal(observations=observations) is not None:
            return observations
        remaining = deadline - monotonic()
        if remaining <= 0:
            return observations
        sleeper(seconds=min(1.0, remaining))


def _first_terminal(*, observations: dict[str, GateObservation]) -> GateObservation | None:
    """The earliest-observed target that has left ITS OWN running state.

    The predicate is per target kind rather than one shared state name: a
    detached gate continues on `RUNNING` and a Herdr pane on `working`, so a
    single-name test would read every working pane as a finished target and
    return a verdict about a pane that is still mid-turn.
    """
    terminal = [
        observation
        for observation in observations.values()
        if not observation_is_running(observation=observation)
    ]
    if not terminal:
        return None
    return min(terminal, key=lambda observation: observation.observed_at)


def _wait_result(
    *,
    request: WaitRequest,
    observations: dict[str, GateObservation],
    deadline: float,
) -> WaitResult:
    """Build the outcome from what was actually observed."""
    terminal = _first_terminal(observations=observations)
    if terminal is None:
        return _deadline_result(request=request, observations=observations, deadline=deadline)
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


def _persist_result(
    *,
    wait_store_root: Path,
    request: WaitRequest,
    result: WaitResult,
    lock_budget: LockBudget,
) -> None:
    """Record the round and that a result became RETURNABLE — never received."""
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
