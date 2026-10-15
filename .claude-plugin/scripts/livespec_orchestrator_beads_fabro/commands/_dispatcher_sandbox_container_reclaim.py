"""Reclaim the sandbox containers that terminal runs left running.

The driver that composes the Docker port with the pure decision ladder: read
the inventory once, grade every container against the statuses the surveyed
Fabro servers reported, remove the ones whose run is over, and report both
lanes.

THE TWO LANES ARE SEPARATE COLLECTIONS, for the same reason the run
reconciler keeps its held runs out of its reconciled ones: a held container
is one this pass deliberately spared, and nothing downstream should be able
to hand it to the removal path by a later edit.

A HELD CONTAINER IS REPORTED, not merely skipped. "Removes every terminal
run's container and leaves every live one" is a claim about both halves, and
a sweep that reported only its removals would leave no evidence that it had
even seen the containers it spared.

A REMOVAL THE DAEMON REFUSED IS REPORTED AS A REFUSAL rather than counted as
a reclaim: `removed` is read off the exit code, so the record cannot claim an
envelope that was never given back. It does not move the reconciliation
pass's own exit code — the pass grades the reconciliation of RUNS, and a
daemon that would not remove a container says nothing about whether a run was
correctly reconciled — so the refusal travels on the journal, which is where
a reader looking for it will be.

THE JOURNAL IS THE ONLY DURABLE ACCOUNT OF THIS LANE, and the three records
it writes exist for three different absences. A per-container RECLAIMED
record names the container, its run, that run's terminal status and the
limit reclaimed, because after the removal a `docker ps` shows exactly what a
host that never leaked anything shows. A per-container HELD record names the
reading that spared it, because the claim is about both halves and nothing
else evidences the second. And ONE pass record carries `inventory_observed`,
which is what tells a daemon that refused the listing apart from a host with
nothing on it — both leave zero per-container records.

EVERY ONE OF THE THREE NAMES THE DAEMON IT WAS READ FROM, because one pass
writes one set of them per surveyed factory host and each field in them is a
measurement of that host alone. Unattributed, two hosts' records are
indistinguishable, so a leaking factory and a clean one average into a
reading about neither — and a container name cannot stand in for the
attribution, since it is unique to its daemon only by convention and a
re-dispatched work-item routinely puts one run id on two hosts.

TWO AGGREGATES THAT COULD HAVE BEEN ONE, deliberately kept apart in each
case. A refused removal is counted under `containers_remove_failed` and not
under `containers_removed`, because the second reads as reclaimed capacity.
And `reclaimed_limits_unmeasured` travels beside the byte sum because a limit
nobody could read contributes nothing to it: without the count, the sum reads
as a complete measurement while silently omitting a container.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import JournalWriter
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_container_port import (
    SandboxContainerPort,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_container_sweep import (
    ContainerHold,
    ContainerRemoval,
    sandbox_container_plan,
)

__all__: list[str] = [
    "JOURNAL_STAGE_CONTAINER_HELD",
    "JOURNAL_STAGE_CONTAINER_RECLAIMED",
    "JOURNAL_STAGE_CONTAINER_SWEEP",
    "HeldContainer",
    "ReclaimedContainer",
    "SandboxContainerSweep",
    "journal_container_sweep",
    "reclaim_terminal_run_containers",
]

JOURNAL_STAGE_CONTAINER_RECLAIMED = "sandbox-container-reclaimed"
JOURNAL_STAGE_CONTAINER_HELD = "sandbox-container-held"
JOURNAL_STAGE_CONTAINER_SWEEP = "sandbox-container-sweep"

_DRY_RUN_DETAIL = "dry run: nothing was removed"


@dataclass(frozen=True, kw_only=True)
class ReclaimedContainer:
    """One container a terminal run left behind, and what became of it."""

    container_name: str
    run_id: str
    run_status_kind: str
    memory_limit_bytes: int | None
    removed: bool
    detail: str


@dataclass(frozen=True, kw_only=True)
class HeldContainer:
    """One container this pass spared, and the reading that spared it."""

    container_name: str
    run_id: str
    run_status_kind: str | None
    memory_limit_bytes: int | None
    hold_reason: str


@dataclass(frozen=True, kw_only=True)
class SandboxContainerSweep:
    """One sweep over ONE factory host's running sandbox containers.

    `docker_host` and `factory_names` are WHOSE inventory this is, and they
    are not interchangeable: the daemon is what the sweep was addressed to,
    while the factory names are what an operator configured and can act on.
    Neither has a default, because every other field here is a measurement of
    ONE host and an unattributed measurement of one host reads as a
    measurement of the fleet — the empty tuple of factory names is a
    deliberate "none named" that a caller states, not one it can omit.

    `docker_host` is None ONLY for a factory whose daemon had no address to
    reach, which is the one sweep that took no reading at all; it is never a
    stand-in for the local daemon. That value travels with `observed` False,
    so a reader never has to infer the absence of a reading from the absence
    of an address.

    `detail` carries no default either: it is what tells a sweep that looked
    and found nothing apart from one that could not look, and a default would
    make the second borrow the first's words. `observed` defaults to False
    for the matching reason — a value built without asserting a reading must
    not claim one. A pass that surveyed no factory performs no sweep at all,
    which is the empty TUPLE of sweeps rather than any value of this type.
    """

    docker_host: str | None
    factory_names: tuple[str, ...]
    detail: str
    reclaimed: tuple[ReclaimedContainer, ...] = ()
    held: tuple[HeldContainer, ...] = ()
    observed: bool = False
    dry_run: bool = False


def reclaim_terminal_run_containers(
    *,
    port: SandboxContainerPort,
    status_by_run: Mapping[str, str | None],
    factory_names: Sequence[str] = (),
    dry_run: bool = False,
) -> SandboxContainerSweep:
    """Remove every observed container whose run the servers report terminal.

    The daemon is read off the PORT rather than passed beside it, so the
    address this sweep records is necessarily the one its own calls went to —
    which is why that attribution has no default and this one does: the
    factory names are a mapping back to configuration that a caller holding
    only a daemon address genuinely does not have.
    """
    inventory = port.inventory()
    plan = sandbox_container_plan(
        containers=inventory.containers,
        status_by_run=status_by_run,
    )
    return SandboxContainerSweep(
        docker_host=port.docker_host,
        factory_names=tuple(factory_names),
        reclaimed=tuple(
            _reclaimed(port=port, removal=removal, dry_run=dry_run) for removal in plan.removals
        ),
        held=tuple(_held(hold=hold) for hold in plan.holds),
        observed=inventory.observed,
        detail=inventory.detail,
        dry_run=dry_run,
    )


def _reclaimed(
    *,
    port: SandboxContainerPort,
    removal: ContainerRemoval,
    dry_run: bool,
) -> ReclaimedContainer:
    if dry_run:
        return _reclaimed_record(removal=removal, removed=False, detail=_DRY_RUN_DETAIL)
    removed = port.remove(name=removal.container.name)
    return _reclaimed_record(
        removal=removal,
        removed=removed.exit_code == 0,
        detail=f"docker rm -f exited {removed.exit_code}",
    )


def _reclaimed_record(
    *,
    removal: ContainerRemoval,
    removed: bool,
    detail: str,
) -> ReclaimedContainer:
    return ReclaimedContainer(
        container_name=removal.container.name,
        run_id=removal.container.run_id,
        run_status_kind=removal.run_status_kind,
        memory_limit_bytes=removal.container.memory_limit_bytes,
        removed=removed,
        detail=detail,
    )


def _held(*, hold: ContainerHold) -> HeldContainer:
    return HeldContainer(
        container_name=hold.container.name,
        run_id=hold.container.run_id,
        run_status_kind=hold.run_status_kind,
        memory_limit_bytes=hold.container.memory_limit_bytes,
        hold_reason=hold.hold_reason,
    )


def journal_container_sweep(*, journal: JournalWriter, sweep: SandboxContainerSweep) -> None:
    """Record one sweep: every container it touched, then the pass that touched them.

    The per-container records come FIRST and the pass record LAST, so the
    summary follows the evidence it summarises rather than preceding it.
    """
    for run in sweep.reclaimed:
        journal.append(
            record={
                "stage": JOURNAL_STAGE_CONTAINER_RECLAIMED,
                "docker_host": sweep.docker_host,
                "container_name": run.container_name,
                "run_id": run.run_id,
                "run_status_kind": run.run_status_kind,
                "memory_limit_bytes": run.memory_limit_bytes,
                "removed": run.removed,
                "detail": run.detail,
            }
        )
    for hold in sweep.held:
        journal.append(
            record={
                "stage": JOURNAL_STAGE_CONTAINER_HELD,
                "docker_host": sweep.docker_host,
                "container_name": hold.container_name,
                "run_id": hold.run_id,
                "run_status_kind": hold.run_status_kind,
                "memory_limit_bytes": hold.memory_limit_bytes,
                "hold_reason": hold.hold_reason,
            }
        )
    journal.append(record=_pass_record(sweep=sweep))


def _pass_record(*, sweep: SandboxContainerSweep) -> dict[str, object]:
    removed = tuple(run for run in sweep.reclaimed if run.removed)
    return {
        "stage": JOURNAL_STAGE_CONTAINER_SWEEP,
        "docker_host": sweep.docker_host,
        "factory_names": list(sweep.factory_names),
        "inventory_observed": sweep.observed,
        "detail": sweep.detail,
        "containers_observed": len(sweep.reclaimed) + len(sweep.held),
        "containers_removed": len(removed),
        "containers_remove_failed": len(sweep.reclaimed) - len(removed),
        "containers_held": len(sweep.held),
        "memory_limit_bytes_reclaimed": _reclaimed_bytes(removed=removed),
        "reclaimed_limits_unmeasured": sum(1 for run in removed if run.memory_limit_bytes is None),
    }


def _reclaimed_bytes(*, removed: Sequence[ReclaimedContainer]) -> int:
    return sum(run.memory_limit_bytes for run in removed if run.memory_limit_bytes is not None)
