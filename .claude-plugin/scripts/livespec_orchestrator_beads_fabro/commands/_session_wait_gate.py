"""Existing gate-status adapter for independently observed wait targets."""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_defaults import (
    FLEET_RECIPE_RUNNER,
    FLEET_TOOL_RUNNER,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._session_wait_types import (
    GateObservation,
    GateTarget,
)

__all__: list[str] = [
    "GateStatusLauncher",
    "GateStatusProbe",
    "observe_gate_target",
    "resolve_primary_repository",
]

_DEFAULT_COMMAND = (
    FLEET_TOOL_RUNNER,
    "exec",
    "--",
    FLEET_RECIPE_RUNNER,
    "gate-status",
)
_STATE_PATTERN = re.compile(r"^\s*state\s*:\s*(\S+)\s*$", re.MULTILINE)
_EXIT_PATTERN = re.compile(r"^\s*exit_code\s*:\s*(-?\d+)\s*$", re.MULTILINE)


def resolve_primary_repository(*, repository: Path) -> Path:
    result = ShellCommandRunner().run(
        argv=["git", "-C", str(repository), "config", "--get", "livespec.primaryPath"],
        cwd=repository,
        timeout_seconds=5.0,
    )
    configured = result.stdout.strip()
    return Path(configured).resolve() if configured else repository.resolve()


def _generation_observation(*, target: GateTarget, observed_at: float) -> GateObservation | None:
    try:
        generation = (target.gate_store_root / target.run_id / "started_at").read_text(
            encoding="utf-8"
        )
    except OSError:
        return GateObservation(
            target=target,
            state="GONE",
            exit_code=None,
            observed_at=observed_at,
            fresh=True,
        )
    if generation.strip() != target.generation:
        return GateObservation(
            target=target,
            state="REPLACED",
            exit_code=None,
            observed_at=observed_at,
            fresh=True,
        )
    return None


def _parse_status(*, target: GateTarget, output: str, observed_at: float) -> GateObservation:
    state_match = _STATE_PATTERN.search(output)
    if state_match is None:
        return GateObservation(
            target=target,
            state="UNAVAILABLE",
            exit_code=None,
            observed_at=observed_at,
            fresh=True,
        )
    state = state_match.group(1)
    exit_match = _EXIT_PATTERN.search(output)
    exit_code = int(exit_match.group(1)) if exit_match is not None else None
    return GateObservation(
        target=target,
        state=state,
        exit_code=exit_code,
        observed_at=observed_at,
        fresh=True,
    )


@dataclass(kw_only=True)
class _CommandTask:
    target: GateTarget
    command_prefix: tuple[str, ...]
    observed_at: float
    timeout_seconds: float
    result: GateObservation | None = field(default=None, init=False)

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        self.result = observe_gate_target(
            target=self.target,
            observed_at=self.observed_at,
            command_prefix=self.command_prefix,
            timeout_seconds=self.timeout_seconds,
        )


@dataclass(kw_only=True)
class GateStatusProbe:
    target: GateTarget
    repository: Path
    command_prefix: tuple[str, ...]
    timeout_seconds: float
    task: _CommandTask | None = field(default=None, init=False)

    @property
    def active(self) -> bool:
        return self.task is not None and self.task.result is None

    def poll(self, *, now: float) -> GateObservation | None:
        generation_observation = _generation_observation(target=self.target, observed_at=now)
        if generation_observation is not None:
            return observe_gate_target(
                target=self.target,
                observed_at=now,
                command_prefix=self.command_prefix,
                timeout_seconds=self.timeout_seconds,
            )
        if self.task is None:
            self.task = _CommandTask(
                target=self.target,
                command_prefix=self.command_prefix,
                observed_at=now,
                timeout_seconds=self.timeout_seconds,
            )
            self.task.start()
        if self.task.result is None:
            return None
        observation = self.task.result
        self.task = None
        return observation

    def cancel(self, *, timeout_seconds: float) -> None:
        del timeout_seconds
        self.task = None


@dataclass(frozen=True, kw_only=True)
class GateStatusLauncher:
    repository: Path
    command_prefix: tuple[str, ...] = _DEFAULT_COMMAND

    def launch(self, *, target: GateTarget, timeout_seconds: float) -> GateStatusProbe:
        return GateStatusProbe(
            target=target,
            repository=self.repository,
            command_prefix=self.command_prefix,
            timeout_seconds=min(1.0, max(0.01, timeout_seconds)),
        )


def observe_gate_target(
    *,
    target: GateTarget,
    observed_at: float,
    command_prefix: tuple[str, ...] = _DEFAULT_COMMAND,
    timeout_seconds: float = 1.0,
) -> GateObservation:
    generation_observation = _generation_observation(target=target, observed_at=observed_at)
    if generation_observation is not None:
        return generation_observation
    result: CommandResult = ShellCommandRunner().run(
        argv=[*command_prefix, target.run_id],
        cwd=target.gate_store_root / target.run_id,
        timeout_seconds=timeout_seconds,
    )
    return _parse_status(
        target=target,
        output=result.stdout + result.stderr,
        observed_at=observed_at,
    )
