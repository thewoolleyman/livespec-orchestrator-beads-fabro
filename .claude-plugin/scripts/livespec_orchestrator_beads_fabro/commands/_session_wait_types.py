"""Immutable values and protocols shared by session-wait concerns."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TypeAlias
from urllib.parse import quote

__all__: list[str] = [
    "GATE_TARGET_KIND",
    "PANE_TARGET_KIND",
    "GateObservation",
    "GateProbeLauncher",
    "GateTarget",
    "PaneProbeLauncher",
    "PaneTarget",
    "Probe",
    "ProbeLauncher",
    "WaitRequest",
    "WaitResult",
    "WaitTarget",
    "freeze_gate_pointer",
    "observation_is_running",
]

GATE_TARGET_KIND = "gate"
PANE_TARGET_KIND = "herdr-pane"


@dataclass(frozen=True, kw_only=True)
class GateTarget:
    gate_store_root: Path
    run_id: str
    generation: str

    @property
    def kind(self) -> str:
        return GATE_TARGET_KIND

    @property
    def identity(self) -> str:
        return f"gate:{self.gate_store_root}:{self.run_id}"

    def record_payload(self) -> dict[str, object]:
        return {
            "gate_store_root": str(self.gate_store_root),
            "generation": self.generation,
            "identity": self.identity,
            "kind": GATE_TARGET_KIND,
            "run_id": self.run_id,
        }

    @classmethod
    def freeze(cls, *, gate_store_root: Path, run_id: str) -> GateTarget:
        started_at = (gate_store_root / run_id / "started_at").read_text(encoding="utf-8")
        return cls(
            gate_store_root=gate_store_root,
            run_id=run_id,
            generation=started_at.strip(),
        )


@dataclass(frozen=True, kw_only=True)
class PaneTarget:
    backend: str
    socket_path: Path
    server_generation: str
    pane_id: str
    terminal_id: str

    @property
    def kind(self) -> str:
        return PANE_TARGET_KIND

    @property
    def identity(self) -> str:
        """An identity whose components cannot bleed into one another.

        Every component is percent-escaped before the join, because two of
        them routinely carry the separator: a Herdr pane id holds a colon by
        construction (`w1:p1`), and a socket path may hold a colon or a space.
        Joining them raw would let one component's content forge another's, so
        a pane id alone could present itself as a different server's pane.
        Escaping is what makes the server's socket path and instance
        generation unforgeable components of this string, and therefore what
        stops a REUSED pane id from aliasing a pane on another server.
        """
        return ":".join(
            (
                PANE_TARGET_KIND,
                *(
                    quote(component, safe="")
                    for component in (
                        self.backend,
                        str(self.socket_path),
                        self.server_generation,
                        self.pane_id,
                        self.terminal_id,
                    )
                ),
            )
        )

    def record_payload(self) -> dict[str, object]:
        return {
            "backend": self.backend,
            "identity": self.identity,
            "kind": PANE_TARGET_KIND,
            "pane_id": self.pane_id,
            "server_generation": self.server_generation,
            "socket_path": str(self.socket_path),
            "terminal_id": self.terminal_id,
        }


WaitTarget: TypeAlias = GateTarget | PaneTarget

# The ONE state per target kind that means "keep waiting". It is per KIND
# rather than a shared vocabulary because the two backends do not share one: a
# detached gate continues on `RUNNING` and a Herdr pane on `working`, and
# nothing else on either continues.
_STILL_RUNNING_STATE: dict[str, str] = {
    GATE_TARGET_KIND: "RUNNING",
    PANE_TARGET_KIND: "working",
}


@dataclass(frozen=True, kw_only=True)
class GateObservation:
    target: WaitTarget
    state: str
    exit_code: int | None
    observed_at: float
    fresh: bool

    @classmethod
    def running(cls, *, target: WaitTarget, observed_at: float) -> GateObservation:
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
        target: WaitTarget,
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


def observation_is_running(*, observation: GateObservation) -> bool:
    """Whether this observation's state means the wait must keep waiting.

    An unrecognised target kind RAISES rather than defaulting, because both
    available defaults are wrong in opposite directions: treating it as
    running hangs the wait until its deadline, and treating it as terminal
    returns a verdict about a target nobody managed to classify. A kind this
    build does not know is a bug in the build, not a state of a target.
    """
    return observation.state == _STILL_RUNNING_STATE[observation.target.kind]


@dataclass(frozen=True, kw_only=True)
class WaitRequest:
    wait_id: str
    session_id: str
    repository: Path
    deadline_seconds: float
    targets: tuple[WaitTarget, ...]
    # The `monotonic` instant the caller's budget began, for a caller that has
    # already spent part of it observing targets before handing them over —
    # the CLI freezes each pane's identity first. The wait measures its
    # deadline from that instant rather than restarting it, so the caller's
    # own observations and the wait spend ONE budget. None starts it at arming.
    started_at: float | None = None


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
    def launch(self, *, target: WaitTarget, timeout_seconds: float) -> Probe: ...


class GateProbeLauncher(Protocol):
    def launch(self, *, target: GateTarget, timeout_seconds: float) -> Probe: ...


class PaneProbeLauncher(Protocol):
    def launch(self, *, target: PaneTarget, timeout_seconds: float) -> Probe: ...


def freeze_gate_pointer(*, gate_store_root: Path, pointer: Path) -> GateTarget:
    return GateTarget.freeze(
        gate_store_root=gate_store_root,
        run_id=pointer.read_text(encoding="utf-8").strip(),
    )
