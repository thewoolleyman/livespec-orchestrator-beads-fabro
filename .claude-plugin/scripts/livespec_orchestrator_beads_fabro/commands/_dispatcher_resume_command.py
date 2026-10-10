"""`resume --item`: finish a published pull request instead of rebuilding it.

`SPECIFICATION/contracts.md` section "Resume from a published pull request
(`resume --item`)" is the clause; Scenarios 142 and 143 exercise it. The pieces
this command drives each live in their own module — `_dispatcher_resume_anchor`
reads what the pull request says, `_dispatcher_resume_observation` measures the
ledger, the forge and the factory, `_dispatcher_resume_refusals` grades those
measurements, `_dispatcher_resume_journal` builds the record that links the two
dispatches, and `_dispatcher_resume_entry` puts the sandbox on the published head
at the resumed-at node. This module is the SEQUENCE, and the sequence is the part
the clause specifies.

WHERE EACH STEP LANDS IS LOAD-BEARING, not stylistic.

The ladder runs "before the admission valve, before any run exists and before
touching any ref", so a refused resume leaves no claim, no run and no journaled
record. Every one of its arms is a measurement the gather took, which is why the
gather runs first and the ladder is pure over its result.

The resume record is journaled "before the run exists" AND after the wall. Before
the run, because it is what links the earlier run's identifiers to this dispatch
and the acceptance pass reads it to attribute a record the earlier run published.
After the wall, because the third-resume refusal COUNTS these records: a dispatch
the wall then refused would consume one of the two resumes the chain allows and
silently lower the bound for the next attempt, with the journal reading as though
a resume had happened.

The reclaim is passed OFF explicitly. The clause: a resume "MUST NOT run the
stale publish-branch reclaim above: the surviving publish branch is the branch the
run resumes on, and no preservation ref is created." The two routes are exclusive
per dispatch — one keeps the dead run's work by finishing it, the other makes a
fresh start possible by clearing it — and running both would preserve the head to
a ref and delete the very branch the resumed run was about to check out.

TWO DEPARTURES FROM `dispatch --item`, each the clause's own wording.

The WIP CAP BINDS. `dispatch --item` is an operator override that passes
`enforce_cap=False`; the resume clause lists "the WIP cap" among the rules the
resume IS subject to. So the valve can hand back a deferral with nothing
launched, and the deferred outcome it built is what gets reported — taking `[0]`
of the launched list alone would raise on exactly that path.

THE WORKFLOW NAME IS SET, NEVER PINNED. The resumed run runs "the workflow the
earlier run's dispatch record names", and separately "a resume MUST NOT write or
clear the item's `dispatch_workflow` metadata, so the next plain dispatch of the
item re-runs the recorded workflow from `start`".
The workflow-pinning helper the plain dispatch uses WRITES that metadata, so
this module must not call it and deliberately does not import or name it. An
absent name leaves the ordinary variant precedence to resolve the item's own
recorded pin, which is the same graph.

WHY AN UNANCHORED RESUME REFUSES EVEN WHEN THE LADDER NAMED NOTHING. The ladder's
anchor arms cover it, so this is a fail-closed narrowing rather than a second
decision — but the direction matters: without an anchor there is no head to check
out and no record to attribute, so proceeding would dispatch a plain run onto the
default branch while the journal recorded a resume.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands._dispatcher_admission import admit_and_select
from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    EXIT_PRECONDITION_ERROR,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_args import (
    add_dispatch_common,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_tail import (
    dispatch_tail_exit,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_ledger import (
    args_with_dispatch_factory_target,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_size_gate import (
    apply_factory_size_dispatch_entry,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop import dispatch_one
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_outcomes import (
    failed_dispatch_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_selection import prepare
from livespec_orchestrator_beads_fabro.commands._dispatcher_otel_wiring import arm_otel_egress
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import journal_path, store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_pre_dispatch_wall import (
    pre_dispatch_wall_exit,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_anchor import ResumeAnchor
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_entry import (
    RESUME_ENTRY_NODE_ARG,
    RESUME_HEAD_ARG,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_journal import (
    resume_journal_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_observation import (
    ResumeGather,
    gather_resume,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_refusals import resume_refusals
from livespec_orchestrator_beads_fabro.commands._dispatcher_rework_admission import ReworkPass
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_checks import dispatch_preamble
from livespec_orchestrator_beads_fabro.io import write_stderr
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "add_resume_arguments",
    "resume_refusal_report",
    "run_resume_command",
]

# The fail-closed narrowing's own refusal, for the shape the ladder's anchor arms
# cover but cannot be proven to: no anchoring record and no pull request number.
# It names a plain dispatch as the remedy, as those arms do.
_UNANCHORED_REFUSAL = (
    "the resume gathered neither an open pull request nor an anchoring Proof of"
    " Done record for this item, so there is nothing to resume from; dispatch it"
    " plainly instead"
)

# A resume NEVER rides the rework leg. The ladder refuses any item that is not
# `ready`, and a `rework:pending` row is `active`, so the leg is unreachable --
# but the valve's DEFAULT is "every marked row" in the tenant, which would let a
# one-item resume re-dispatch unrelated marked work. An empty scope removes them.
_NO_REWORK = ReworkPass(scope_ids=frozenset())


def add_resume_arguments(*, parser: argparse.ArgumentParser) -> None:
    """The resume's flag surface: the dispatching group plus a required `--item`.

    It takes `add_dispatch_common` whole rather than a narrower subset, because
    the namespace it builds is handed to the SAME seams a dispatch's is -- the
    preamble, the wall, the launch and the post-verdict tail all read it, and a
    missing `dest` surfaces as an `AttributeError` inside the dispatch rather
    than as a usage error here. `--item` is required, unlike the probe's: a
    resume with nothing to resume is not a question the handler should have to
    answer.
    """
    add_dispatch_common(parser=parser)
    _ = parser.add_argument("--item", dest="item", required=True)


def resume_refusal_report(*, work_item_id: str, refusals: Sequence[str]) -> str:
    """Every applicable refusal as one operator-facing message, in the clause's order.

    EVERY line, never `refusals[0]`: "a refusal that names only the first does not
    satisfy this clause". An item `active` under a live claim is refused on the
    status bullet AND the live-run bullet, and an operator told only "not ready"
    runs `resolve-blocked` and drives the resume straight into the live run it was
    never told about.
    """
    lines = "".join(f"  - {refusal}\n" for refusal in refusals)
    return f"ERROR: resume refused for {work_item_id}:\n{lines}"


def run_resume_command(*, args: argparse.Namespace) -> int:
    """Measure, grade, journal, and dispatch one resume; or refuse naming every mismatch."""
    repo = Path(args.repo)
    janitor, preamble_exit = dispatch_preamble(args=args, repo=repo)
    if preamble_exit is not None:
        return preamble_exit
    arm_otel_egress(args=args, repo=repo)
    prepared = prepare(args=args, repo=repo)
    if prepared is None:
        return EXIT_PRECONDITION_ERROR
    items, journal = prepared
    target = _resume_target_or_exit(
        args=args,
        repo=repo,
        items=items,
        journal=journal,
    )
    if isinstance(target, int):
        return target
    item = target
    # The ladder grades the item's ledger status itself, so the item is looked up
    # by id across EVERY row rather than through `ready_items`: a non-`ready`
    # item has to reach the ladder to be refused by name, with the remedy its own
    # status calls for.
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
        _ = write_stderr(
            text=resume_refusal_report(
                work_item_id=item.id, refusals=refusals or (_UNANCHORED_REFUSAL,)
            )
        )
        return EXIT_PRECONDITION_ERROR
    # Every refusal that must land after selection and before the claim, as ONE
    # decision -- the SAME wall the dispatch and the drain run, minus the publish
    # branch reclaim, which is the one act a resume must never perform.
    wall_exit = pre_dispatch_wall_exit(
        args=args,
        repo=repo,
        items=[item],
        journal=journal,
        reclaim_publish_branches=False,
    )
    if wall_exit is not None:
        return wall_exit
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
    resumed = _resumed_args(args=args, gather=gather, anchor=anchor)
    outcome = _admit_and_dispatch_resume(
        args=resumed, repo=repo, items=items, item=item, journal=journal, janitor=janitor
    )
    # The SAME post-verdict tail the single dispatch runs, so the resume journals
    # exactly as a dispatch does and its outcome maps to the same exit codes.
    return dispatch_tail_exit(args=resumed, repo=repo, outcome=outcome, journal=journal)


def _resume_target_or_exit(
    *,
    args: argparse.Namespace,
    repo: Path,
    items: list[WorkItem],
    journal: JournalFile,
) -> WorkItem | int:
    """Resolve and size-gate the named row before resume observation or walls."""
    item = next((one for one in items if one.id == args.item), None)
    if item is None:
        _ = write_stderr(
            text=(
                f"ERROR: work-item {args.item} not found in the target-tenant"
                f" ({repo.name}); --repo and --item must reference the same tenant\n"
            )
        )
        return EXIT_PRECONDITION_ERROR
    size_result = apply_factory_size_dispatch_entry(
        cwd=repo,
        path_factory=lambda: store_config(repo=repo),
        items=(item,),
        journal=journal,
    )
    if not is_successful(size_result):
        failure = unsafe_perform_io(size_result.failure())
        outcome = failed_dispatch_outcome(
            journal=journal,
            work_item_id=item.id,
            stage="configuration",
            detail=failure.detail,
        )
        return dispatch_tail_exit(args=args, repo=repo, outcome=outcome, journal=journal)
    size_refusals = unsafe_perform_io(size_result.unwrap())
    if size_refusals:
        return dispatch_tail_exit(
            args=args,
            repo=repo,
            outcome=size_refusals[0],
            journal=journal,
        )
    return item


def _resumed_args(
    *, args: argparse.Namespace, gather: ResumeGather, anchor: ResumeAnchor
) -> argparse.Namespace:
    """An args clone carrying the resumed-at node, the published head, and the workflow.

    The two resume attributes are read DEFENSIVELY downstream -- only this entry
    point ever sets them -- so a clone that failed to set them dispatches as an
    ordinary run, from `start`, with nothing in the output to say so.
    """
    cloned = argparse.Namespace(**vars(args))
    setattr(cloned, RESUME_ENTRY_NODE_ARG, anchor.resumed_at)
    setattr(cloned, RESUME_HEAD_ARG, anchor.head)
    # The earlier run's recorded name WINS over an explicit `--workflow-name`,
    # because the clause makes it the requirement rather than a default: the
    # resumed run "MUST run the workflow the earlier run's dispatch record
    # names". When the journal holds none -- a dispatch written by a build
    # predating the field -- whatever the invocation asked for stands, and an
    # absent name leaves the ordinary variant precedence to resolve the item's
    # own recorded pin, which is the same graph.
    cloned.workflow_name = gather.workflow_name or getattr(args, "workflow_name", None)
    return cloned


def _admit_and_dispatch_resume(
    *,
    args: argparse.Namespace,
    repo: Path,
    items: list[WorkItem],
    item: WorkItem,
    journal: JournalFile,
    janitor: tuple[str, ...] | None,
) -> DispatchOutcome:
    """Admit the one item through the ordinary valve and launch the resumed run.

    `enforce_cap=True` because the clause lists the WIP cap among the rules a
    resume is subject to, which is where it parts company with `dispatch --item`.
    A capacity deferral therefore launches nothing, and the valve's own deferred
    outcome is what the caller reports.

    The FACTORY pin is applied as the plain dispatch applies it -- "resolve its
    factory as `dispatch --item` does" -- while the workflow pin deliberately is
    not: `_resumed_args` has already set the name the earlier run's dispatch
    record carries, and the workflow-pinning helper would write it to the ledger.
    """
    admission = admit_and_select(
        repo=repo,
        items=items,
        candidates=[item],
        journal=journal,
        enforce_cap=True,
        rework=_NO_REWORK,
    )
    dispatched = [
        dispatch_one(
            args=args_with_dispatch_factory_target(args=args, repo=repo, work_item_id=admitted.id),
            repo=repo,
            item=admitted,
            journal=journal,
            janitor=janitor,
        )
        for admitted in admission.admitted
    ]
    return (admission.refused + admission.deferred + dispatched)[0]
