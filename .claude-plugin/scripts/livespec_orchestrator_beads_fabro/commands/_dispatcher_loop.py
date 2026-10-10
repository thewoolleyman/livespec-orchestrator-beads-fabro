"""Per-item dispatch launch: the run-scoped credential projection and the run itself.

The other half of one dispatch -- resolving WHAT it is from the ledger and the
committed workflow, and journaling that record -- lives in
`_dispatcher_loop_record`, which runs entirely before the proof-credential mint.
This module owns everything from the mint onward: the overlay that carries the
run-scoped credentials, the rendered goal, the watched run, and the dispositions
its outcome routes to.
"""

from __future__ import annotations

import argparse
import time
from contextlib import ExitStack
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_self_update as selfup,
)
from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_credentials import (
    materialize_overlay,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_id_journal import (
    DispatchJournalIdentity,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_lock import (
    dispatch_lock_path,
    live_dispatch_lock,
    release_dispatch_lock,
    write_dispatch_lock,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    DispatchOutcome,
    run_dispatch,
    run_fabro_factory_auth_login,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_projection import (
    contract_prompt_variables,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    GithubTokenEnvRunner,
    JournalFile,
    ShellCommandRunner,
    WatchedFabroLauncher,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_lessons import (
    read_ratified_lessons,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_outcomes import (
    failed_dispatch_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_plan import (
    goal_file_path,
    overlay_file_path,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_record import record_dispatch
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_run import (
    DispatchRunContext,
    run_dispatch_with_watchdog,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_selection import (
    post_run_dispositions,
    run_id,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import (
    spans_path,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    minijinja_findings_detail,
    minijinja_openers_in_goal_sources,
    render_goal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_pre_run_claim import (
    release_pre_run_claim_if_needed,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_precondition import (
    journaled_proof_rendering,
    publish_branch_for,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_entry import (
    resume_checkout_for,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_review_gate import (
    ReviewGateEmission,
    emit_review_gate_from_fabro_events,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_secret_vault import (
    fabro_vault_sink_for_plan,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "dispatch_one",
]


@dataclass(frozen=True, kw_only=True)
class _DispatchLifetime:
    """The identity and cleanup stack shared by one locked dispatch."""

    identity: DispatchJournalIdentity
    cleanup: ExitStack


def dispatch_one(
    *,
    args: argparse.Namespace,
    repo: Path,
    item: WorkItem,
    journal: JournalFile,
    janitor: tuple[str, ...] | None,
) -> DispatchOutcome:
    raw_factory_target = getattr(args, "fabro_factory_target", None)
    dispatch_factory = (
        raw_factory_target.name if isinstance(raw_factory_target, FactoryTarget) else None
    )
    if not isinstance(raw_factory_target, FactoryTarget):
        args.fabro_factory_target = FactoryTarget(name="default", server=None, dev_token=None)
    lock = live_dispatch_lock(repo=repo, work_item_id=item.id)
    if lock is None or lock.dispatch_id is None:
        dispatch_id = run_id()
        lock_path = write_dispatch_lock(repo=repo, work_item_id=item.id, dispatch_id=dispatch_id)
    else:
        dispatch_id = lock.dispatch_id
        lock_path = dispatch_lock_path(repo=repo, work_item_id=item.id)
    with ExitStack() as stack:
        _ = stack.callback(lambda: release_dispatch_lock(path=lock_path))
        outcome = _dispatch_one_locked(
            args=args,
            repo=repo,
            item=item,
            journal=journal,
            janitor=janitor,
            lifetime=_DispatchLifetime(
                identity=DispatchJournalIdentity(
                    dispatch_id=dispatch_id,
                    dispatch_factory=dispatch_factory,
                ),
                cleanup=stack,
            ),
        )
        release_pre_run_claim_if_needed(repo=repo, item=item, outcome=outcome, journal=journal)
        return outcome


# One return per PRE-RUN REFUSAL STAGE still standing here — the recorded-dispatch
# refusal rail, GitHub App auth, the goal preflight and the run-config overlay —
# plus the dispatched outcome. Each names its own stage in the journal and
# collapsing any two would report the wrong one. The count no longer needs a
# `PLR0911` waiver because the ledger-labels, materialization and ledger-comments
# refusals moved behind `record_dispatch`'s single rail; that is a consequence of
# the split, not a licence to collapse what is left.
def _dispatch_one_locked(
    *,
    args: argparse.Namespace,
    repo: Path,
    item: WorkItem,
    journal: JournalFile,
    janitor: tuple[str, ...] | None,
    lifetime: _DispatchLifetime,
) -> DispatchOutcome:
    identity = lifetime.identity
    recorded = record_dispatch(
        args=args, repo=repo, item=item, journal=journal, janitor=janitor, identity=identity
    )
    if isinstance(recorded, DispatchOutcome):
        return recorded
    plan = recorded.plan
    goal_file = goal_file_path(work_item_id=item.id)
    overlay_file = getattr(plan, "workflow_toml", overlay_file_path(work_item_id=item.id))
    if isinstance(token_supplier := selfup.github_token_supplier(), str):
        return failed_dispatch_outcome(
            journal=journal,
            work_item_id=item.id,
            stage="github-app-auth",
            detail=token_supplier,
        )
    # Lessons are read host-side from `repo` (the dispatcher's operative
    # checkout, where the reflector maintains loop-reflection-gate/lessons.md),
    # exactly like the ledger comments the dispatch record carries; only
    # committed content is read, so an unmerged reflector proposal never
    # influences a brief.
    lessons = read_ratified_lessons(lessons_root=repo)
    findings = minijinja_openers_in_goal_sources(
        item=item, comments=recorded.comments, lessons=lessons
    )
    if findings:
        return failed_dispatch_outcome(
            journal=journal,
            work_item_id=item.id,
            stage="goal-minijinja-preflight",
            detail=minijinja_findings_detail(findings=findings),
        )
    # EVERYTHING BELOW THIS LINE RUNS AFTER THE PROOF-CREDENTIAL MINT, whose
    # revoke is the RUN's own teardown — so a return added between here and the
    # launch leaks a live provider credential nothing will ask back, plus the
    # mode-600 overlay carrying its value. That is why the goal preflight is
    # ABOVE the overlay rather than beside the render it guards: its inputs are
    # the item, its comments and the lessons, none of which the overlay
    # supplies, so it has no reason to run on the leaking side.
    # A native vault is authenticated through the same Fabro login file as the
    # later run. Establish that credential before materialization reaches its
    # first `fabro secret set`; a fresh candidate host otherwise fails while the
    # dev token is still waiting in the launcher's later auth step.
    factory_runner = ShellCommandRunner()
    run_fabro_factory_auth_login(plan=plan, runner=factory_runner)
    secret_sink = fabro_vault_sink_for_plan(plan=plan, runner=factory_runner, journal=journal)
    # Fallback for every pre-launch refusal and exception. On the normal path
    # the watched launcher releases much earlier, at RUNNING, immediately after
    # the candidate worker has snapshotted the vault.
    _ = lifetime.cleanup.callback(lambda: secret_sink.release_launch_guard())
    overlay_error = materialize_overlay(
        committed=recorded.committed_workflow,
        overlay=overlay_file,
        repo=repo,
        work_item_id=item.id,
        dispatch_id=identity.dispatch_id,
        token=token_supplier,
        # The review-fix guard THIS plan renders, so the overlay's credential
        # requirement is derived from the loop bound this dispatch actually runs
        # rather than from the committed default a bare `fabro run` would see.
        review_fix_visit_cap=plan.review_fix_visit_cap,
        graph_override=recorded.payload.graph,
        # The publish branch and head a RESUME puts the sandbox clone on, built
        # from the head the anchoring record names rather than from the branch
        # tip: a tip read at prepare time may have moved since the record was
        # published, which is the state the head-moved refusal exists to catch.
        resume_checkout=resume_checkout_for(
            args=args, branch=publish_branch_for(work_item_id=item.id)
        ),
        # The ONE contract the plan already resolved, projected once more: the
        # committed run config's prepare commands template these values as
        # `{{ inputs.* }}`, and the pinned engine renders that site for the
        # graph but not for `run.prepare`.
        prepare_inputs=contract_prompt_variables(resolved=plan.integration),
        git_author=recorded.git_author,
        # This repository's proof-asset rendering, as the pre-dispatch gate
        # MEASURED and journaled it. Read back from that record rather than
        # re-probed: the overlay is materialized on every dispatch, offline
        # included, so the measurement travels through the journal and the
        # projection stays pure (bd-ib-pa73qh).
        proof_rendering=journaled_proof_rendering(journal_path=journal.path, repository=repo.name),
        # The adapter inputs this dispatch WRAPS, so the route check grades the
        # graph against what is actually guarded rather than against a convention.
        adapter_inputs=(
            frozenset() if plan.acp_nodes is None else frozenset(plan.acp_nodes.inputs.values())
        ),
        # WHICH factory this dispatch launches at, and that factory's own vault.
        # Both read off the plan's already-resolved target rather than from a
        # second configuration read, for the resolve-once reason the integration
        # contract gives: a credential stored in one server's vault while the run
        # launched against another's resolves to nothing.
        factory_name=plan.fabro_factory_name,
        secret_sink=secret_sink,
    )
    if overlay_error is not None:
        return failed_dispatch_outcome(
            journal=journal,
            work_item_id=item.id,
            stage="run-config-overlay",
            detail=overlay_error,
        )
    goal_text = render_goal(
        item=item, repo=repo, branch=plan.branch, comments=recorded.comments, lessons=lessons
    )
    _ = goal_file.write_text(goal_text, encoding="utf-8")
    started_at, outcome = run_dispatch_with_watchdog(
        context=DispatchRunContext(
            args=args,
            repo=repo,
            plan=plan,
            journal=journal,
            overlay_file=overlay_file,
            payload_dir=recorded.payload.payload_dir,
            token_supplier=token_supplier,
            dispatch_id=identity.dispatch_id,
        ),
        run_dispatch_func=run_dispatch,
        fabro_launcher_type=partial(
            WatchedFabroLauncher,
            on_worker_running=secret_sink.release_launch_guard,
        ),
    )
    # REBOUND, not merely called: the post-merge acceptance valve runs inside, and
    # the outcome it returns is the one the dispatch RESULT must report — a park
    # reported as the janitor's own `green at done` is finding F7(b).
    outcome = post_run_dispositions(
        args=args,
        repo=repo,
        item=item,
        outcome=outcome,
        journal=journal,
        wall_clock_seconds=time.monotonic() - started_at,
        dispatch_context_size=len(goal_text),
        token_supplier=token_supplier,
    )
    emit_review_gate_from_fabro_events(
        emission=ReviewGateEmission(
            plan=plan,
            runner=GithubTokenEnvRunner(inner=ShellCommandRunner(), token=token_supplier),
            journal=journal,
            spans_path=spans_path(args=args, repo=repo),
            work_item_id=item.id,
            dispatch_id=identity.dispatch_id,
            run_id=outcome.fabro_run_id,
            dispatch_factory=identity.dispatch_factory,
        )
    )
    return outcome
