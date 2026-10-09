"""Everything one resume measures, gathered once before the ladder grades it.

`_dispatcher_resume_refusals` is deliberately PURE: three external systems answer
a resume's questions — the ledger, the forge and the factory — and gathering them
is a different concern from grading them. This is the gathering half, so this is
where the IO-shaped failures are decided: a "could not ask" must never arrive at
the ladder looking like an answer, because for every one of these measurements the
two support opposite decisions.

THE ORDER OF THE THREE READS IS FORCED, not chosen. The forge's listing gives the
pull request NUMBER, without which no comment can be read; the comments give the
anchoring record, without which no run id is known; and the run id is what the
factory is asked about. So the gather is a chain, and each link short-circuits into
an observation the ladder can refuse on rather than into an exception.

WHY `resume_anchor` IS CALLED TWICE. It takes the executing node as an argument and
picks the latest factory record itself, but the executing node can only be asked
about a run the anchoring record NAMES — so the first call (with no executing node)
identifies the record and its run id, the factory is then asked, and the second
call builds the answer. Both calls are pure and deterministic over the same
records, so the second cannot disagree with the first about WHICH record anchors;
only about the stage, which is the point.

WHY THE DEFINITION-OF-DONE DIFFERENCE IS MEASURED AGAINST THE RECORD RATHER THAN
THE JOURNAL. The clause refuses when the item's current section "differs from the
earlier run's dispatch-time snapshot", and gives its reason outright: "so the
inherited records prove exactly the assertions the resumed dispatch is graded on".
The journal carries no snapshot of that section; the anchoring RECORD does, because
a factory proof record publishes every assertion it was dispatched with. So an
assertion the record does not carry is one the inherited proof cannot cover —
which is the thing the refusal exists to prevent — and measuring it this way also
catches the case a journal snapshot could not: an earlier run dispatched from
another checkout, whose journal is invisible here.

WHY THE MATCH IS WHITESPACE-NORMALIZED. A record is prose, and the publisher may
hard-wrap a long assertion across several physical lines — most likely for exactly
the assertions most worth checking. `_dispatcher_proof_record` normalizes for the
same reason before its own per-assertion search.
"""

from __future__ import annotations

import argparse
import re
import time
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_lock import (
    live_dispatch_lock,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_effective_criteria import (
    effective_criteria,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_evidence import (
    read_pull_request_records,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_precondition import (
    publish_branch_for,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import ProofRecord
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_attribution import (
    NON_TERMINAL_STATUS_KINDS,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection_journal import (
    read_journal_records,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_anchor import (
    ResumeAnchor,
    resume_anchor,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_forge import (
    branch_pull_request,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_journal import (
    resumes_anchored_on,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_refusals import (
    LiveRun,
    ResumeObservation,
    live_runs_from_pairs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_run_record import (
    executing_node_from_payload,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_tdd_probe import dispatch_ids_for
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroTarget
from livespec_orchestrator_beads_fabro.commands._run_attribution import journaled_run_ids
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "FactoryReading",
    "ResumeGather",
    "earlier_workflow_name",
    "gather_resume",
    "unproved_assertions",
]

_PS_TIMEOUT_SECONDS = 60.0
_INSPECT_TIMEOUT_SECONDS = 60.0
_DISPATCH_ID_STAGE = "dispatch-id"
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True, kw_only=True)
class FactoryReading:
    """What one factory answered about the earlier run of one item.

    `observed` false means the factory could not be asked. It is deliberately not
    the same value as an answering factory holding nothing alive, which carries
    the same empty `live_runs`: one authorizes a resume, the other refuses it.

    `executing_node` is `None` both when the factory no longer holds the run and
    when it holds it but names no stage, because the clause gives those one
    treatment — the verdict of the latest record decides instead.
    """

    observed: bool
    live_runs: tuple[LiveRun, ...]
    executing_node: str | None


@dataclass(frozen=True, kw_only=True)
class ResumeGather:
    """One resume's whole measurement: what to refuse on, and what to resume onto.

    `observation` is the ladder's input. `anchor` is what a non-refused resume
    acts on — the head to check out, the stage to enter at, the record to
    attribute — and it is `None` exactly when some arm of the ladder refuses, so
    a caller narrows on it rather than re-deriving whether a resume is possible.
    """

    observation: ResumeObservation
    anchor: ResumeAnchor | None
    branch: str
    earlier_run_ids: tuple[str, ...]
    workflow_name: str | None


def gather_resume(
    *,
    args: argparse.Namespace,
    repo: Path,
    item: WorkItem,
    journal_path: Path,
    runner: CommandRunner,
) -> ResumeGather:
    """Measure the ledger, the forge and the factory for one candidate resume."""
    branch = publish_branch_for(work_item_id=item.id)
    forge = branch_pull_request(repo=repo, branch=branch, runner=runner)
    pull_request = forge.pull_request
    records = (
        read_pull_request_records(repo=repo, pr_number=pull_request.number, runner=runner)
        if pull_request is not None
        else None
    )
    provisional = resume_anchor(records=records or (), executing_node=None)
    factory = _factory_reading(
        args=args,
        repo=repo,
        item=item,
        journal_path=journal_path,
        earlier_run_id=None if provisional is None else provisional.record.run_id,
        runner=runner,
    )
    anchor = resume_anchor(records=records or (), executing_node=factory.executing_node)
    journaled = read_journal_records(journal_path=journal_path)
    return ResumeGather(
        observation=ResumeObservation(
            work_item_id=item.id,
            status=item.status,
            blocked_reason=item.blocked_reason,
            anchor_head=None if anchor is None else anchor.head,
            forge_observed=forge.observed,
            pull_request=None if pull_request is None else pull_request.number,
            pull_request_state=None if pull_request is None else pull_request.state,
            pull_request_head=None if pull_request is None else pull_request.head,
            live_runs=factory.live_runs,
            liveness_observed=factory.observed,
            lock_age_seconds=_lock_age_seconds(repo=repo, work_item_id=item.id),
            changed_assertions=(
                () if anchor is None else unproved_assertions(item=item, record=anchor.record)
            ),
            earlier_resumes=(
                ()
                if pull_request is None
                else resumes_anchored_on(
                    records=journaled,
                    work_item_id=item.id,
                    pull_request=pull_request.number,
                )
            ),
        ),
        anchor=anchor,
        branch=branch,
        earlier_run_ids=_earlier_run_ids(records=journaled, item=item, anchor=anchor),
        workflow_name=earlier_workflow_name(records=journaled, work_item_id=item.id),
    )


def unproved_assertions(*, item: WorkItem, record: ProofRecord) -> tuple[str, ...]:
    """The item's current assertions the anchoring record does not carry.

    The LIST rather than a boolean, because the refusal has to name the
    difference: an operator reading which assertion arrived after the earlier run
    can decide whether a plain dispatch is what they want.
    """
    body = _normalized(text=record.body)
    return tuple(
        one for one in effective_criteria(item=item).assertions if _normalized(text=one) not in body
    )


def earlier_workflow_name(
    *, records: tuple[dict[str, object], ...], work_item_id: str
) -> str | None:
    """The workflow the item's newest `dispatch-id` record names, or `None`.

    `None` leaves the resumed dispatch on the ordinary variant precedence, which
    resolves the item's own recorded pin first — the same graph. That is the right
    degradation for a journal written by a build predating the field: refusing
    would strand an item whose workflow is recoverable from the ledger anyway.
    """
    found: str | None = None
    for record in records:
        if record.get("stage") != _DISPATCH_ID_STAGE or record.get("work_item_id") != work_item_id:
            continue
        candidate = record.get("workflow_name")
        if isinstance(candidate, str) and candidate:
            found = candidate
    return found


def _earlier_run_ids(
    *, records: tuple[dict[str, object], ...], item: WorkItem, anchor: ResumeAnchor | None
) -> tuple[str, ...]:
    """Every identifier the earlier run answers to, the record's own leading.

    LEADING matters: `resumes_anchored_on` names each resume by the FIRST
    identifier, so an operator reading the third-resume refusal sees the run ids
    they can look up on the factory rather than an opaque dispatch hash.

    The record's run id is the load-bearing one, because it is the only identifier
    read off the FORGE: the earlier run may have been dispatched from a checkout
    whose journal is invisible here. The journal's own run and dispatch ids ride
    along because the attribution clause accepts "either identifier the Dispatcher
    can attribute", and a record published by a different stage of the same run may
    carry the dispatch id instead.
    """
    named = [] if anchor is None else [anchor.record.run_id]
    named.extend(journaled_run_ids(records=records, work_item_id=item.id))
    named.extend(dispatch_ids_for(records=records, work_item_id=item.id))
    return tuple(dict.fromkeys(named))


def _factory_reading(
    *,
    args: argparse.Namespace,
    repo: Path,
    item: WorkItem,
    journal_path: Path,
    earlier_run_id: str | None,
    runner: CommandRunner,
) -> FactoryReading:
    """Ask the resolved factory which runs of this item live, and where the earlier one was.

    The factory target is read off `args` the way every other post-selection seam
    reads it — `dispatch_preamble` pins it before this is reached — and an absent
    one degrades to the client's own default rather than raising.
    """
    port = FabroPort(
        fabro_bin=args.fabro_bin,
        target=_factory_target(args=args),
        runner=runner,
        cwd=repo,
    )
    ps = port.ps(timeout_seconds=_PS_TIMEOUT_SECONDS)
    if ps.command.exit_code != 0:
        return FactoryReading(observed=False, live_runs=(), executing_node=None)
    journaled = frozenset(
        journaled_run_ids(
            records=read_journal_records(journal_path=journal_path), work_item_id=item.id
        )
    )
    attributed = [run for run in ps.runs if run.run_id in journaled or run.work_item_id == item.id]
    live = live_runs_from_pairs(
        pairs=[
            (run.run_id, run.status_kind or "unknown")
            for run in attributed
            if run.status_kind in NON_TERMINAL_STATUS_KINDS
        ]
    )
    held = earlier_run_id is not None and any(run.run_id == earlier_run_id for run in ps.runs)
    if not held:
        # An authoritative not-found observes the run as not live and sends the
        # stage question to the verdict fallback. Asking `inspect` anyway would
        # spend a round trip to learn what `ps` already answered, and a failing
        # `inspect` there would read as an outage rather than as the answer it is.
        return FactoryReading(observed=True, live_runs=live, executing_node=None)
    inspected = port.inspect(
        run_id=earlier_run_id if earlier_run_id is not None else "",
        timeout_seconds=_INSPECT_TIMEOUT_SECONDS,
    )
    return FactoryReading(
        observed=True,
        live_runs=live,
        executing_node=executing_node_from_payload(payload=inspected.payload),
    )


def _factory_target(*, args: argparse.Namespace) -> FabroTarget:
    """The resolved factory, or the client's own default when none was pinned."""
    target = getattr(args, "fabro_factory_target", None)
    return FabroTarget(
        server_url=getattr(target, "server", None),
        dev_token=getattr(target, "dev_token", None),
    )


def _lock_age_seconds(*, repo: Path, work_item_id: str) -> float | None:
    """How long this item's live ownership lock has been held, or `None` for none.

    `None` rather than zero for an item with no lock: zero reads as a lock taken
    this instant, and the refusal arm keys on the value being present at all, so
    a zero would refuse every clean resume.
    """
    lock = live_dispatch_lock(repo=repo, work_item_id=work_item_id)
    if lock is None:
        return None
    return max(0.0, time.time() - lock.started_at_epoch)


def _normalized(*, text: str) -> str:
    """One string with its whitespace collapsed and its case folded."""
    return _WHITESPACE.sub(" ", text).strip().casefold()
