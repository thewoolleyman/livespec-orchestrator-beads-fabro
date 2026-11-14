"""The `resume` route, with the needs-human refs it passes over listed.

A `resume` takes no needs-human ref: it finishes the run's own publication. The
clause nonetheless requires its `recovery-route` record to carry
`passed_over_needs_human`, listing each ref that carries one of the item's earlier
runs, so an operator reading the record can see which preserved trees the resume
did not take. The identification is the pass's one listing (see
`_dispatcher_recovery_pass_listing`), and "an identification that cannot be taken
is the existing unobservable-measurement hold and MUST NOT be read as absence": a
resume recorded as passing over nothing, off a listing nobody could read, would
state a fact no measurement supports.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human_refs import (
    NeedsHumanRefsUnobservable,
    NeedsHumanScope,
    carrying_needs_human_refs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_measurements import (
    MEASUREMENT_PRESERVED_WORK,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_preserved import (
    NEEDS_HUMAN_REF_PREFIX,
    SEED_REMOTE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_records import (
    recovery_held_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import (
    ROUTE_HELD,
    ROUTE_RESUME,
    RecoveryHold,
    RecoveryMeasurement,
    RecoveryResume,
    RecoveryRoute,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_run_age import (
    foreign_run_ids,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection_journal import (
    read_journal_records,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_anchor import ResumeAnchor
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_observation import ResumeGather
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = ["resume_of", "resume_with_listing"]

_GIT_TIMEOUT_SECONDS = 120.0


def resume_of(*, gather: ResumeGather, anchor: ResumeAnchor, pull_request: int) -> RecoveryResume:
    """What a `resume` route hands its launch, from the gather and its narrowed anchor."""
    return RecoveryResume(
        entry_node=anchor.resumed_at,
        head=anchor.head,
        pull_request=pull_request,
        earlier_run_ids=gather.earlier_run_ids,
        source=anchor.source,
        workflow_name=gather.workflow_name,
    )


def resume_with_listing(
    *,
    runner: CommandRunner,
    repo: Path,
    item: WorkItem,
    journal: JournalFile,
    gather: ResumeGather,
    resume: RecoveryResume,
) -> RecoveryRoute:
    """The `resume` route listing every carrying needs-human ref, or a recorded hold."""
    carrying = carrying_needs_human_refs(
        runner=runner,
        repo=repo,
        scope=NeedsHumanScope(
            run_ids=gather.earlier_run_ids,
            foreign_run_ids=foreign_run_ids(
                records=read_journal_records(journal_path=journal.path),
                work_item_id=item.id,
                own=gather.earlier_run_ids,
            ),
        ),
        ref_prefix=NEEDS_HUMAN_REF_PREFIX,
        remote=SEED_REMOTE,
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
    )
    if isinstance(carrying, NeedsHumanRefsUnobservable):
        hold = RecoveryHold(
            measurements=(
                RecoveryMeasurement(
                    name=MEASUREMENT_PRESERVED_WORK,
                    detail=(
                        f"{carrying.detail}, so the resume cannot establish every "
                        "needs-human ref it passes over"
                    ),
                ),
            )
        )
        journal.append(record=recovery_held_record(work_item_id=item.id, hold=hold))
        return RecoveryRoute(work_item_id=item.id, route=ROUTE_HELD, hold=hold)
    return replace(
        RecoveryRoute(work_item_id=item.id, route=ROUTE_RESUME, resume=resume),
        passed_over_needs_human=tuple((one.ref, one.commit_sha) for one in carrying),
    )
