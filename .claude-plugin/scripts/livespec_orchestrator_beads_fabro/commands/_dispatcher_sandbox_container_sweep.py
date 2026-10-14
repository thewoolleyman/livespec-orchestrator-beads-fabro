"""Which sandbox containers a terminal run has left behind, and which are live.

PURE. The decision is a function of one container inventory and the run
statuses the surveyed Fabro servers reported, so it is exercisable without a
Docker daemon — which is the whole reason it lives apart from the port that
reads one.

A `fabro-run-<run id>` container outlives its run: the run reaches a terminal
state and the container keeps running inside `fabro-sandbox.slice`, spending
the aggregate memory and CPU envelope that the LIVE runs share. So the leak
does not merely waste idle capacity, it raises the OOM and throttle risk for
real work every time a run fails.

THE TERMINAL SET IS AN ALLOW-LIST, NOT THE COMPLEMENT OF THE LIVE ONE, and
that is the one decision here worth not inverting. Read as a complement, a
status kind this build has never seen — a newer engine's own spelling, a
queue state the Petri-era server reports — classifies as terminal, and the
sweep then kills a container whose run is still working. The expensive
direction is removal, so an unrecognised kind is HELD and says so.

THE TWO OUTCOMES ARE TWO TYPES rather than one record carrying a disposition
field, which is what makes a removal unable to travel without the terminal
status that justified it: `ContainerRemoval.run_status_kind` is not optional,
while a hold carries both its reason and whatever status it managed to read.

THREE HOLD REASONS, because three different absences reach this decision and
they support different conclusions. `run-unobserved` is a container whose run
no surveyed server reported at all: a pruned record, or a run served by a
factory this pass did not survey. `run-status-unrecognised` is a run that WAS
reported, under a kind this build cannot grade. `run-live` is the ordinary
answer — the run is running, runnable, starting, paused or parked at a gate.
Collapsing them would make a sweep that had gone blind read exactly like a
sweep over a healthy host.

`NON_TERMINAL_STATUS_KINDS` is the run reconciler's own set rather than a
second list: the reconciler's orphan join and this sweep must agree about
which runs are still alive, and two lists that happened to agree today would
be two places for a new engine's status kind to be added.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_attribution import (
    NON_TERMINAL_STATUS_KINDS,
)

__all__: list[str] = [
    "CONTAINER_HOLD_RUN_LIVE",
    "CONTAINER_HOLD_RUN_UNOBSERVED",
    "CONTAINER_HOLD_STATUS_UNRECOGNISED",
    "SANDBOX_CONTAINER_NAME_PREFIX",
    "TERMINAL_RUN_STATUS_KINDS",
    "ContainerHold",
    "ContainerPlan",
    "ContainerRemoval",
    "SandboxContainer",
    "container_run_id",
    "sandbox_container_plan",
]

# How Fabro names the sandbox container it starts for a run. The run id
# follows it verbatim, which is what makes a container attributable to a run
# without asking the daemon for its labels.
SANDBOX_CONTAINER_NAME_PREFIX = "fabro-run-"

# The kinds that mean the run is over. Both spellings of a cancelled run are
# accepted because the engine and this repo's own telemetry disagree about it,
# and a sweep that recognised one would silently hold every container left by
# the other.
TERMINAL_RUN_STATUS_KINDS: tuple[str, ...] = (
    "canceled",
    "cancelled",
    "failed",
    "succeeded",
)

CONTAINER_HOLD_RUN_LIVE = "run-live"
CONTAINER_HOLD_RUN_UNOBSERVED = "run-unobserved"
CONTAINER_HOLD_STATUS_UNRECOGNISED = "run-status-unrecognised"


@dataclass(frozen=True, kw_only=True)
class SandboxContainer:
    """One `fabro-run-*` container as the daemon reported it.

    `memory_limit_bytes` is `None` when the limit could not be READ and `0`
    when the daemon reported the container as having none of its own. The two
    are not interchangeable: zero is a measurement saying this container was
    free to consume the whole slice, and `None` is the absence of one.
    """

    name: str
    run_id: str
    memory_limit_bytes: int | None


@dataclass(frozen=True, kw_only=True)
class ContainerRemoval:
    """One container whose run the owning server reported in a terminal state."""

    container: SandboxContainer
    run_status_kind: str


@dataclass(frozen=True, kw_only=True)
class ContainerHold:
    """One container this sweep spares, and the reading that spares it."""

    container: SandboxContainer
    run_status_kind: str | None
    hold_reason: str


@dataclass(frozen=True, kw_only=True)
class ContainerPlan:
    """What one inventory grades out to: what to remove, and what to leave."""

    removals: tuple[ContainerRemoval, ...]
    holds: tuple[ContainerHold, ...]


def container_run_id(*, name: str) -> str:
    """The run id a sandbox container's name carries."""
    return name.removeprefix(SANDBOX_CONTAINER_NAME_PREFIX)


def sandbox_container_plan(
    *,
    containers: Sequence[SandboxContainer],
    status_by_run: Mapping[str, str | None],
) -> ContainerPlan:
    """Grade every observed container against the statuses the servers gave."""
    graded = tuple(
        _graded(container=container, status=status_by_run.get(container.run_id))
        for container in containers
    )
    return ContainerPlan(
        removals=tuple(entry for entry in graded if isinstance(entry, ContainerRemoval)),
        holds=tuple(entry for entry in graded if isinstance(entry, ContainerHold)),
    )


def _graded(
    *,
    container: SandboxContainer,
    status: str | None,
) -> ContainerRemoval | ContainerHold:
    if status is None:
        return ContainerHold(
            container=container,
            run_status_kind=None,
            hold_reason=CONTAINER_HOLD_RUN_UNOBSERVED,
        )
    if status in NON_TERMINAL_STATUS_KINDS:
        return ContainerHold(
            container=container,
            run_status_kind=status,
            hold_reason=CONTAINER_HOLD_RUN_LIVE,
        )
    if status not in TERMINAL_RUN_STATUS_KINDS:
        return ContainerHold(
            container=container,
            run_status_kind=status,
            hold_reason=CONTAINER_HOLD_STATUS_UNRECOGNISED,
        )
    return ContainerRemoval(container=container, run_status_kind=status)
