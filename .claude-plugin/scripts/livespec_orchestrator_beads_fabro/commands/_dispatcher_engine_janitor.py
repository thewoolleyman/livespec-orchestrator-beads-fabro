"""Post-merge janitor flow for the Dispatcher engine.

THE CHECK RUN'S VERDICT IS ABOUT THE MERGE, NEVER ABOUT HOW THE DISPATCH WAS
ROUTED. The janitor runs the target repository's check aggregate in a fresh
checkout of the merged default-branch tip, inheriting this process's own
environment -- which carries the variables the Dispatcher itself reads to
select a factory and to attribute a journal record. Those describe THIS
dispatch; they are not part of the merged code under test, and a governed
repository's suite legitimately exercises the code that reads them, so
inheriting them makes the verdict depend on the route. Measured 2026-10-17 on
`bd-ib-o6aeji`: the merge commit was green on the default branch's own CI, the
dispatch had been launched with the factory route exported, and the janitor
went red on 25 tests in exactly those areas -- stranding an already-merged item
`active` with no merge audit. Every merge dispatched through the documented
env-var route to a non-default factory failed that way.

The scrub reaches the RECONCILE janitor for free, because `reconcile-merged`
re-runs the post-merge flow through this same `post_merge`.
"""

from __future__ import annotations

import os
from contextlib import ExitStack
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_journal import (
    StageJournalOptions,
    journal_stage,
    run_stage,
    tail,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_hook_install_recipe import (
    JanitorBootstrapRecipe,
    resolve_janitor_bootstrap_recipe,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import INVOKER_ENV_VAR
from livespec_orchestrator_beads_fabro.commands._dispatcher_janitor_check_venue import (
    CLUSTER_GATE_ARGV,
    cluster_janitor_red,
    gate_tree_hash,
    host_janitor_red,
    janitor_check_row_fields,
    janitor_check_started_at,
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

__all__: list[str] = [
    "JANITOR_REMOVED_ENV_VARS",
    "janitor_env_delta",
    "janitor_removed_env_vars",
    "post_merge",
]

_GIT_TIMEOUT_SECONDS = 600.0
_JANITOR_TIMEOUT_SECONDS = 3600.0

# The dispatcher's factory-routing and invoker-attribution variables, removed
# from the janitor's check run. The factory name is spelled here rather than
# imported, because each reader holds its own PRIVATE constant for it
# (`_ENV_FABRO_FACTORY` in `_config` and in `_dispatcher_factory_ledger`) and a
# cross-module private import is the one thing this package's layering forbids;
# the invoker name is PUBLIC at its reader, so it comes from there. A later
# variable the Dispatcher reads to select a factory or to attribute a journal
# record belongs in this tuple.
JANITOR_REMOVED_ENV_VARS: tuple[str, ...] = ("LIVESPEC_FABRO_FACTORY", INVOKER_ENV_VAR)


def janitor_removed_env_vars() -> tuple[str, ...]:
    """Which scrubbed variables this Dispatcher's environment actually carries.

    The DELTA names the whole scrub set unconditionally; the journal row names
    what was really there, so a reader can tell a scrubbed run from one that
    inherited nothing.
    """
    return tuple(name for name in JANITOR_REMOVED_ENV_VARS if name in os.environ)


def janitor_env_delta(*, core_plugin_root: str) -> dict[str, str | None]:
    """The janitor check run's environment delta: one addition, the scrub as removals.

    Every other value the Dispatcher's environment carries is retained, because
    the check needs the credentials and the toolchain path it was invoked with.
    A removal is unconditional rather than conditioned on presence: removing a
    name this process does not carry is a no-op, so the delta states the whole
    scrub set instead of a reading of which members happened to be set.
    """
    return {
        CORE_PLUGIN_ROOT_ENV_VAR: core_plugin_root,
        **dict.fromkeys(JANITOR_REMOVED_ENV_VARS),
    }


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

    THE ROW IS WRITTEN HERE RATHER THAN THROUGH `run_stage`, which is the one
    stage in this flow that composes the run and the journal itself. Its row
    carries an account OF THE VENUE THAT RAN, and part of that account is read
    off the command's own output -- which does not exist until the command has
    returned. `run_stage` journals from inside, so it cannot be handed fields
    derived from the result it is still producing; putting a callable on the
    shared options for this one call site would make every other reader of that
    type read past a seam nothing else uses.

    THE ROUTE SCRUB IS THE SAME IN BOTH VENUES, and the addition is not. The
    removals carry this module's own rule -- the verdict is about the merge,
    never about how the dispatch was routed -- which a delegated gate owes
    exactly as a host-local suite does, and it is what keeps the stage's
    journaled removal account true whichever venue ran. The core plugin root is
    added for the HOST-LOCAL venue alone, because it exists so a suite running
    HERE can resolve this plugin inside the fresh checkout; the gate client
    reads no such root, and the pod re-derives its own checkout from the pushed
    tree.
    """
    on_the_cluster = janitor_runs_on_the_cluster(cwd=plan.repo)
    argv = list(CLUSTER_GATE_ARGV) if on_the_cluster else list(plan.janitor)
    env: dict[str, str | None] = (
        dict.fromkeys(JANITOR_REMOVED_ENV_VARS)
        if on_the_cluster
        else janitor_env_delta(core_plugin_root=str(plan.janitor_core_checkout / ".claude-plugin"))
    )
    # Read BEFORE the launch and only on the cluster venue, because it is the
    # tree that venue is about to ASK the gate about -- and because the
    # host-local row owes no gate account at all, so spending the reading there
    # would measure something no row reports.
    tree_hash = (
        gate_tree_hash(runner=runner, checkout=plan.janitor_checkout) if on_the_cluster else None
    )
    # Stamped LAST before the launch, after the tree reading above, so the
    # row's two instants bound the check suite itself rather than the readings
    # taken for its account.
    started_at = janitor_check_started_at()
    result = runner.run(
        argv=argv, cwd=plan.janitor_checkout, timeout_seconds=_JANITOR_TIMEOUT_SECONDS, env=env
    )
    journal_stage(
        journal=journal,
        plan=plan,
        stage="janitor-post-merge",
        result=result,
        # The check suite is the command whose red the retention clause exists
        # for: its excerpt names the suite, and the failing target it reports
        # is on the stream the excerpt did not keep. The removal list rides the
        # same options, because the scrub and its account are one policy for
        # this one stage.
        journal_options=StageJournalOptions(
            retention=plan.janitor_retention,
            removed_env_vars=janitor_removed_env_vars(),
            extra_fields=janitor_check_row_fields(
                on_the_cluster=on_the_cluster,
                result=result,
                tree_hash=tree_hash,
                started_at=started_at,
            ),
        ),
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
