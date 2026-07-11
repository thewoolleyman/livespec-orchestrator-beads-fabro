"""Post-merge janitor flow for the Dispatcher engine."""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_merge import journal_stage
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    CORE_PLUGIN_ROOT_ENV_VAR,
    DispatchPlan,
    PrView,
    janitor_bootstrap_argv,
    janitor_core_clone_argv,
    janitor_trust_argv,
    janitor_worktree_add_argv,
    janitor_worktree_remove_argv,
    pull_primary_argv,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
        CommandResult,
        CommandRunner,
        DispatchOutcome,
        JournalWriter,
    )

__all__: list[str] = ["post_merge"]

_GIT_TIMEOUT_SECONDS = 600.0
_JANITOR_TIMEOUT_SECONDS = 3600.0


def post_merge(
    *,
    outcome_type: type[DispatchOutcome],
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    merged: PrView,
) -> DispatchOutcome:
    """Refresh the primary, then gate on the janitor in a fresh checkout.

    The janitor runs in a freshly provisioned detached worktree of the
    merged ref — NEVER the host primary's working tree, whose
    environment rot once false-redded a confirmed-green merge
    (livespec-impl-beads-cgd). Provisioning failures degrade (green
    outcome at `janitor-env-degraded` with actionable detail) instead
    of failing; a red janitor inside the fresh checkout is the real
    signal and stays a failure, with the checkout kept for diagnosis.
    """
    pull = runner.run(
        argv=pull_primary_argv(plan=plan),
        cwd=plan.repo,
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
    )
    journal_stage(journal=journal, plan=plan, stage="pull-primary", result=pull)
    if pull.exit_code != 0:
        return outcome_type(
            work_item_id=plan.work_item_id,
            status="failed",
            stage="pull-primary",
            pr_number=merged.number,
            merge_sha=merged.merge_sha,
            detail=_tail(text=pull.stderr),
        )
    degraded = _provision_janitor_checkout(
        outcome_type=outcome_type,
        plan=plan,
        runner=runner,
        journal=journal,
        merged=merged,
    )
    if degraded is not None:
        return degraded
    janitor = runner.run(
        argv=list(plan.janitor),
        cwd=plan.janitor_checkout,
        timeout_seconds=_JANITOR_TIMEOUT_SECONDS,
        env={CORE_PLUGIN_ROOT_ENV_VAR: str(plan.janitor_core_checkout / ".claude-plugin")},
    )
    journal_stage(journal=journal, plan=plan, stage="janitor-post-merge", result=janitor)
    if janitor.exit_code != 0:
        return outcome_type(
            work_item_id=plan.work_item_id,
            status="failed",
            stage="janitor-post-merge",
            pr_number=merged.number,
            merge_sha=merged.merge_sha,
            detail=(
                f"post-merge janitor red in fresh checkout {plan.janitor_checkout} "
                f"(kept for diagnosis): {_tail(text=janitor.stderr)}"
            ),
        )
    cleanup = runner.run(
        argv=janitor_worktree_remove_argv(plan=plan),
        cwd=plan.repo,
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
    )
    journal_stage(journal=journal, plan=plan, stage="janitor-checkout-remove", result=cleanup)
    return outcome_type(
        work_item_id=plan.work_item_id,
        status="green",
        stage="done",
        pr_number=merged.number,
        merge_sha=merged.merge_sha,
        detail="merged, post-merge janitor green",
    )


def _provision_janitor_checkout(
    *,
    outcome_type: type[DispatchOutcome],
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    merged: PrView,
) -> DispatchOutcome | None:
    """Provision the fresh detached worktree the post-merge janitor runs in.

    Returns None when the checkout is ready, or the janitor-env-degraded
    outcome when a provisioning step fails (environment-shaped; the
    merge is already confirmed, so gate accounting must not record a
    work-item failure). Steps: a pre-clean `git worktree remove --force`
    whose result is deliberately ignored (it clears a stale registration
    left by a crashed earlier dispatch; on a clean host it just fails),
    the detached `git worktree add` at the merged ref (the merge sha
    when the PR view carried one, `origin/master` otherwise — the
    just-pulled primary has both), and `mise trust` inside the checkout
    (trust is per-path, so the fresh path is never pre-trusted and the
    default janitor's `mise exec` would refuse to run there).
    """
    preclean = runner.run(
        argv=janitor_worktree_remove_argv(plan=plan),
        cwd=plan.repo,
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
    )
    journal_stage(journal=journal, plan=plan, stage="janitor-checkout-preclean", result=preclean)
    ref = merged.merge_sha if merged.merge_sha is not None else "origin/master"
    add = runner.run(
        argv=janitor_worktree_add_argv(plan=plan, ref=ref),
        cwd=plan.repo,
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
    )
    journal_stage(journal=journal, plan=plan, stage="janitor-checkout-add", result=add)
    if add.exit_code != 0:
        return _merged_degraded(
            outcome_type=outcome_type,
            plan=plan,
            merged=merged,
            step=(
                f"provisioning the fresh janitor checkout at "
                f"{plan.janitor_checkout} (ref {ref})"
            ),
            result=add,
        )
    trust = runner.run(
        argv=janitor_trust_argv(),
        cwd=plan.janitor_checkout,
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
    )
    journal_stage(journal=journal, plan=plan, stage="janitor-checkout-trust", result=trust)
    if trust.exit_code != 0:
        return _merged_degraded(
            outcome_type=outcome_type,
            plan=plan,
            merged=merged,
            step=f"`mise trust` inside the janitor checkout {plan.janitor_checkout}",
            result=trust,
        )
    bootstrap = runner.run(
        argv=janitor_bootstrap_argv(),
        cwd=plan.repo,
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
    )
    journal_stage(journal=journal, plan=plan, stage="janitor-checkout-bootstrap", result=bootstrap)
    if bootstrap.exit_code != 0:
        return _merged_degraded(
            outcome_type=outcome_type,
            plan=plan,
            merged=merged,
            step=(
                f"installing canonical hooks via `just install-commit-refuse-hooks` in "
                f"{plan.repo}"
            ),
            result=bootstrap,
        )
    core = runner.run(
        argv=janitor_core_clone_argv(plan=plan),
        cwd=plan.janitor_checkout,
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
    )
    journal_stage(journal=journal, plan=plan, stage="janitor-core-provision", result=core)
    if core.exit_code != 0:
        return _merged_degraded(
            outcome_type=outcome_type,
            plan=plan,
            merged=merged,
            step=(
                f"provisioning livespec core at {plan.janitor_core_checkout} "
                f"(ref {plan.janitor_core_ref})"
            ),
            result=core,
        )
    return None


def _merged_degraded(
    *,
    outcome_type: type[DispatchOutcome],
    plan: DispatchPlan,
    merged: PrView,
    step: str,
    result: CommandResult,
) -> DispatchOutcome:
    """Janitor-env-degraded: merged green, but the gate could not run.

    NOT a work-item failure (livespec-impl-beads-cgd): the merge is
    confirmed on the remote and the work-item's own sandbox checks and
    CI were green, so a host-side provisioning failure must not reset
    the gate streak. The outcome stays `green` for accounting, with the
    degradation loud in the stage and an actionable remediation detail.
    """
    return outcome_type(
        work_item_id=plan.work_item_id,
        status="green",
        stage="janitor-env-degraded",
        pr_number=merged.number,
        merge_sha=merged.merge_sha,
        detail=(
            f"merged, but the post-merge janitor DID NOT RUN: {step} failed "
            f"({_tail(text=result.stderr, limit=500)}). This is a host-environment "
            f"problem, not a work-item failure — the merge is confirmed on the "
            f"remote. Remediate the host, then run `{' '.join(plan.janitor)}` in "
            f"a clean checkout of merged master to close the gate by hand."
        ),
    )


def _tail(*, text: str, limit: int = 2000) -> str:
    stripped = text.strip()
    if len(stripped) <= limit:
        return stripped
    return stripped[-limit:]
