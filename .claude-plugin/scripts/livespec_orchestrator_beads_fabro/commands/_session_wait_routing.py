"""Routing from a wait target's kind to the adapter that observes it."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from typing_extensions import assert_never

from livespec_orchestrator_beads_fabro.commands._session_wait_gate import (
    GateStatusLauncher,
    observe_gate_target,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_pane import (
    HerdrPaneLauncher,
    observe_pane_target,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_types import (
    PANE_TARGET_KIND,
    GateObservation,
    GateProbeLauncher,
    GateTarget,
    PaneProbeLauncher,
    PaneTarget,
    Probe,
    ProbeLauncher,
    WaitTarget,
)

__all__: list[str] = [
    "RoutingLauncher",
    "default_wait_launcher",
    "observe_wait_target",
    "wait_target_from_payload",
]


@dataclass(frozen=True, kw_only=True)
class RoutingLauncher:
    """One launcher over a mixed target set, routed by each target's kind."""

    gate: GateProbeLauncher
    pane: PaneProbeLauncher

    def launch(self, *, target: WaitTarget, timeout_seconds: float) -> Probe:
        match target:
            case PaneTarget():
                return self.pane.launch(target=target, timeout_seconds=timeout_seconds)
            case GateTarget():
                return self.gate.launch(target=target, timeout_seconds=timeout_seconds)
            case _:
                assert_never(target)


def default_wait_launcher(*, repository: Path) -> ProbeLauncher:
    return RoutingLauncher(
        gate=GateStatusLauncher(repository=repository),
        pane=HerdrPaneLauncher(),
    )


def observe_wait_target(*, target: WaitTarget, observed_at: float) -> GateObservation:
    """One fresh observation of any target kind, through its own adapter."""
    match target:
        case PaneTarget():
            return observe_pane_target(target=target, observed_at=observed_at)
        case GateTarget():
            return observe_gate_target(target=target, observed_at=observed_at)
        case _:
            assert_never(target)


def wait_target_from_payload(*, payload: dict[str, object]) -> WaitTarget:
    """The frozen target that one registered record's target entry describes.

    Dispatch is on the record's own `kind`, which every record this build
    writes carries. Anything else is read as a gate target, because that is
    exactly how every record written before pane targets existed must be read.
    """
    if payload.get("kind") == PANE_TARGET_KIND:
        return PaneTarget(
            backend=str(payload["backend"]),
            socket_path=Path(str(payload["socket_path"])),
            server_generation=str(payload["server_generation"]),
            pane_id=str(payload["pane_id"]),
            terminal_id=str(payload["terminal_id"]),
        )
    return GateTarget(
        gate_store_root=Path(str(payload["gate_store_root"])),
        run_id=str(payload["run_id"]),
        generation=str(payload["generation"]),
    )
