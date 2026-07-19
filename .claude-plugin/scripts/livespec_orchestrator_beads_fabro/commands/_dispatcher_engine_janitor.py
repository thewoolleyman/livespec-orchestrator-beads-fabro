"""Post-merge janitor flow for the Dispatcher engine."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_journal import (
    run_stage,
    tail,
)
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
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

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


def _janitor_lock_path(*, plan: DispatchPlan) -> Path:
    return plan.janitor_checkout.with_name(f"{plan.janitor_checkout.name}.lock")


def _claim_janitor_lock(*, path: Path, owner: str) -> str | None:
    path.parent.mkdir(parents=True, exist_ok=True)
    opened = attempt(
        action=lambda: os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600),
        exceptions=(FileExistsError, OSError),
    )
    if isinstance(opened, AttemptFailure):
        return (
            f"janitor checkout lock {path} is already held for work-item {owner}; "
            "another post-merge janitor is using the janitor checkout. "
            f"Wait for that janitor to finish before retrying."
        )
    descriptor = opened
    with os.fdopen(descriptor, "wb") as handle:
        _ = handle.write(f"work_item_id={owner}\n".encode())
    return None


def _release_janitor_lock(*, path: Path) -> None:
    _ = attempt(action=path.unlink, exceptions=(FileNotFoundError, OSError))


def post_merge(
    *,
    outcome_type: type[DispatchOutcome],
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    merged: PrView,
) -> DispatchOutcome:
    lock_path = _janitor_lock_path(plan=plan)
    lock_detail = _claim_janitor_lock(path=lock_path, owner=plan.work_item_id)
    if lock_detail is not None:
        return outcome_type(
            work_item_id=plan.work_item_id,
            status="failed",
            stage="janitor-checkout-locked",
            pr_number=merged.number,
            merge_sha=merged.merge_sha,
            detail=lock_detail,
        )
    outcome = _post_merge_locked(
        outcome_type=outcome_type,
        plan=plan,
        runner=runner,
        journal=journal,
        merged=merged,
    )
    _release_janitor_lock(path=lock_path)
    return outcome


def _post_merge_locked(
    *,
    outcome_type: type[DispatchOutcome],
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    merged: PrView,
) -> DispatchOutcome:
    pull = run_stage(
        runner=runner,
        journal=journal,
        plan=plan,
        stage="pull-primary",
        command=(pull_primary_argv(plan=plan), plan.repo, _GIT_TIMEOUT_SECONDS, None),
    )
    if pull.exit_code != 0:
        return outcome_type(
            work_item_id=plan.work_item_id,
            status="failed",
            stage="pull-primary",
            pr_number=merged.number,
            merge_sha=merged.merge_sha,
            detail=tail(text=pull.stderr),
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
    janitor = run_stage(
        runner=runner,
        journal=journal,
        plan=plan,
        stage="janitor-post-merge",
        command=(
            list(plan.janitor),
            plan.janitor_checkout,
            _JANITOR_TIMEOUT_SECONDS,
            {CORE_PLUGIN_ROOT_ENV_VAR: str(plan.janitor_core_checkout / ".claude-plugin")},
        ),
    )
    if janitor.exit_code != 0:
        return outcome_type(
            work_item_id=plan.work_item_id,
            status="failed",
            stage="janitor-post-merge",
            pr_number=merged.number,
            merge_sha=merged.merge_sha,
            detail=(
                f"post-merge janitor red in fresh checkout {plan.janitor_checkout} "
                f"(kept for diagnosis): {tail(text=janitor.stderr)}"
            ),
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


def _provision_janitor_checkout(
    *,
    outcome_type: type[DispatchOutcome],
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    merged: PrView,
) -> DispatchOutcome | None:
    _ = run_stage(
        runner=runner,
        journal=journal,
        plan=plan,
        stage="janitor-checkout-preclean",
        command=(janitor_worktree_remove_argv(plan=plan), plan.repo, _GIT_TIMEOUT_SECONDS, None),
    )
    ref = merged.merge_sha if merged.merge_sha is not None else "origin/master"
    core_step = (
        f"provisioning livespec core at {plan.janitor_core_checkout} (ref {plan.janitor_core_ref})"
    )
    steps = (
        (
            "janitor-checkout-add",
            janitor_worktree_add_argv(plan=plan, ref=ref),
            plan.repo,
            f"provisioning the fresh janitor checkout at {plan.janitor_checkout} (ref {ref})",
        ),
        (
            "janitor-checkout-trust",
            janitor_trust_argv(),
            plan.janitor_checkout,
            f"`mise trust` inside the janitor checkout {plan.janitor_checkout}",
        ),
        (
            "janitor-checkout-bootstrap",
            janitor_bootstrap_argv(),
            plan.repo,
            f"installing canonical hooks via `just install-commit-refuse-hooks` in {plan.repo}",
        ),
        (
            "janitor-core-provision",
            janitor_core_clone_argv(plan=plan),
            plan.janitor_checkout,
            core_step,
        ),
    )
    for stage, argv, cwd, step in steps:
        result = run_stage(
            runner=runner,
            journal=journal,
            plan=plan,
            stage=stage,
            command=(argv, cwd, _GIT_TIMEOUT_SECONDS, None),
        )
        if result.exit_code != 0:
            return _merged_degraded(
                outcome_type=outcome_type,
                plan=plan,
                merged=merged,
                step=step,
                result=result,
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
    return outcome_type(
        work_item_id=plan.work_item_id,
        status="green",
        stage="janitor-env-degraded",
        pr_number=merged.number,
        merge_sha=merged.merge_sha,
        detail=(
            f"merged, but the post-merge janitor DID NOT RUN: {step} failed "
            f"({tail(text=result.stderr, limit=500)}). This is a host-environment "
            f"problem, not a work-item failure — the merge is confirmed on the "
            f"remote. Remediate the host, then run `{' '.join(plan.janitor)}` in "
            f"a clean checkout of merged master to close the gate by hand."
        ),
    )
