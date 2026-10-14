"""Observe detached gates directly from their frozen runner directories.

The runner atomically publishes exit_code last. Local file reads and signal-zero
liveness checks need neither a worker thread nor a status subprocess. The host
wait supplies the one-second sleep cadence and the shared monotonic deadline.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._session_wait_types import (
    GateObservation,
    GateTarget,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

__all__: list[str] = [
    "GateStatusLauncher",
    "GateStatusProbe",
    "observe_gate_target",
    "resolve_primary_repository",
]


_SIGNAL_EXIT_FLOOR = 128


def resolve_primary_repository(*, repository: Path) -> Path:
    result = ShellCommandRunner().run(
        argv=["git", "-C", str(repository), "config", "--get", "livespec.primaryPath"],
        cwd=repository,
        timeout_seconds=5.0,
    )
    configured = result.stdout.strip()
    return Path(configured).resolve() if configured else repository.resolve()


def _generation_state(*, target: GateTarget) -> str | None:
    generation = attempt(
        action=lambda: (target.gate_store_root / target.run_id / "started_at").read_text(
            encoding="utf-8"
        ),
        exceptions=(OSError, UnicodeError),
    )
    if isinstance(generation, AttemptFailure):
        return "GONE" if isinstance(generation.error, FileNotFoundError) else "UNAVAILABLE"
    return "REPLACED" if generation.strip() != target.generation else None


def _read_integer(*, path: Path) -> int | AttemptFailure:
    return attempt(
        action=lambda: int(path.read_text(encoding="utf-8").strip()),
        exceptions=(OSError, ValueError),
    )


def _running_state(*, run_dir: Path) -> str:
    pid = _read_integer(path=run_dir / "pid")
    if isinstance(pid, AttemptFailure):
        return "DIED_WITHOUT_VERDICT" if isinstance(pid.error, FileNotFoundError) else "UNAVAILABLE"
    if pid <= 0:
        return "UNAVAILABLE"
    alive = attempt(action=lambda: os.kill(pid, 0), exceptions=(OSError, OverflowError))
    if isinstance(alive, AttemptFailure):
        return (
            "DIED_WITHOUT_VERDICT" if isinstance(alive.error, ProcessLookupError) else "UNAVAILABLE"
        )
    return _process_state(pid=pid)


def _process_state(*, pid: int) -> str:
    """Linux retains an exited PID until reaping; signal-zero alone is insufficient."""
    stat = attempt(
        action=lambda: Path(f"/proc/{pid}/stat").read_text(encoding="utf-8"),
        exceptions=(OSError, UnicodeError),
    )
    if isinstance(stat, AttemptFailure):
        return (
            "DIED_WITHOUT_VERDICT" if isinstance(stat.error, FileNotFoundError) else "UNAVAILABLE"
        )
    # The comm field may itself contain parentheses, so split after its LAST close.
    fields = stat.rpartition(")")[2].split()
    state = fields[0] if fields else ""
    if state in {"Z", "X", "x"}:
        return "DIED_WITHOUT_VERDICT"
    if state in {"R", "S", "D", "T", "t", "W", "K", "P", "I"}:
        return "RUNNING"
    return "UNAVAILABLE"


def _recorded_verdict(*, run_dir: Path) -> tuple[str, int | None] | None:
    recorded = _read_integer(path=run_dir / "exit_code")
    if isinstance(recorded, AttemptFailure):
        return None if isinstance(recorded.error, FileNotFoundError) else ("UNAVAILABLE", None)
    state = "PASSED" if recorded == 0 else "FAILED"
    if recorded >= _SIGNAL_EXIT_FLOOR:
        state = "DIED_WITHOUT_VERDICT"
    return state, recorded


def _gate_status(*, run_dir: Path) -> tuple[str, int | None]:
    verdict = _recorded_verdict(run_dir=run_dir)
    if verdict is not None:
        return verdict
    state = _running_state(run_dir=run_dir)
    if state != "RUNNING":
        # The runner can atomically publish its verdict and exit between the
        # first file read and the PID probe. Never discard that recorded result.
        verdict = _recorded_verdict(run_dir=run_dir)
        if verdict is not None:
            return verdict
    return state, None


def observe_gate_target(*, target: GateTarget, observed_at: float) -> GateObservation:
    """Read only this frozen gate; absent or unreadable data never means success."""
    state = _generation_state(target=target)
    exit_code: int | None = None
    if state is None:
        state, exit_code = _gate_status(run_dir=target.gate_store_root / target.run_id)
    return GateObservation(
        target=target,
        state=state,
        exit_code=exit_code,
        observed_at=observed_at,
        fresh=True,
    )


@dataclass(kw_only=True)
class GateStatusProbe:
    target: GateTarget

    @property
    def active(self) -> bool:
        """There is no asynchronous observation work to cancel."""
        return False

    def poll(self, *, now: float) -> GateObservation:
        return observe_gate_target(target=self.target, observed_at=now)

    def cancel(self, *, timeout_seconds: float) -> None:
        """Releasing an observer never signals or modifies the gate."""
        del timeout_seconds


@dataclass(frozen=True, kw_only=True)
class GateStatusLauncher:
    repository: Path

    def launch(self, *, target: GateTarget, timeout_seconds: float) -> GateStatusProbe:
        del timeout_seconds
        return GateStatusProbe(target=target)
