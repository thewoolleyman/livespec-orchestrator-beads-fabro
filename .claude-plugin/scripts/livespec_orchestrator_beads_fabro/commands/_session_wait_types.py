"""Immutable values and protocols shared by session-wait concerns."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

__all__: list[str] = [
    "GateObservation",
    "GateTarget",
    "Probe",
    "ProbeLauncher",
    "WaitRequest",
    "WaitResult",
    "freeze_gate_pointer",
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


class Probe(Protocol):
    def poll(self, *, now: float) -> GateObservation | None: ...

    def cancel(self, *, timeout_seconds: float) -> None: ...


class ProbeLauncher(Protocol):
    def launch(self, *, target: GateTarget, timeout_seconds: float) -> Probe: ...


def freeze_gate_pointer(*, gate_store_root: Path, pointer: Path) -> GateTarget:
    return GateTarget.freeze(
        gate_store_root=gate_store_root,
        run_id=pointer.read_text(encoding="utf-8").strip(),
    )
