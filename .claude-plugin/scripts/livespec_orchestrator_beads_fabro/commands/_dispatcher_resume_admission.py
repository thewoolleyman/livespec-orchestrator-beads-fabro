"""Admission and launch for ordinary and proof-only resumed runs."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_ledger import (
    explicit_dispatch_factory,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_run import DispatchLaunchContext
from livespec_orchestrator_beads_fabro.commands._dispatcher_prelaunch_cpu import PrelaunchCpuProfile
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_entry import (
    RESUME_PROOF_ONLY_ARG,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_rework_admission import ReworkPass
from livespec_orchestrator_beads_fabro.commands._dispatcher_screened_verdict import (
    screened_verdict_of,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = ["admit_and_dispatch_resume"]

_NO_REWORK = ReworkPass(scope_ids=frozenset())


@dataclass(frozen=True, kw_only=True)
class ResumeAdmissionPorts:
    """The command-owned seams used by the resume admission sequence."""

    admit: Callable[..., Any]
    dispatch: Callable[..., DispatchOutcome]
    target_args: Callable[..., argparse.Namespace]


@dataclass(frozen=True, kw_only=True)
class ResumeAdmissionRequest:
    """The resumed run and its environment at the admission boundary."""

    args: argparse.Namespace
    repo: Path
    items: list[WorkItem]
    item: WorkItem
    journal: JournalFile
    launch: DispatchLaunchContext


def admit_and_dispatch_resume(
    *, request: ResumeAdmissionRequest, ports: ResumeAdmissionPorts
) -> DispatchOutcome:
    """Launch the proof arm directly, or admit an ordinary resumed run first."""
    if getattr(request.args, RESUME_PROOF_ONLY_ARG, False):
        return ports.dispatch(
            args=ports.target_args(
                args=request.args, repo=request.repo, work_item_id=request.item.id, resume=True
            ),
            repo=request.repo,
            item=request.item,
            journal=request.journal,
            launch=request.launch,
        )
    admission = cast(PrelaunchCpuProfile, request.launch.prelaunch_profile).phase(
        name="admission",
        action=lambda: ports.admit(
            repo=request.repo,
            items=request.items,
            candidates=[request.item],
            journal=request.journal,
            enforce_cap=True,
            rework=_NO_REWORK,
            explicit_factory=explicit_dispatch_factory(args=request.args),
            screened=screened_verdict_of(args=request.args),
            resume_ids=frozenset({request.item.id}),
        ),
    )
    return (
        admission.refused
        + admission.deferred
        + [
            ports.dispatch(
                args=ports.target_args(
                    args=request.args, repo=request.repo, work_item_id=admitted.id, resume=True
                ),
                repo=request.repo,
                item=admitted,
                journal=request.journal,
                verdict=admission.verdict,
                launch=request.launch,
            )
            for admitted in admission.admitted
        ]
    )[0]
