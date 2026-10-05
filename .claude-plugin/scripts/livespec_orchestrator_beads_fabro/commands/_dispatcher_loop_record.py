"""Resolve WHAT one dispatch is, record it, and refuse before any credential exists.

Split out of `_dispatcher_loop` by cohesion, the same way
`_dispatcher_loop_materialize` was and for the same reason -- that module stood
exactly at the file-LLOC hard ceiling, so its overlay call site could not take
another projection argument. `_dispatcher_loop` is left with the other concern:
minting the run-scoped credentials, launching the run and disposing of its
outcome.

ONE CONCERN LIVES HERE. Everything that answers "what is this dispatch?" from
sources that need no credential: the item's ledger labels and comments, the
committed workflow and the plan resolved from it, the dispatch-time warnings that
ride that resolution, and the `dispatch-id` journal record that names the whole
thing before a run exists. Each step is a READ of the ledger, the repository's
committed configuration, or the item itself, and each refusal it can produce is a
fault in one of those -- never in a credential and never in the forge.

WHY THAT MAKES IT A SEAM RATHER THAN THE FIRST N LINES OF A FUNCTION. The
proof-credential mint's revoke is the RUN's own teardown, so a refusal returning
between the mint and the launch leaks a live provider credential plus the mode-600
overlay carrying its value. Every refusal whose inputs the overlay does not supply
therefore belongs above `materialize_overlay`, and splitting the
credential-independent ones out here keeps that ordering rule enforceable by
STRUCTURE: a refusal added to THIS module cannot land on the leaking side of the
line, because the whole module runs before the mint. The refusals the caller
keeps -- the App-token mint and the goal preflight -- stay there because one IS a
credential step and the other guards the goal render the launch owns.

ONE RETURN PER REFUSAL STAGE, and each names its own journal stage -- ledger
labels, dispatch materialization, ledger comments. Collapsing any two would report
the wrong one, which is the same rule the launch half applies to its own returns.
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_completion import (
    warn_item_sizing,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_conformance_premises import (
    emit_conformance_premise_notices,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credentials import (
    read_dispatch_comments,
    read_dispatch_labels,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_id_journal import (
    DispatchJournalIdentity,
    append_dispatch_id_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_git_author import GitAuthor
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_materialize import (
    MaterializationRefusal,
    materialize_dispatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_outcomes import (
    failed_dispatch_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_plan import (
    dispatch_plan_for_item,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_payload import WorkflowPayload
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan_build import DispatchPlan
from livespec_orchestrator_beads_fabro.store import WorkItemComment
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "RecordedDispatch",
    "record_dispatch",
]


@dataclass(frozen=True, kw_only=True)
class RecordedDispatch:
    """What the launch half needs, once this dispatch is resolved and journaled.

    Deliberately NARROWER than the values this module reads: the workflow variant
    name and the resolved ACP adapters are consumed HERE, by the journal record,
    and a launch that could reach them would be a launch that could re-derive the
    resolution they came from.
    """

    plan: DispatchPlan
    committed_workflow: Path
    payload: WorkflowPayload
    git_author: GitAuthor
    comments: tuple[WorkItemComment, ...]


def record_dispatch(
    *,
    args: argparse.Namespace,
    repo: Path,
    item: WorkItem,
    journal: JournalFile,
    janitor: tuple[str, ...] | None,
    identity: DispatchJournalIdentity,
) -> RecordedDispatch | DispatchOutcome:
    """Resolve and journal this dispatch, or return the refusal outcome.

    A `DispatchOutcome` is the refusal rail: every one of them is already the
    failed outcome the caller would otherwise have built, carrying the journal
    stage that produced it, so the launch half routes it by TYPE rather than by
    re-reading which step failed.
    """
    raw_labels = read_dispatch_labels(repo=repo, item=item)
    if isinstance(raw_labels, str):
        return failed_dispatch_outcome(
            journal=journal, work_item_id=item.id, stage="ledger-labels", detail=raw_labels
        )
    materialized = materialize_dispatch(args=args, repo=repo, work_item_id=item.id, journal=journal)
    if isinstance(materialized, MaterializationRefusal):
        return failed_dispatch_outcome(
            journal=journal,
            work_item_id=item.id,
            stage=materialized.stage,
            detail=materialized.detail,
        )
    committed_workflow = materialized.committed_workflow
    payload = materialized.payload
    plan = dispatch_plan_for_item(
        args=args,
        repo=repo,
        item=item,
        janitor=janitor,
        raw_labels=raw_labels,
        timeouts=payload.timeouts,
        # The default-branch probe rides a plain shell runner: it reads the
        # target's own git/forge state and predates the per-dispatch GitHub App
        # token, whose remint decorator exists for the engine's long merge poll.
        runner=ShellCommandRunner(),
        committed_workflow=committed_workflow,
        acp_nodes=materialized.acp_nodes,
    )
    warn_item_sizing(item=item, journal=journal)
    # Surfaced from the ONE contract the plan just resolved, on the same stderr
    # channel as the other dispatch-time warnings, and never blocking: an
    # undeclared conformance premise is a legitimate no-op that would otherwise
    # be indistinguishable from a chosen one.
    emit_conformance_premise_notices(resolved=plan.integration, journal=journal)
    comments = read_dispatch_comments(repo=repo, item=item)
    if isinstance(comments, str):
        return failed_dispatch_outcome(
            journal=journal, work_item_id=item.id, stage="ledger-comments", detail=comments
        )
    append_dispatch_id_record(
        journal=journal,
        work_item_id=item.id,
        identity=identity,
        started_at_epoch=time.time(),
        workflow_toml=committed_workflow,
        workflow_name=materialized.workflow_name,
        integration=plan.integration,
        merge_hold=plan.merge_hold,
    )
    return RecordedDispatch(
        plan=plan,
        committed_workflow=committed_workflow,
        payload=payload,
        git_author=materialized.git_author,
        comments=comments,
    )
