"""Retain progress-watchdog evidence while a dropped client is reattached."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._dispatcher_watchdog import (
    StallVerdict,
    decide_stall,
    quiet_window_seconds,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroInspectResult, FabroPort

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import JournalWriter
    from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_reattach_watch import (
        ReattachTiming,
    )
    from livespec_orchestrator_beads_fabro.commands._dispatcher_watchdog import LivenessSample

__all__: list[str] = ["ReattachStallWatch"]


@dataclass(frozen=True, kw_only=True)
class _LivenessInputs:
    """The facts that form one reattach liveness sample."""

    plan: DispatchPlan
    port: FabroPort
    run_id: str
    observed_at: float
    state: object
    run_record: object | None
    journal: JournalWriter


@dataclass(kw_only=True)
class ReattachStallWatch:
    """Liveness evidence retained while a reattached running run is observed."""

    plan: DispatchPlan
    journal: JournalWriter
    run_id: str
    timing: ReattachTiming
    port: FabroPort
    liveness_state: object = field(default_factory=lambda: _liveness_state())
    samples: list[LivenessSample] = field(default_factory=list)

    def cancel_if_quiet(self, *, inspect: FabroInspectResult) -> bool:
        """Cancel only after retained samples prove the entire quiet window."""
        self.samples.append(
            liveness_sample(
                inputs=_LivenessInputs(
                    plan=self.plan,
                    port=self.port,
                    run_id=self.run_id,
                    observed_at=self.timing.clock(),
                    state=self.liveness_state,
                    run_record=inspect.payload,
                    journal=self.journal,
                )
            )
        )
        samples = tuple(self.samples)
        if (
            decide_stall(samples=samples, stall_seconds=self.plan.stall_window.seconds)
            != StallVerdict.STALLED
        ):
            return False
        return cancel_stalled_run(
            plan=self.plan,
            port=self.port,
            journal=self.journal,
            run_id=self.run_id,
            quiet_seconds=quiet_window_seconds(samples=samples),
        )


def _liveness_state() -> object:
    """Construct liveness state after the engine's reattach import has settled."""
    from livespec_orchestrator_beads_fabro.commands._dispatcher_io_liveness_probe import (
        LivenessState,
    )

    return LivenessState()


def liveness_sample(*, inputs: _LivenessInputs) -> LivenessSample:
    """Take a liveness sample without making the engine import cyclic."""
    from livespec_orchestrator_beads_fabro.commands._dispatcher_io_liveness_probe import (
        LivenessState,
    )
    from livespec_orchestrator_beads_fabro.commands._dispatcher_io_liveness_probe import (
        liveness_sample as resolved_liveness_sample,
    )

    return resolved_liveness_sample(
        plan=inputs.plan,
        port=inputs.port,
        run_id=inputs.run_id,
        heartbeat_path=None,
        dispatch_id=None,
        observed_at=inputs.observed_at,
        state=cast("LivenessState", inputs.state),
        run_record=inputs.run_record,
        journal=inputs.journal,
    )


def cancel_stalled_run(
    *,
    plan: DispatchPlan,
    port: FabroPort,
    journal: JournalWriter,
    run_id: str,
    quiet_seconds: float | None,
) -> bool:
    """Cancel lazily so the engine's import graph remains acyclic."""
    from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_cancel import (
        cancel_stalled_run as resolved_cancel_stalled_run,
    )

    return resolved_cancel_stalled_run(
        dispatch_id=None,
        plan=plan,
        port=port,
        journal=journal,
        run_id=run_id,
        quiet_seconds=quiet_seconds,
    )
