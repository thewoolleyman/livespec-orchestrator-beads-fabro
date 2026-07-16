"""DispatchPlan dataclass and per-item plan construction."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_argv import (
    janitor_argv_with_default,
    janitor_core_checkout_path,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    DEFAULT_MERGE_ON_REVIEW_CAP,
    DEFAULT_REVIEW_FIX_CAP,
)

__all__: list[str] = [
    "DispatchPlan",
    "build_plan",
]

_DEFAULT_JANITOR_CORE_REPO_URL = "https://github.com/thewoolleyman/livespec.git"
_DEFAULT_JANITOR_CORE_REF = "master"
_MERGE_ON_REVIEW_CAP_DISABLED_OUTCOME = "__merge_on_review_cap_disabled__"


@dataclass(frozen=True, kw_only=True)
class DispatchPlan:
    """Everything one work-item dispatch needs, resolved up front.

    `branch` is the PUBLISH branch (`feat/<work-item-id>`) the phase
    graph's pr stage pushes and the engine polls — the Fabro-managed
    run branch inside the sandbox is run-internal and never leaves it.
    `workflow_toml` is the MATERIALIZED run-config overlay path (the
    committed config plus the credential env table), not the committed
    file itself. `janitor_checkout` is the path the engine provisions
    as a FRESH detached worktree of the merged ref and runs the
    post-merge janitor in — never the host primary's working tree,
    whose environment rot (stale `.venv` shebangs, stale `.coverage`,
    ghost `__pycache__` dirs) once false-redded a confirmed-green
    merge (work-item livespec-impl-beads-cgd).
    """

    repo: Path
    work_item_id: str
    branch: str
    workflow_toml: Path
    goal_file: Path
    fabro_bin: str
    janitor: tuple[str, ...]
    janitor_checkout: Path
    janitor_core_checkout: Path
    janitor_core_repo_url: str
    janitor_core_ref: str
    review_fix_visit_cap: int
    merge_on_review_cap_outcome: str


def build_plan(  # noqa: PLR0913 — kw-only plan resolver; each field is an independent caller input.
    *,
    repo: Path,
    work_item_id: str,
    workflow_toml: Path,
    goal_file: Path,
    fabro_bin: str,
    janitor: tuple[str, ...] | None,
    janitor_checkout: Path,
    janitor_core_repo_url: str = _DEFAULT_JANITOR_CORE_REPO_URL,
    janitor_core_ref: str = _DEFAULT_JANITOR_CORE_REF,
    review_fix_cap: int = DEFAULT_REVIEW_FIX_CAP,
    merge_on_review_cap: bool = DEFAULT_MERGE_ON_REVIEW_CAP,
) -> DispatchPlan:
    """Resolve the per-item dispatch plan (publish branch, argv config)."""
    return DispatchPlan(
        repo=repo,
        work_item_id=work_item_id,
        branch=f"feat/{work_item_id}",
        workflow_toml=workflow_toml,
        goal_file=goal_file,
        fabro_bin=fabro_bin,
        janitor=janitor_argv_with_default(janitor=janitor),
        janitor_checkout=janitor_checkout,
        janitor_core_checkout=janitor_core_checkout_path(janitor_checkout=janitor_checkout),
        janitor_core_repo_url=janitor_core_repo_url,
        janitor_core_ref=janitor_core_ref,
        review_fix_visit_cap=review_fix_cap + 1,
        merge_on_review_cap_outcome=(
            "succeeded" if merge_on_review_cap else _MERGE_ON_REVIEW_CAP_DISABLED_OUTCOME
        ),
    )
