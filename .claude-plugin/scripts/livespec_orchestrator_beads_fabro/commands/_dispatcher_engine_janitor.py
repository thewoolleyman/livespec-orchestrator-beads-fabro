"""Post-merge janitor flow for the Dispatcher engine."""

from __future__ import annotations

from contextlib import ExitStack
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_journal import (
    StageJournalOptions,
    run_stage,
    tail,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_hook_install_recipe import (
    JanitorBootstrapRecipe,
    resolve_janitor_bootstrap_recipe,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_janitor_check_venue import (
    CLUSTER_GATE_ARGV,
    cluster_janitor_red,
    host_janitor_red,
    janitor_runs_on_the_cluster,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_janitor_degraded import (
    DegradedStep,
    degraded_step,
    merged_degraded_for_plan,
    merged_degraded_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_janitor_lock import (
    claim_janitor_lock,
    janitor_lock_path,
    release_janitor_lock,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_janitor_venue import (
    provision_janitor_checkout,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    CORE_PLUGIN_ROOT_ENV_VAR,
    DispatchPlan,
    PrView,
    janitor_worktree_remove_argv,
    pull_primary_argv,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
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
    # Resolved ONCE for the whole post-merge flow: the recipe the janitor
    # invokes and the recipe a degradation names have to be the same recipe,
    # and a second resolution is how they come to disagree.
    recipe = resolve_janitor_bootstrap_recipe(cwd=plan.repo)
    lock_path = janitor_lock_path(plan=plan)
    lock_detail = claim_janitor_lock(path=lock_path, owner=plan.work_item_id)
    if lock_detail is not None:
        return merged_degraded_outcome(
            outcome_type=outcome_type,
            work_item_id=plan.work_item_id,
            merged=merged,
            step=DegradedStep(description="claiming the janitor checkout lock", reason=lock_detail),
            recipe=recipe,
        )
    with ExitStack() as stack:
        _ = stack.callback(release_janitor_lock, path=lock_path)
        return _post_merge_locked(
            outcome_type=outcome_type,
            plan=plan,
            runner=runner,
            journal=journal,
            merged=merged,
            recipe=recipe,
        )


def _check_suite_red(
    *,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
) -> str | None:
    """Run the janitor's check suite in the DECLARED venue; `None` when it is green.

    The venue is read here rather than carried on the plan because it decides
    only what this one stage runs: no earlier seam needs it, and nothing is
    journaled about the janitor before the flow reaches this point.

    The cluster venue passes NO environment: the core plugin root exists so a
    HOST-LOCAL suite can resolve this plugin inside the fresh checkout, and the
    pod re-derives its own checkout from the pushed tree.
    """
    on_the_cluster = janitor_runs_on_the_cluster(cwd=plan.repo)
    argv = list(CLUSTER_GATE_ARGV) if on_the_cluster else list(plan.janitor)
    env = (
        None
        if on_the_cluster
        else {CORE_PLUGIN_ROOT_ENV_VAR: str(plan.janitor_core_checkout / ".claude-plugin")}
    )
    result = run_stage(
        runner=runner,
        journal=journal,
        plan=plan,
        stage="janitor-post-merge",
        command=(argv, plan.janitor_checkout, _JANITOR_TIMEOUT_SECONDS, env),
        # The check suite is the command whose red the retention clause exists
        # for: its excerpt names the suite, and the failing target it reports
        # is on the stream the excerpt did not keep.
        journal_options=StageJournalOptions(retention=plan.janitor_retention),
    )
    if on_the_cluster:
        return cluster_janitor_red(result=result, checkout=plan.janitor_checkout)
    return host_janitor_red(result=result, checkout=plan.janitor_checkout)


def _post_merge_locked(
    *,
    outcome_type: type[DispatchOutcome],
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    merged: PrView,
    recipe: JanitorBootstrapRecipe,
) -> DispatchOutcome:
    pull = run_stage(
        runner=runner,
        journal=journal,
        plan=plan,
        stage="pull-primary",
        command=(pull_primary_argv(plan=plan), plan.repo, _GIT_TIMEOUT_SECONDS, None),
    )
    if pull.exit_code != 0:
        return merged_degraded_for_plan(
            outcome_type=outcome_type,
            plan=plan,
            merged=merged,
            step=degraded_step(
                description=f"refreshing the primary checkout {plan.repo} via pull-primary",
                result=pull,
            ),
            recipe=recipe,
        )
    degraded = provision_janitor_checkout(
        outcome_type=outcome_type,
        plan=plan,
        runner=runner,
        journal=journal,
        merged=merged,
        recipe=recipe,
    )
    if degraded is not None:
        return degraded
    red = _check_suite_red(plan=plan, runner=runner, journal=journal)
    if red is not None:
        return outcome_type(
            work_item_id=plan.work_item_id,
            status="failed",
            stage="janitor-post-merge",
            pr_number=merged.number,
            merge_sha=merged.merge_sha,
            detail=red,
        )
    cleanup = run_stage(
        runner=runner,
        journal=journal,
        plan=plan,
        stage="janitor-checkout-remove",
        command=(janitor_worktree_remove_argv(plan=plan), plan.repo, _GIT_TIMEOUT_SECONDS, None),
    )
    if cleanup.exit_code != 0:
        return outcome_type(
            work_item_id=plan.work_item_id,
            status="failed",
            stage="janitor-checkout-remove",
            pr_number=merged.number,
            merge_sha=merged.merge_sha,
            detail=tail(text=cleanup.stderr),
        )
    return outcome_type(
        work_item_id=plan.work_item_id,
        status="green",
        stage="done",
        pr_number=merged.number,
        merge_sha=merged.merge_sha,
        detail="merged, post-merge janitor green",
    )
