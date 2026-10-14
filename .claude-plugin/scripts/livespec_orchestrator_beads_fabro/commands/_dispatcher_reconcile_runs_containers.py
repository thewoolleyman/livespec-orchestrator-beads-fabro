"""The container lane of one reconciliation pass.

Where `_dispatcher_reconcile_runs.py` owns the RUN lane — the orphan join,
the export, the termination — this owns the sweep that runs beside it:
resolve the Docker daemons the surveyed factories declare, open a port onto
each, and decide whether this pass is entitled to sweep at all.

ONE SWEEP PER SURVEYED DAEMON, AND THE DAEMON IS THE FACTORY'S. The sandbox
containers run where the Fabro server runs, and this pass runs wherever the
timer that invoked it runs; on this fleet those are different hosts. A sweep
through the reconciling host's own daemon therefore inventories a host that
has never started a sandbox container and journals `containers_observed: 0`
— a record indistinguishable at every field from a sweep over a clean
factory. Measured 2026-10-14: every sweep record written on the reconciling
host read zero while twelve `fabro-run-*` containers ran on `hp`, four of
them left by runs that server reported `failed`.

DISTINCT DAEMONS RATHER THAN DISTINCT FACTORIES, because two factories may
serve one host — a production server beside an upgrade candidate — and a
second sweep of one daemon would grade containers the first had just
removed, reporting an inventory that shrank for reasons its own record
cannot show. The factories sharing a daemon are named together on its sweep
instead.

EVERY DAEMON IS GRADED AGAINST THE UNION of the statuses the surveyed
factories reported, never against one factory's own. A container's run is
served by whichever factory launched it, so a sweep that asked only the
factory it was addressing would read every sibling server's container as a
run nobody reported and hold it for as long as it keeps running.

A FACTORY THAT DECLARES NO DAEMON IS NOT SWEPT. The declaration is the only
thing that says where that factory's containers run: a server url is no
evidence of it — a loopback url is as likely to be a forwarded tunnel as a
local engine — so inferring one fails in the expensive direction, removing a
container on the reconciling host on the strength of a status read from a
different host.

A PASS THAT SURVEYED NO FACTORY PERFORMS NO SWEEP, and the empty tuple says
so. Not as a saving: with no inventory at all every container is ungradeable,
so no reading could license a removal — and the pass has reconciled nothing,
so there is no reconciliation for the sweep to be part of. That is the same
distinction the `reconcile-runs` command draws when it treats a pass over
zero factories as a failure rather than as a clean sweep.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_inputs import (
    ReconcileInputs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_container_port import (
    SandboxContainerPort,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_container_reclaim import (
    SandboxContainerSweep,
    journal_container_sweep,
    reclaim_terminal_run_containers,
)

__all__: list[str] = ["pass_container_sweeps"]


@dataclass(frozen=True, kw_only=True)
class _SurveyedDaemon:
    """One Docker daemon to sweep, and every surveyed factory it serves."""

    docker_host: str
    factory_names: tuple[str, ...]


def pass_container_sweeps(
    *,
    inputs: ReconcileInputs,
    factories: Sequence[FactoryTarget],
    run_statuses: Mapping[str, str | None],
    dry_run: bool,
) -> tuple[SandboxContainerSweep, ...]:
    """Sweep every surveyed factory's own daemon, and record what each did.

    The ACT and its RECORD are composed here rather than inside the reclaim
    driver, which keeps the one decision a dry run turns on — write nothing —
    beside the one the survey turns on, instead of splitting them across two
    modules that each hold half of it.
    """
    sweeps = tuple(
        _daemon_sweep(inputs=inputs, daemon=daemon, run_statuses=run_statuses, dry_run=dry_run)
        for daemon in _surveyed_daemons(factories=factories)
    )
    if not dry_run:
        for sweep in sweeps:
            journal_container_sweep(journal=inputs.journal, sweep=sweep)
    return sweeps


def _surveyed_daemons(*, factories: Sequence[FactoryTarget]) -> tuple[_SurveyedDaemon, ...]:
    """Group the surveyed factories by the daemon each one declares."""
    by_host: dict[str, list[str]] = {}
    for factory in factories:
        if factory.docker_host is None:
            continue
        by_host.setdefault(factory.docker_host, []).append(factory.name)
    return tuple(
        _SurveyedDaemon(docker_host=docker_host, factory_names=tuple(names))
        for docker_host, names in by_host.items()
    )


def _daemon_sweep(
    *,
    inputs: ReconcileInputs,
    daemon: _SurveyedDaemon,
    run_statuses: Mapping[str, str | None],
    dry_run: bool,
) -> SandboxContainerSweep:
    return reclaim_terminal_run_containers(
        port=SandboxContainerPort(
            runner=inputs.runner,
            cwd=inputs.repo,
            docker_host=daemon.docker_host,
        ),
        status_by_run=run_statuses,
        dry_run=dry_run,
    )
