"""The shared entry phases of a `resume --item` dispatch."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_prelaunch_cpu import (
    PrelaunchCpuProfile,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "ResumePrelaunch",
    "prepare_resume_prelaunch",
]


@dataclass(frozen=True, kw_only=True)
class ResumePrelaunch:
    """The entry facts available after a resume reaches target selection."""

    janitor: tuple[str, ...] | None
    items: list[WorkItem]
    journal: JournalFile


def prepare_resume_prelaunch(
    *,
    profile: PrelaunchCpuProfile,
    preamble: Callable[[], tuple[tuple[str, ...] | None, int | None]],
    arm_otel: Callable[[], None],
    prepare: Callable[[], tuple[list[WorkItem], JournalFile] | None],
    precondition_exit: int,
) -> ResumePrelaunch | int:
    """Run and account for the setup every resume performs before selection."""
    janitor, preamble_exit = profile.phase(name="dispatch-preamble", action=preamble)
    if preamble_exit is not None:
        return preamble_exit
    _ = profile.phase(name="otel-egress", action=arm_otel)
    prepared = profile.phase(name="ledger-prepare", action=prepare)
    if prepared is None:
        return precondition_exit
    items, journal = prepared
    return ResumePrelaunch(janitor=janitor, items=items, journal=journal)
