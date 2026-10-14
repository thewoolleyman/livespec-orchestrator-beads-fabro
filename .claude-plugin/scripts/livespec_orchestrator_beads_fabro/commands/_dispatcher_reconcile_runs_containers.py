"""The container lane of one reconciliation pass.

Where `_dispatcher_reconcile_runs.py` owns the RUN lane — the orphan join,
the export, the termination — this owns the sweep that runs beside it: build
the Docker port from the pass's own seams, and decide whether this pass is
entitled to sweep at all.

ONE SWEEP PER PASS rather than one per factory: the sandbox containers run on
the host's single Docker daemon whatever number of factories was surveyed, and
the statuses they are graded against are the union of what those factories
reported.

A PASS THAT SURVEYED NO FACTORY PERFORMS NO SWEEP, and says so rather than
reporting an empty one. Not as a saving: with no inventory at all every
container is ungradeable, so no reading could license a removal — and the
pass has reconciled nothing, so there is no reconciliation for the sweep to
be part of. The no-sweep value is distinguishable from an empty sweep, which
is what keeps "nothing was looked at" from reading as "nothing was there".
That distinction is the same one the `reconcile-runs` command draws when it
treats a pass over zero factories as a failure rather than as a clean sweep.
"""

from __future__ import annotations

from collections.abc import Mapping

from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_inputs import (
    ReconcileInputs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_container_port import (
    SandboxContainerPort,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_container_reclaim import (
    SandboxContainerSweep,
    reclaim_terminal_run_containers,
)

__all__: list[str] = ["pass_container_sweep"]


def pass_container_sweep(
    *,
    inputs: ReconcileInputs,
    surveyed: bool,
    run_statuses: Mapping[str, str | None],
    dry_run: bool,
) -> SandboxContainerSweep:
    """Sweep the host's sandbox containers, for a pass that surveyed something."""
    if not surveyed:
        return SandboxContainerSweep()
    return reclaim_terminal_run_containers(
        port=SandboxContainerPort(runner=inputs.runner, cwd=inputs.repo),
        status_by_run=run_statuses,
        dry_run=dry_run,
    )
