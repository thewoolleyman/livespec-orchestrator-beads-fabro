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
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_container_port import (
    SandboxContainerPort,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_container_sweep import (
    ContainerHold,
    ContainerRemoval,
    sandbox_container_plan,
)

__all__: list[str] = [
    "HeldContainer",
    "ReclaimedContainer",
    "SandboxContainerSweep",
    "reclaim_terminal_run_containers",
]

_DRY_RUN_DETAIL = "dry run: nothing was removed"
_NO_SWEEP_DETAIL = "no sandbox-container sweep was performed"


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
    """One sweep over the host's running sandbox containers.

    The all-default value is the NO-SWEEP state, and `observed` defaults to
    False for that reason: a caller holding no factory to survey performed no
    sweep, which is not the same claim as a sweep that found nothing.
    """

    reclaimed: tuple[ReclaimedContainer, ...] = ()
    held: tuple[HeldContainer, ...] = ()
    observed: bool = False
    detail: str = _NO_SWEEP_DETAIL
    dry_run: bool = False


def reclaim_terminal_run_containers(
    *,
    port: SandboxContainerPort,
    status_by_run: Mapping[str, str | None],
    dry_run: bool = False,
) -> SandboxContainerSweep:
    """Remove every observed container whose run the servers report terminal."""
    inventory = port.inventory()
    plan = sandbox_container_plan(
        containers=inventory.containers,
        status_by_run=status_by_run,
    )
    return SandboxContainerSweep(
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
