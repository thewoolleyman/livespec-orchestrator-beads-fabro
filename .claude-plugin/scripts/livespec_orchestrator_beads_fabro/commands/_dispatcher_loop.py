"""Dispatch-loop candidate selection and per-item launch primitives."""

from __future__ import annotations

import argparse
import time
from contextlib import ExitStack
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_manager import (
    CredentialManagerClient,
    CredentialReceipt,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_manager_io import (
    LlmProviderManagerClient,
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_lock import (
    release_dispatch_lock,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    DispatchOutcome,
    run_dispatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_projection import (
    contract_prompt_variables,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
    WatchedFabroLauncher,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_lessons import (
    read_ratified_lessons,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_lease import (
    resolve_dispatch_lease,
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_reports import (
    emit_post_run_reports,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_run import (
    DispatchRunContext,
    run_dispatch_with_watchdog,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_selection import (
    post_run_dispositions,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    minijinja_findings_detail,
    minijinja_openers_in_goal_sources,
    render_goal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_pre_run_claim import (
    release_pre_run_claim_if_needed,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "dispatch_one",
]


def dispatch_one(
    *,
    args: argparse.Namespace,
    repo: Path,
    item: WorkItem,
    journal: JournalFile,
    janitor: tuple[str, ...] | None,
) -> DispatchOutcome:
    lease = resolve_dispatch_lease(args=args, repo=repo, work_item_id=item.id)
    with ExitStack() as stack:
        _ = stack.callback(lambda: release_dispatch_lock(path=lease.lock_path))
        outcome = _dispatch_one_locked(
            args=args,
            repo=repo,
            item=item,
            journal=journal,
            janitor=janitor,
            identity=lease.identity,
        )
        release_pre_run_claim_if_needed(repo=repo, item=item, outcome=outcome, journal=journal)
        return outcome


def _dispatch_one_locked(  # noqa: PLR0911, PLR0913 — one return per PRE-RUN REFUSAL STAGE (ledger labels, dispatch materialization, ledger comments, GitHub App auth, run-config overlay, goal preflight) plus the dispatched outcome; each names its own stage in the journal and collapsing any two would report the wrong one. `credential_manager` is the injected llm-provider-manager seam, kw-only and defaulted, so a hermetic test drives this path without an installed manager executable.
    *,
    args: argparse.Namespace,
    repo: Path,
    item: WorkItem,
    journal: JournalFile,
    janitor: tuple[str, ...] | None,
    identity: DispatchJournalIdentity,
    credential_manager: CredentialManagerClient | None = None,
) -> DispatchOutcome:
    goal_file = goal_file_path(work_item_id=item.id)
    overlay_file = overlay_file_path(work_item_id=item.id)
    # The credential authority for this dispatch, resolved ONCE so the provisioning
    # request and any later failure report reach the SAME manager. `receipts` collects
    # the one secret-free receipt the overlay materializer obtains; it stays empty when
    # the dispatch refuses before provisioning, which is what tells the post-run report
    # there is no record identity to report against.
    manager = credential_manager or LlmProviderManagerClient(temp_dir=overlay_file.parent)
    receipts: list[CredentialReceipt] = []
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
        credential_manager=manager,
        receipt_sink=receipts.append,
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
    started_at, outcome = run_dispatch_with_watchdog(
        context=DispatchRunContext(
            args=args,
            repo=repo,
            plan=plan,
            journal=journal,
            overlay_file=overlay_file,
            payload_dir=payload.payload_dir,
            token_supplier=token_supplier,
            dispatch_id=identity.dispatch_id,
        ),
        run_dispatch_func=run_dispatch,
        fabro_launcher_type=WatchedFabroLauncher,
    )
    post_run_dispositions(
        args=args,
        repo=repo,
        item=item,
        outcome=outcome,
        journal=journal,
        wall_clock_seconds=time.monotonic() - started_at,
        dispatch_context_size=len(goal_text),
        token_supplier=token_supplier,
    )
    emit_post_run_reports(
        args=args,
        repo=repo,
        plan=plan,
        journal=journal,
        outcome=outcome,
        identity=identity,
        work_item_id=item.id,
        token_supplier=token_supplier,
        credential_manager=manager,
        receipts=receipts,
        now_epoch=time.time(),
    )
    return outcome
