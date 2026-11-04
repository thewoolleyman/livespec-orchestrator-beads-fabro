"""The outcome a bounded wait reports: what ended it, or why nothing did.

Moved out of `session_wait` by cohesion: building a `WaitResult` from the
observations a wait actually made is one concern, and the deadline result, the
first-terminal choice and the target-ended result all answer it. The names are
public only because the wait module and this one are now two modules.
"""

from __future__ import annotations

from dataclasses import replace

from livespec_orchestrator_beads_fabro.commands._session_wait_types import (
    GateObservation,
    WaitRequest,
    WaitResult,
    observation_is_running,
)

__all__: list[str] = [
    "deadline_result",
    "first_terminal",
    "wait_result",
]


def deadline_result(
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


def first_terminal(*, observations: dict[str, GateObservation]) -> GateObservation | None:
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


def wait_result(
    *,
    request: WaitRequest,
    observations: dict[str, GateObservation],
    deadline: float,
) -> WaitResult:
    """Build the outcome from what was actually observed."""
    terminal = first_terminal(observations=observations)
    if terminal is None:
        return deadline_result(request=request, observations=observations, deadline=deadline)
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
