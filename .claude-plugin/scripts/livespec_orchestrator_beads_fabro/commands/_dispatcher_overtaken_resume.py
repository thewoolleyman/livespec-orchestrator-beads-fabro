"""Resume an overtaken armed pull request in the invocation that found it overtaken.

`SPECIFICATION/contracts.md` "Armed pull request overtaken by the default
branch" requires the resume to run "through the same path `resume --item
<work-item-id>` takes" and to be "subject to every refusal and bound" of that
command. The measurement, the ladder, the journal record and the launch are the
resume command's own pieces, so this module only sequences them for an item the
Dispatcher has just resolved to `ready`. It does not import the resume command:
that command imports the dispatch loop, which offers this resume to its
dispositions, so the launch is handed in instead.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from functools import partial
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_lock import (
    dispatch_lock_path,
    release_dispatch_lock,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_close import load_items
from livespec_orchestrator_beads_fabro.commands._dispatcher_lifecycle_writes import (
    write_blocked_state_and_reconcile,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_run import DispatchLaunchContext
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_selection import run_id
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import journal_path
from livespec_orchestrator_beads_fabro.commands._dispatcher_prelaunch_cpu import (
    PrelaunchCpuProfile,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_args import resumed_args
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_journal import (
    resume_journal_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_observation import (
    gather_resume,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_refusal_record import (
    record_resume_refusal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_refusals import resume_refusals

__all__: list[str] = ["bound_overtaken_resume", "resume_overtaken_item"]

_UNANCHORED_REFUSAL = (
    "the resume gathered neither an open pull request nor an anchoring Proof of"
    " Done record for this item, so there is nothing to resume from"
)


def bound_overtaken_resume(
    *,
    args: argparse.Namespace,
    repo: Path,
    journal: JournalFile,
    janitor: tuple[str, ...] | None,
    admit_and_dispatch: Callable[..., DispatchOutcome],
) -> Callable[..., DispatchOutcome]:
    """The resume a launching command offers a dispatch whose pull request is overtaken.

    The returned callable takes only the work-item id. The dispatch it is handed
    to is launched WITHOUT one, which is what bounds the automatic resume to one
    attempt per invocation.
    """
    return partial(
        resume_overtaken_item,
        args=args,
        repo=repo,
        journal=journal,
        janitor=janitor,
        admit_and_dispatch=admit_and_dispatch,
    )


def resume_overtaken_item(
    *,
    args: argparse.Namespace,
    repo: Path,
    journal: JournalFile,
    janitor: tuple[str, ...] | None,
    admit_and_dispatch: Callable[..., DispatchOutcome],
    work_item_id: str,
) -> DispatchOutcome:
    """Resume the item through the path `resume --item` takes, in this invocation.

    The ownership lock this invocation holds is released first, so the ladder's
    live-lock refusal does not read the invocation itself as a competing dispatch.
    Every other refusal applies unchanged. A refusal records its ledger comment,
    rests the item at `blocked` / `needs-human` and reports it, because the item
    was already resolved to `ready` and must not be left claimable under a
    refused resume.
    """
    release_dispatch_lock(path=dispatch_lock_path(repo=repo, work_item_id=work_item_id))
    items = load_items(repo=repo)
    item = next(one for one in items if one.id == work_item_id)
    gather = gather_resume(
        args=args,
        repo=repo,
        item=item,
        journal_path=journal_path(args=args, repo=repo),
        runner=ShellCommandRunner(),
    )
    anchor = gather.anchor
    pull_request = gather.observation.pull_request
    refusals = resume_refusals(observation=gather.observation)
    if refusals or anchor is None or pull_request is None:
        # BEFORE the blocked transition, as the contract orders the cause comment,
        # and fail-soft: the comment names the refusal the outcome detail names.
        named = refusals or (_UNANCHORED_REFUSAL,)
        record_resume_refusal(
            repo=repo,
            work_item_id=item.id,
            pr_number=pull_request,
            pr_head=anchor.head if anchor is not None else None,
            refusals=named,
            journal=journal,
        )
        write_blocked_state_and_reconcile(
            repo=repo,
            item_id=item.id,
            status="blocked",
            blocked_reason="needs-human",
            admission_policy="manual",
        )
        journal.append(
            record={
                "stage": "needs-human-blocked",
                "work_item_id": item.id,
                "reason": "needs-human",
                "outcome_stage": "merge-poll",
                "outcome_status": "blocked",
            }
        )
        return DispatchOutcome(
            work_item_id=item.id,
            status="blocked",
            stage="merge-poll",
            pr_number=pull_request,
            merge_sha=None,
            detail=(
                "base-advanced-after-arming: the automatic resume was refused: " + "; ".join(named)
            ),
        )
    journal.append(
        record=resume_journal_record(
            work_item_id=item.id,
            earlier_run_ids=gather.earlier_run_ids,
            pull_request=pull_request,
            head=anchor.head,
            resumed_at=anchor.resumed_at,
            source=anchor.source,
        )
    )
    return admit_and_dispatch(
        args=resumed_args(args=args, gather=gather, anchor=anchor),
        repo=repo,
        items=items,
        item=item,
        journal=journal,
        launch=DispatchLaunchContext(
            janitor=janitor,
            prelaunch_profile=PrelaunchCpuProfile.for_drive_launch(dispatch_id=run_id()),
        ),
    )
