"""Assemble WHAT one dispatch launches with, and route every pre-run refusal.

Split out of `_dispatcher_loop` by cohesion, continuing the seam
`_dispatcher_loop_materialize` opened. That module answers which workflow a
dispatch runs; this one assembles everything the LAUNCH needs around it -- the
plan, the ledger text the brief is rendered from, the minted GitHub App token,
the run-config overlay and the written goal file -- and routes each refusal that
can still happen before any Fabro run exists. `_dispatcher_loop` is left with the
two concerns that remain: holding the dispatch lock, and running the launch and
disposing of its outcome.

EVERY STEP HERE REFUSES BEFORE A RUN EXISTS, which is why they belong together.
Unreadable ledger labels, an unmaterializable workflow, unreadable ledger
comments, a GitHub App token that will not mint, an unusable run config and a
goal carrying a MiniJinja opener are the same KIND of fault: each is discovered
by the dispatch that would otherwise have gone out carrying something nobody
chose, and each keeps its own journal stage so the record still says which step
failed.

THE ORDER IS LOAD-BEARING IN TWO PLACES. The `dispatch-id` record is appended
BEFORE the token mints, so a dispatch that dies at authentication still leaves
the identity row a reconciler keys on. And the goal is rendered LAST, after the
overlay, because the overlay is where the dispatch's own credential projection
lands and a goal written beside a failed overlay would be a brief for a run that
cannot start.
"""

from __future__ import annotations

import argparse
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_self_update as selfup,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_completion import (
    warn_item_sizing,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_conformance_premises import (
    emit_conformance_premise_notices,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credentials import (
    materialize_overlay,
    read_dispatch_comments,
    read_dispatch_labels,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_id_journal import (
    DispatchJournalIdentity,
    append_dispatch_id_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_projection import (
    contract_prompt_variables,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_lessons import (
    read_ratified_lessons,
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
    goal_file_path,
    overlay_file_path,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
    minijinja_findings_detail,
    minijinja_openers_in_goal_sources,
    render_goal,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "PreparedLaunch",
    "prepare_launch",
]


@dataclass(frozen=True, kw_only=True)
class PreparedLaunch:
    """Everything one dispatch needs to launch, once nothing can refuse it.

    `goal_text` rides along beside the file it was written to because the
    post-run disposition reports the brief's SIZE, and re-reading the file to
    recover a length the renderer already knew would be a second source for one
    fact.
    """

    plan: DispatchPlan
    token_supplier: Callable[[], str]
    goal_text: str
    overlay_file: Path
    payload_dir: Path


def prepare_launch(  # noqa: PLR0911 — one return per PRE-RUN REFUSAL STAGE (ledger labels, dispatch materialization, ledger comments, GitHub App auth, run-config overlay, goal preflight) plus the prepared launch; each names its own stage in the journal and collapsing any two would report the wrong one.
    *,
    args: argparse.Namespace,
    repo: Path,
    item: WorkItem,
    journal: JournalFile,
    janitor: tuple[str, ...] | None,
    identity: DispatchJournalIdentity,
) -> PreparedLaunch | DispatchOutcome:
    """Assemble the launch, or return the terminal outcome of the step that refused."""
    goal_file = goal_file_path(work_item_id=item.id)
    overlay_file = overlay_file_path(work_item_id=item.id)
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
    if isinstance(token_supplier := selfup.github_token_supplier(), str):
        return failed_dispatch_outcome(
            journal=journal,
            work_item_id=item.id,
            stage="github-app-auth",
            detail=token_supplier,
        )
    overlay_error = materialize_overlay(
        committed=committed_workflow,
        overlay=overlay_file,
        repo=repo,
        work_item_id=item.id,
        dispatch_id=identity.dispatch_id,
        token=token_supplier,
        graph_override=payload.graph,
        # The ONE contract the plan already resolved, projected once more: the
        # committed run config's prepare commands template these values as
        # `{{ inputs.* }}`, and the pinned engine renders that site for the
        # graph but not for `run.prepare`.
        prepare_inputs=contract_prompt_variables(resolved=plan.integration),
        git_author=materialized.git_author,
        # This dispatch's own journal, so the proof-store projection can read back
        # the image rendering the pre-dispatch gate MEASURED for this repository
        # rather than re-probing the forge from a path that must render offline.
        # Threading it is what this module's extraction bought: the call site that
        # could take the argument sat at the file-size ceiling before the split.
        journal_path=journal.path,
    )
    if overlay_error is not None:
        return failed_dispatch_outcome(
            journal=journal,
            work_item_id=item.id,
            stage="run-config-overlay",
            detail=overlay_error,
        )
    # Lessons are read host-side from `repo` (the dispatcher's operative
    # checkout, where the reflector maintains loop-reflection-gate/lessons.md),
    # exactly like `comments` above; only committed content is read, so an
    # unmerged reflector proposal never influences a brief.
    lessons = read_ratified_lessons(lessons_root=repo)
    findings = minijinja_openers_in_goal_sources(item=item, comments=comments, lessons=lessons)
    if findings:
        return failed_dispatch_outcome(
            journal=journal,
            work_item_id=item.id,
            stage="goal-minijinja-preflight",
            detail=minijinja_findings_detail(findings=findings),
        )
    goal_text = render_goal(
        item=item, repo=repo, branch=plan.branch, comments=comments, lessons=lessons
    )
    _ = goal_file.write_text(goal_text, encoding="utf-8")
    return PreparedLaunch(
        plan=plan,
        token_supplier=token_supplier,
        goal_text=goal_text,
        overlay_file=overlay_file,
        payload_dir=payload.payload_dir,
    )
